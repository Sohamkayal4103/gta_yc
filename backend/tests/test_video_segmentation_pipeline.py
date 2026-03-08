import asyncio
import base64
import json
from io import BytesIO

import pytest
from PIL import Image, ImageChops, ImageStat

from backend.models.video_scene_schema import VideoSessionState
from backend.providers.gemini_scene import GeminiSceneClient
from backend.providers.overshoot import OvershootAdapter, OvershootSegmentResult, render_overlay
from backend.services import video_scene_pipeline as vsp
from backend.services.video_scene_pipeline import (
    _build_missions,
    _build_segmentation_summary,
    _ensure_hidden_mac_mini_object,
    list_events,
    load_state,
    persist_state,
)


def test_overshoot_adapter_parses_generic_objects_payload():
    adapter = OvershootAdapter("generic_v1")
    result = adapter.parse_response(
        {
            "objects": [
                {
                    "label": "chair",
                    "confidence": 0.91,
                    "bbox": [10, 20, 50, 60],
                    "polygon": [[10, 20], [60, 20], [60, 80], [10, 80]],
                    "mask": "ZmFrZQ==",
                }
            ]
        }
    )

    assert len(result.objects) == 1
    obj = result.objects[0]
    assert obj.label == "chair"
    assert obj.confidence == 0.91
    assert obj.bbox == [10.0, 20.0, 50.0, 60.0]
    assert obj.mask_b64 == "ZmFrZQ=="


def test_segmentation_summary_and_missions_reflect_people_detection():
    selected_frames = [
        {
            "frame_id": "frame_001",
            "timestamp_sec": 10,
            "objects": [
                {"label": "person", "confidence": 0.89},
                {"label": "door", "confidence": 0.74},
                {"label": "chair", "confidence": 0.61},
            ],
        },
        {
            "frame_id": "frame_002",
            "timestamp_sec": 20,
            "objects": [
                {"label": "person", "confidence": 0.91},
                {"label": "monitor", "confidence": 0.78},
            ],
        },
    ]

    summary = _build_segmentation_summary(selected_frames)
    assert summary["has_people"] is True
    assert summary["label_counts"]["person"] == 2

    missions = _build_missions({"objects": []}, selected_frames)
    assert len(missions) == 3
    # Contact mission should become rescue if person detected.
    contact = [m for m in missions if m.id == "mission_contact"][0]
    assert any(o.type == "rescue" for o in contact.objectives)

    climax = [m for m in missions if m.id == "mission_climax"][0]
    assert any((o.target_label or "").lower() == "mac mini" for o in climax.objectives)


def test_segmentation_summary_reports_geometry_quality():
    selected_frames = [
        {
            "frame_id": "frame_001",
            "timestamp_sec": 1,
            "objects": [
                {"label": "desk", "confidence": 0.9, "bbox": [1, 1, 10, 12], "polygon": [[0, 0], [1, 0], [1, 1]]},
                {"label": "lamp", "confidence": 0.8, "bbox": [5, 5, 8, 9], "polygon": [[0, 0], [1, 0], [1, 1]]},
            ],
        }
    ]

    summary = _build_segmentation_summary(selected_frames)
    assert summary["geometry_quality"] in {"high", "medium", "low"}
    assert summary["geometry_score"] > 0
    assert summary["bbox_valid_ratio"] == 1.0


def test_scene_is_enriched_with_hidden_mac_mini_when_missing():
    scene = {
        "room": {"width": 4, "depth": 4, "height": 2.8, "floor_color": "#222", "wall_color": "#444", "ceiling_color": "#eee"},
        "lights": [],
        "objects": [{"name": "Desk", "position": [0, 0, 0]}],
        "people": [],
    }

    _ensure_hidden_mac_mini_object(scene)
    assert any("mac mini" in obj.get("name", "").lower() for obj in scene.get("objects", []))


def test_render_overlay_uses_mask_data_and_avoids_black_output(tmp_path):
    source = tmp_path / "frame.jpg"
    overlay = tmp_path / "overlay.jpg"

    base = Image.new("RGB", (120, 80), (160, 160, 160))
    base.save(source)

    mask = Image.new("L", (60, 40), 255)
    buf = BytesIO()
    mask.save(buf, format="PNG")
    mask_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    objects = [
        OvershootSegmentResult(
            label="wall",
            confidence=0.88,
            bbox=[],
            polygon=[],
            mask_b64=mask_b64,
        )
    ]

    render_overlay(str(source), objects, str(overlay))

    assert overlay.exists()
    out = Image.open(overlay).convert("RGB")
    stat = ImageStat.Stat(out)
    avg = sum(stat.mean) / len(stat.mean)
    assert avg > 20  # Regression: no all-black previews.

    delta = ImageChops.difference(base, out)
    diff = ImageStat.Stat(delta).mean
    assert any(v > 1 for v in diff)


def test_generate_scene_failure_sets_session_error_state(tmp_path, monkeypatch):
    uploads_root = tmp_path / "uploads"
    sessions_root = uploads_root / "video_sessions"
    games_root = tmp_path / "games"

    monkeypatch.setattr(vsp, "UPLOAD_DIR", str(uploads_root))
    monkeypatch.setattr(vsp, "VIDEO_SESSIONS_ROOT", sessions_root)
    monkeypatch.setattr(vsp, "GAMES_DIR", str(games_root))

    session_id = "sess_error"
    vsp._ensure_dirs(session_id)

    state = VideoSessionState(
        session_id=session_id,
        status="ready_for_selection",
        stage="selection",
        progress=100,
        message="ready",
        frame_interval_sec=1.0,
        frames_total=1,
        frames_segmented=1,
    )
    persist_state(state)

    vsp._write_json(
        vsp._frames_index_path(session_id),
        [
            {
                "frame_id": "frame_000001",
                "frame_index": 0,
                "timestamp_sec": 1.0,
                "frame_path": str(tmp_path / "frame.jpg"),
                "frame_url": "/uploads/x.jpg",
                "overlay_url": "/uploads/y.jpg",
                "objects": [{"label": "chair", "confidence": 0.9}],
                "status": "complete",
                "error": None,
            }
        ],
    )

    def _boom(self, selected_frames):
        raise RuntimeError("gemini exploded")

    monkeypatch.setattr(vsp.GeminiSceneClient, "generate_scene_from_segments", _boom)

    with pytest.raises(RuntimeError):
        asyncio.run(vsp.generate_scene_from_selection(session_id, ["frame_000001"]))

    updated = load_state(session_id)
    assert updated is not None
    assert updated.status == "error"
    assert updated.stage == "failed"
    assert "gemini exploded" in (updated.error or "")

    events = list_events(session_id)
    assert any(evt.get("type") == "error" for evt in events)


def test_fallback_scene_prefers_semantic_layout_and_scales_room():
    client = GeminiSceneClient()
    selected_frames = [
        {
            "frame_id": "f1",
            "timestamp_sec": 0.1,
            "objects": [
                {"label": "chair", "confidence": 0.9},
                {"label": "chair", "confidence": 0.88},
                {"label": "desk", "confidence": 0.86},
                {"label": "person", "confidence": 0.91},
                {"label": "person", "confidence": 0.89},
                {"label": "door", "confidence": 0.82},
                {"label": "hallway", "confidence": 0.77},
            ],
        }
    ]

    scene = client._fallback_scene(selected_frames)
    assert scene["room"]["width"] >= 10.0
    assert scene["room"]["depth"] >= 9.0
    assert len(scene.get("people", [])) >= 1
    assert any("door" in str(obj.get("name", "")).lower() for obj in scene.get("objects", []))


def test_post_process_scene_expands_people_and_adds_connecting_door():
    client = GeminiSceneClient()
    selected_frames = [
        {
            "frame_id": "f1",
            "timestamp_sec": 0.1,
            "objects": [
                {"label": "person", "confidence": 0.9},
                {"label": "person", "confidence": 0.88},
                {"label": "person", "confidence": 0.87},
                {"label": "person", "confidence": 0.86},
                {"label": "kitchen", "confidence": 0.8},
            ],
        }
    ]

    scene = {
        "room": {"width": 7.0, "depth": 6.0, "height": 2.8},
        "objects": [{"name": "Desk", "position": [0, 0.45, 0], "size": [1.5, 0.8, 0.8], "nav_blocker": True}],
        "people": [],
        "lights": [],
    }

    processed = client._post_process_scene(scene, selected_frames)
    assert processed["room"]["width"] >= 10.0
    assert processed["room"]["depth"] >= 9.0
    assert len(processed["people"]) >= 2
    assert any("door" in str(obj.get("name", "")).lower() for obj in processed["objects"])


def test_gemini_scene_request_uses_raw_images_only_contract(tmp_path):
    class _FakeModels:
        def __init__(self):
            self.kwargs = None

        def generate_content(self, **kwargs):
            self.kwargs = kwargs
            return type(
                "Resp",
                (),
                {
                    "text": json.dumps(
                        {
                            "room": {"width": 10.2, "depth": 9.3, "height": 3.1, "floor_color": "#555", "wall_color": "#ccc", "ceiling_color": "#eee"},
                            "lights": [{"type": "ambient", "color": "#fff", "intensity": 0.5}],
                            "objects": [{"name": "Desk", "position": [0, 0.45, -2], "size": [1.2, 0.8, 0.7], "shape": "box", "color": "#999"}],
                            "people": [],
                        }
                    )
                },
            )()

    class _FakeClient:
        def __init__(self):
            self.models = _FakeModels()

    frame_path = tmp_path / "frame_001.jpg"
    Image.new("RGB", (96, 64), (80, 100, 120)).save(frame_path)

    client = GeminiSceneClient()
    client.enabled = True
    client.client = _FakeClient()
    client.model = "fake-model"

    selected_frames = [
        {
            "frame_id": "frame_001",
            "timestamp_sec": 1.25,
            "frame_path": str(frame_path),
            "objects": [
                {"label": "person", "confidence": 0.92, "bbox": [1, 2, 30, 40], "polygon": [[0, 0], [1, 0], [1, 1]]}
            ],
        }
    ]

    scene = client.generate_scene_from_segments(selected_frames)

    kwargs = client.client.models.kwargs
    assert kwargs is not None
    assert kwargs["model"] == "fake-model"
    contents = kwargs["contents"]
    assert isinstance(contents, list)
    assert len(contents) >= 2  # prompt + at least one raw image part

    prompt = str(contents[0]).lower()
    assert "raw" in prompt
    assert "no overshoot geometry" in prompt
    # Contract regression check: no concrete overshoot geometry payload leaks into prompt.
    assert "[1, 2, 30, 40]" not in prompt
    assert "frame_001_obj" not in prompt

    # Still post-processes for playability defaults.
    assert scene["room"]["width"] >= 10.0
    assert scene["room"]["depth"] >= 9.0


def test_generate_scene_result_contains_play_routes(tmp_path, monkeypatch):
    uploads_root = tmp_path / "uploads"
    sessions_root = uploads_root / "video_sessions"
    games_root = tmp_path / "games"

    monkeypatch.setattr(vsp, "UPLOAD_DIR", str(uploads_root))
    monkeypatch.setattr(vsp, "VIDEO_SESSIONS_ROOT", sessions_root)
    monkeypatch.setattr(vsp, "GAMES_DIR", str(games_root))
    monkeypatch.setattr(vsp, "_is_unreal_stream_available", lambda _url: False)

    session_id = "sess_success"
    vsp._ensure_dirs(session_id)

    state = VideoSessionState(
        session_id=session_id,
        status="ready_for_selection",
        stage="selection",
        progress=100,
        message="ready",
        frame_interval_sec=1.0,
        frames_total=1,
        frames_segmented=1,
    )
    persist_state(state)

    frame_path = tmp_path / "frame.jpg"
    Image.new("RGB", (64, 64), (120, 120, 120)).save(frame_path)

    vsp._write_json(
        vsp._frames_index_path(session_id),
        [
            {
                "frame_id": "frame_000001",
                "frame_index": 0,
                "timestamp_sec": 1.0,
                "frame_path": str(frame_path),
                "frame_url": "/uploads/x.jpg",
                "overlay_url": "/uploads/y.jpg",
                "objects": [{"label": "chair", "confidence": 0.9, "bbox": [1, 1, 10, 10], "polygon": [[0, 0], [1, 0], [1, 1]]}],
                "status": "complete",
                "error": None,
            }
        ],
    )

    monkeypatch.setattr(vsp.GeminiSceneClient, "generate_scene_from_segments", lambda _self, _frames: {
        "room": {"width": 8, "depth": 7, "height": 3, "floor_color": "#111", "wall_color": "#222", "ceiling_color": "#ddd"},
        "lights": [{"type": "ambient", "color": "#fff", "intensity": 0.5}],
        "objects": [{"name": "Desk", "position": [0, 0.5, 0], "shape": "box", "size": [1, 1, 1], "color": "#999"}],
        "people": [],
    })

    result = asyncio.run(vsp.generate_scene_from_selection(session_id, ["frame_000001"]))
    assert result.get("play_routes", {}).get("three_url") == f"/universe/{session_id}?engine=three"
    assert result.get("play_routes", {}).get("unreal_stream_available") is False
    assert result.get("models", {}).get("gemini")
    assert result.get("models", {}).get("overshoot_adapter")
    assert result.get("models", {}).get("overshoot_mode") in {"mock", "live"}
