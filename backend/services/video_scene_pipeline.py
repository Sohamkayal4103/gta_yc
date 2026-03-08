from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.config import GAMES_DIR, GEMINI_MODEL, UPLOAD_DIR
from backend.models.video_scene_schema import (
    FrameSegmentation,
    MissionObjective,
    MissionSpec,
    UnrealSceneBundle,
    VideoSessionState,
)
from backend.providers.gemini_scene import GeminiSceneClient
from backend.providers.overshoot import (
    OvershootClient,
    render_overlay,
    write_mask_from_base64,
    write_mask_from_bbox,
)


VIDEO_SESSIONS_ROOT = Path(UPLOAD_DIR) / "video_sessions"

_session_cache: dict[str, VideoSessionState] = {}
_realtime_queues: dict[str, asyncio.Queue] = {}
_realtime_workers: dict[str, asyncio.Task] = {}
_session_locks: dict[str, asyncio.Lock] = {}


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _session_root(session_id: str) -> Path:
    return VIDEO_SESSIONS_ROOT / session_id


def _state_path(session_id: str) -> Path:
    return _session_root(session_id) / "metadata" / "session_state.json"


def _frames_index_path(session_id: str) -> Path:
    return _session_root(session_id) / "metadata" / "frames_index.json"


def _result_path(session_id: str) -> Path:
    return _session_root(session_id) / "metadata" / "scene_result.json"


def _events_path(session_id: str) -> Path:
    return _session_root(session_id) / "metadata" / "events.json"


def _is_unreal_stream_available(player_url: str) -> bool:
    explicit = os.getenv("UE_STREAM_AVAILABLE", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False

    try:
        with urllib.request.urlopen(player_url, timeout=2.5) as response:
            return int(getattr(response, "status", 0) or 0) < 500
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def _runtime_context() -> dict[str, Any]:
    overshoot = OvershootClient()
    return {
        "overshoot_mode": "mock" if overshoot.mock_mode else "live",
        "overshoot_adapter": overshoot.adapter.adapter_name,
        "gemini_model": GEMINI_MODEL,
    }


def _ensure_runtime_metadata(state: VideoSessionState) -> VideoSessionState:
    runtime = _runtime_context()
    if not state.overshoot_mode:
        state.overshoot_mode = runtime["overshoot_mode"]
    if not (state.overshoot_adapter or "").strip():
        state.overshoot_adapter = runtime["overshoot_adapter"]
    if not (state.gemini_model or "").strip():
        state.gemini_model = runtime["gemini_model"]
    return state


def _play_routes(session_id: str) -> dict[str, Any]:
    player_url = os.getenv("UE_PLAYER_URL", "http://127.0.0.1:80")
    unreal_available = _is_unreal_stream_available(player_url)
    encoded_player_url = urllib.parse.quote(player_url, safe="")
    return {
        "three_url": f"/universe/{session_id}?engine=three",
        "unreal_url": f"/universe/{session_id}?engine=unreal&playerUrl={encoded_player_url}",
        "unreal_player_url": player_url,
        "unreal_stream_available": unreal_available,
    }


def _ensure_dirs(session_id: str) -> dict[str, Path]:
    root = _session_root(session_id)
    dirs = {
        "root": root,
        "video": root / "video",
        "frames": root / "frames",
        "segmentation": root / "segmentation",
        "metadata": root / "metadata",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_public_path(path: Path) -> str:
    rel = path.relative_to(Path(UPLOAD_DIR)).as_posix()
    return f"/uploads/{rel}"


def persist_state(state: VideoSessionState) -> None:
    _ensure_runtime_metadata(state)
    _session_cache[state.session_id] = state
    _write_json(_state_path(state.session_id), state.model_dump())


def load_state(session_id: str) -> VideoSessionState | None:
    if session_id in _session_cache:
        return _session_cache[session_id]
    payload = _read_json(_state_path(session_id), None)
    if not payload:
        return None
    state = VideoSessionState(**payload)
    _ensure_runtime_metadata(state)
    _session_cache[session_id] = state
    return state


def list_frames(session_id: str) -> list[dict[str, Any]]:
    return _read_json(_frames_index_path(session_id), [])


def get_result(session_id: str) -> dict[str, Any] | None:
    payload = _read_json(_result_path(session_id), None)
    return payload


def list_events(session_id: str, since_seq: int = 0) -> list[dict[str, Any]]:
    events = _read_json(_events_path(session_id), [])
    return [evt for evt in events if int(evt.get("seq", 0)) > since_seq]


def _append_event(session_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state = load_state(session_id)
    if not state:
        return {}

    events = _read_json(_events_path(session_id), [])
    state.event_seq += 1
    event = {
        "seq": state.event_seq,
        "ts": _utc_now(),
        "type": event_type,
        "message": message,
        "payload": payload or {},
    }
    events.append(event)
    _write_json(_events_path(session_id), events)
    persist_state(state)
    return event


def _detect_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def extract_frames_every_interval(video_path: Path, output_dir: Path, interval_sec: float) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame_%06d.jpg"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{interval_sec}",
        "-q:v",
        "2",
        str(pattern),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed: {proc.stderr[-500:]}")

    extracted = sorted(output_dir.glob("frame_*.jpg"))
    duration = _detect_duration(video_path)

    frames = []
    for idx, frame_path in enumerate(extracted):
        frames.append(
            {
                "frame_id": frame_path.stem,
                "frame_index": idx,
                "timestamp_sec": round(idx * interval_sec, 3),
                "frame_path": str(frame_path),
                "frame_url": _to_public_path(frame_path),
            }
        )

    if frames and duration > 0:
        # Clamp final timestamp to actual duration for display correctness.
        frames[-1]["timestamp_sec"] = min(frames[-1]["timestamp_sec"], round(duration, 3))

    return frames


def _build_segmentation_summary(selected_frames: list[dict[str, Any]]) -> dict[str, Any]:
    labels = Counter()
    confidences: dict[str, list[float]] = {}
    total_objects = 0
    valid_bbox = 0
    valid_polygon = 0

    for frame in selected_frames:
        for obj in frame.get("objects", []):
            label = str(obj.get("label", "unknown")).lower()
            labels[label] += 1
            confidences.setdefault(label, []).append(float(obj.get("confidence", 0.0)))

            total_objects += 1
            bbox = obj.get("bbox") or []
            if isinstance(bbox, list) and len(bbox) == 4 and float(bbox[2] or 0) > 0 and float(bbox[3] or 0) > 0:
                valid_bbox += 1
            polygon = obj.get("polygon") or []
            if isinstance(polygon, list) and len(polygon) >= 3:
                valid_polygon += 1

    avg_conf = {
        label: (sum(vals) / len(vals)) if vals else 0.0
        for label, vals in confidences.items()
    }

    bbox_ratio = (valid_bbox / total_objects) if total_objects else 0.0
    polygon_ratio = (valid_polygon / total_objects) if total_objects else 0.0
    geometry_score = (bbox_ratio * 0.55) + (polygon_ratio * 0.45)
    if geometry_score >= 0.75:
        geometry_quality = "high"
    elif geometry_score >= 0.45:
        geometry_quality = "medium"
    else:
        geometry_quality = "low"

    return {
        "selected_frames": len(selected_frames),
        "label_counts": dict(labels),
        "avg_confidence": avg_conf,
        "has_people": any("person" in k for k in labels.keys()),
        "geometry_quality": geometry_quality,
        "geometry_score": round(geometry_score, 3),
        "bbox_valid_ratio": round(bbox_ratio, 3),
        "polygon_valid_ratio": round(polygon_ratio, 3),
    }


def _build_missions(scene: dict[str, Any], selected_frames: list[dict[str, Any]]) -> list[MissionSpec]:
    summary = _build_segmentation_summary(selected_frames)
    label_counts = Counter(summary.get("label_counts", {}))

    top_labels = [k for k, _ in label_counts.most_common(5)]
    has_people = summary.get("has_people", False)

    objectives_1 = [
        MissionObjective(
            id="obj_m1_1",
            type="investigate",
            description=f"Survey detected zone containing {top_labels[0] if top_labels else 'key objects'}",
            target_label=top_labels[0] if top_labels else None,
            confidence=summary.get("avg_confidence", {}).get(top_labels[0], 0.0) if top_labels else None,
        )
    ]
    if len(top_labels) > 1:
        objectives_1.append(
            MissionObjective(
                id="obj_m1_2",
                type="navigate",
                description=f"Reach and scan the {top_labels[1]} interaction area",
                target_label=top_labels[1],
                confidence=summary.get("avg_confidence", {}).get(top_labels[1], 0.0),
            )
        )

    mission_1 = MissionSpec(
        id="mission_recon",
        title="Spatial Recon Run",
        description="Map the room layout and verify interaction anchors from segmentation intelligence.",
        difficulty="easy",
        objectives=objectives_1,
        rewards={"xp": 100, "intel": "layout_map"},
    )

    objective_2_type = "rescue" if has_people else "secure"
    objective_2_desc = "Secure safe passage for detected civilian(s)." if has_people else "Secure critical interactable assets."
    mission_2 = MissionSpec(
        id="mission_contact",
        title="Contact and Control",
        description="Use the highest-confidence detections to establish tactical control.",
        difficulty="medium",
        objectives=[
            MissionObjective(
                id="obj_m2_1",
                type=objective_2_type,
                description=objective_2_desc,
                target_label="person" if has_people else (top_labels[0] if top_labels else None),
                confidence=summary.get("avg_confidence", {}).get("person", 0.0) if has_people else None,
            ),
            MissionObjective(
                id="obj_m2_2",
                type="interact",
                description="Trigger 2 environment interactions without collision violations.",
                target_label=top_labels[2] if len(top_labels) > 2 else (top_labels[0] if top_labels else None),
                confidence=summary.get("avg_confidence", {}).get(top_labels[2], 0.0) if len(top_labels) > 2 else None,
            ),
        ],
        rewards={"xp": 220, "unlock": "advanced_tools"},
    )

    mission_3 = MissionSpec(
        id="mission_climax",
        title="Mission-Ready Extraction",
        description="Complete the final objective chain with realistic interactions and navigation.",
        difficulty="hard",
        objectives=[
            MissionObjective(
                id="obj_m3_1",
                type="collect",
                description="Collect mission package from highest confidence object cluster.",
                target_label=top_labels[0] if top_labels else None,
                confidence=summary.get("avg_confidence", {}).get(top_labels[0], 0.0) if top_labels else None,
            ),
            MissionObjective(
                id="obj_m3_2",
                type="secure",
                description="Hold the extraction zone for 30 seconds.",
                target_label=top_labels[1] if len(top_labels) > 1 else None,
                confidence=summary.get("avg_confidence", {}).get(top_labels[1], 0.0) if len(top_labels) > 1 else None,
            ),
            MissionObjective(
                id="obj_m3_hidden_mac_mini",
                type="investigate",
                description="Locate the hidden Mac mini in the generated scene and verify it by interaction.",
                target_label="mac mini",
                confidence=None,
            ),
        ],
        rewards={"xp": 500, "unlock": "playable_browser_mission"},
    )

    return [mission_1, mission_2, mission_3]


def _mission_objects(scene: dict[str, Any], missions: list[MissionSpec]) -> list[dict[str, Any]]:
    objs = []
    scene_objects = scene.get("objects", []) or []
    for mission in missions:
        for objective in mission.objectives:
            label = objective.target_label
            if not label:
                continue
            match = next(
                (obj for obj in scene_objects if label.lower() in str(obj.get("name", "")).lower()),
                None,
            )
            if not match:
                continue
            objs.append(
                {
                    "mission_id": mission.id,
                    "objective_id": objective.id,
                    "target_label": label,
                    "object_name": match.get("name"),
                    "position": match.get("position", [0, 0, 0]),
                    "interaction": match.get("interaction", "none"),
                }
            )
    return objs


def _ensure_hidden_mac_mini_object(scene: dict[str, Any]) -> None:
    objects = scene.setdefault("objects", [])
    if any("mac mini" in str(obj.get("name", "")).lower() for obj in objects):
        return

    objects.append(
        {
            "name": "Hidden Mac Mini",
            "shape": "box",
            "position": [2.1, 0.2, -1.9],
            "size": [0.22, 0.04, 0.22],
            "rotation": [0, 18, 0],
            "color": "#9ca3af",
            "material": "aluminum",
            "roughness": 0.25,
            "metalness": 0.85,
            "interaction": "use",
            "asset_ref": "/Game/RealmCast/Generated/hidden_mac_mini",
            "asset_variant": "space_gray",
            "material_slots": ["shell"],
            "collider_type": "box",
            "nav_blocker": False,
            "interaction_anchor": {"x": 2.1, "y": 0.35, "z": -1.9},
            "animation_profile": None,
            "audio_profile": "device_hum",
            "lod_group": "small_props",
            "spawn_tags": ["generated", "mission_target", "hidden_mac_mini"],
            "children": [],
        }
    )


def _session_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


def _upsert_frame_record(session_id: str, frame_record: dict[str, Any]) -> None:
    frame_id = frame_record.get("frame_id")
    frames = list_frames(session_id)
    for idx, item in enumerate(frames):
        if item.get("frame_id") == frame_id:
            frames[idx] = frame_record
            _write_json(_frames_index_path(session_id), frames)
            return
    frames.append(frame_record)
    _write_json(_frames_index_path(session_id), frames)


def _segment_single_frame(client: OvershootClient, root: Path, frame: dict[str, Any]) -> dict[str, Any]:
    frame_id = frame["frame_id"]
    frame_path = Path(frame["frame_path"])
    seg_dir = root / "segmentation" / frame_id
    seg_dir.mkdir(parents=True, exist_ok=True)

    model = FrameSegmentation(
        frame_id=frame_id,
        frame_index=frame["frame_index"],
        timestamp_sec=frame["timestamp_sec"],
        frame_path=frame["frame_path"],
        status="pending",
    )

    try:
        result = client.segment_frame(str(frame_path))
        overlay_path = seg_dir / "overlay.jpg"
        render_overlay(str(frame_path), result.objects, str(overlay_path))

        objects_payload = []
        for obj_idx, obj in enumerate(result.objects):
            mask_path = None
            mask_error = None
            try:
                if obj.mask_b64:
                    mask_path = seg_dir / f"mask_{obj_idx:02d}.png"
                    write_mask_from_base64(obj.mask_b64, str(mask_path))
                elif len(obj.bbox) == 4:
                    mask_path = seg_dir / f"mask_{obj_idx:02d}.png"
                    from PIL import Image

                    image = Image.open(frame_path)
                    write_mask_from_bbox(image.size, obj.bbox, str(mask_path))
            except Exception as exc:
                mask_path = None
                mask_error = str(exc)

            objects_payload.append(
                {
                    "id": f"{frame_id}_obj_{obj_idx}",
                    "label": obj.label,
                    "confidence": obj.confidence,
                    "bbox": obj.bbox,
                    "polygon": obj.polygon,
                    "mask": {
                        "path": _to_public_path(mask_path) if mask_path else None,
                    },
                    "metadata": {
                        **(obj.metadata or {}),
                        **({"mask_error": mask_error} if mask_error else {}),
                    },
                }
            )

        model.overlay_path = _to_public_path(overlay_path)
        model.objects = objects_payload  # type: ignore[assignment]
        model.status = "complete"
    except Exception as exc:
        model.status = "error"
        model.error = str(exc)

    return {
        **frame,
        "frame_url": _to_public_path(Path(frame["frame_path"])),
        "overlay_url": model.overlay_path,
        "objects": model.objects,
        "status": model.status,
        "error": model.error,
    }


async def process_video_session(session_id: str) -> None:
    state = load_state(session_id)
    if not state:
        return

    root = _session_root(session_id)
    metadata = _read_json(root / "metadata" / "upload.json", {})
    video_path = Path(metadata["video_path"])

    try:
        state.stage = "frame_extraction"
        state.progress = 10
        state.message = "Extracting frames from uploaded video"
        persist_state(state)
        _append_event(session_id, "status", state.message, {"stage": state.stage, "progress": state.progress})

        frames = extract_frames_every_interval(video_path, root / "frames", state.frame_interval_sec)
        if not frames:
            raise RuntimeError("No frames extracted from video. Ensure ffmpeg is installed and video is valid.")

        state.frames_total = len(frames)
        state.progress = 20
        client = OvershootClient()
        state.overshoot_mode = "mock" if client.mock_mode else "live"
        state.overshoot_adapter = client.adapter.adapter_name
        state.message = (
            f"Extracted {len(frames)} frames. Running Overshoot segmentation "
            f"({state.overshoot_mode}/{state.overshoot_adapter})..."
        )
        persist_state(state)
        _append_event(
            session_id,
            "status",
            state.message,
            {
                "stage": state.stage,
                "progress": state.progress,
                "overshoot_mode": state.overshoot_mode,
                "overshoot_adapter": state.overshoot_adapter,
            },
        )

        frame_records: list[dict[str, Any]] = []

        for idx, frame in enumerate(frames):
            frame_record = _segment_single_frame(client, root, frame)
            frame_records.append(frame_record)

            state.frames_segmented = idx + 1
            state.progress = min(90, 20 + int(70 * ((idx + 1) / max(1, len(frames)))))
            state.stage = "segmentation"
            state.message = f"Segmented frame {idx + 1}/{len(frames)}"
            persist_state(state)
            _write_json(_frames_index_path(session_id), frame_records)
            _append_event(
                session_id,
                "frame_segmented",
                state.message,
                {
                    "frame_id": frame_record.get("frame_id"),
                    "status": frame_record.get("status"),
                    "objects": len(frame_record.get("objects") or []),
                    "overshoot_mode": state.overshoot_mode,
                    "overshoot_adapter": state.overshoot_adapter,
                },
            )

        state.status = "ready_for_selection"
        state.stage = "selection"
        state.progress = 100
        state.message = "Segmentation complete. Select the best frames to generate scene."
        persist_state(state)
        _append_event(session_id, "ready", state.message, {"stage": state.stage, "progress": state.progress})
    except Exception as exc:
        state.status = "error"
        state.stage = "failed"
        state.error = str(exc)
        state.message = str(exc)
        persist_state(state)
        _append_event(session_id, "error", state.message, {"stage": state.stage})


async def _realtime_worker(session_id: str) -> None:
    queue = _realtime_queues.get(session_id)
    if not queue:
        return

    root = _session_root(session_id)
    client = OvershootClient()

    while True:
        frame = await queue.get()
        if frame is None:
            queue.task_done()
            break

        state = load_state(session_id)
        if not state:
            queue.task_done()
            continue

        try:
            frame_record = _segment_single_frame(client, root, frame)
            async with _session_lock(session_id):
                _upsert_frame_record(session_id, frame_record)
                state = load_state(session_id)
                if state:
                    state.frames_segmented += 1
                    state.stage = "live_segmentation"
                    state.overshoot_mode = "mock" if client.mock_mode else "live"
                    state.overshoot_adapter = client.adapter.adapter_name
                    state.progress = min(95, 5 + int(90 * (state.frames_segmented / max(1, state.frames_total))))
                    state.message = (
                        f"Live segmented {state.frames_segmented}/{state.frames_total} frame(s) "
                        f"via Overshoot {state.overshoot_mode}/{state.overshoot_adapter}"
                    )
                    persist_state(state)
                    _append_event(
                        session_id,
                        "frame_segmented",
                        state.message,
                        {
                            "frame_id": frame_record.get("frame_id"),
                            "status": frame_record.get("status"),
                            "objects": len(frame_record.get("objects") or []),
                            "overshoot_mode": state.overshoot_mode,
                            "overshoot_adapter": state.overshoot_adapter,
                        },
                    )
        except Exception as exc:
            _append_event(session_id, "error", f"Realtime frame segmentation failed: {exc}", {"frame_id": frame.get("frame_id")})
        finally:
            queue.task_done()


def _start_realtime_worker(session_id: str) -> None:
    if session_id in _realtime_workers and not _realtime_workers[session_id].done():
        return
    queue = _realtime_queues.setdefault(session_id, asyncio.Queue())
    _realtime_workers[session_id] = asyncio.create_task(_realtime_worker(session_id))


async def create_video_session(video_filename: str, frame_interval_sec: float) -> tuple[str, Path, VideoSessionState]:
    session_id = uuid.uuid4().hex[:10]
    dirs = _ensure_dirs(session_id)

    runtime_ctx = _runtime_context()
    state = VideoSessionState(
        session_id=session_id,
        status="processing",
        stage="initializing",
        progress=0,
        message="Video session created",
        frame_interval_sec=frame_interval_sec,
        overshoot_mode=runtime_ctx["overshoot_mode"],
        overshoot_adapter=runtime_ctx["overshoot_adapter"],
        gemini_model=runtime_ctx["gemini_model"],
    )
    persist_state(state)

    safe_name = video_filename or "input.mp4"
    video_path = dirs["video"] / safe_name
    _write_json(
        dirs["metadata"] / "upload.json",
        {
            "session_id": session_id,
            "video_path": str(video_path),
            "frame_interval_sec": frame_interval_sec,
            "created_at": _utc_now(),
            "mode": "video_upload",
        },
    )

    _append_event(
        session_id,
        "session_created",
        "Video segmentation session created",
        {
            "mode": "video_upload",
            "overshoot_mode": state.overshoot_mode,
            "overshoot_adapter": state.overshoot_adapter,
            "gemini_model": state.gemini_model,
        },
    )
    return session_id, video_path, state


async def create_realtime_session(frame_interval_sec: float, capture_mode: str = "interval") -> VideoSessionState:
    session_id = uuid.uuid4().hex[:10]
    dirs = _ensure_dirs(session_id)

    runtime_ctx = _runtime_context()
    state = VideoSessionState(
        session_id=session_id,
        status="live_capturing",
        stage="live_capture",
        progress=0,
        message="Realtime camera session created. Awaiting frames.",
        frame_interval_sec=frame_interval_sec,
        realtime=True,
        capture_mode="scene_change" if capture_mode == "scene_change" else "interval",
        overshoot_mode=runtime_ctx["overshoot_mode"],
        overshoot_adapter=runtime_ctx["overshoot_adapter"],
        gemini_model=runtime_ctx["gemini_model"],
    )
    persist_state(state)

    _write_json(
        dirs["metadata"] / "upload.json",
        {
            "session_id": session_id,
            "frame_interval_sec": frame_interval_sec,
            "created_at": _utc_now(),
            "mode": "realtime_camera",
            "capture_mode": state.capture_mode,
        },
    )

    _write_json(_frames_index_path(session_id), [])
    _write_json(_events_path(session_id), [])

    _realtime_queues[session_id] = asyncio.Queue()
    _start_realtime_worker(session_id)
    _append_event(
        session_id,
        "session_created",
        "Realtime session started",
        {
            "mode": "realtime_camera",
            "capture_mode": state.capture_mode,
            "overshoot_mode": state.overshoot_mode,
            "overshoot_adapter": state.overshoot_adapter,
            "gemini_model": state.gemini_model,
        },
    )
    return state


async def ingest_realtime_frame(session_id: str, frame_bytes: bytes, timestamp_sec: float | None = None) -> dict[str, Any]:
    state = load_state(session_id)
    if not state:
        raise RuntimeError("Session not found")
    if not state.realtime:
        raise RuntimeError("Session is not a realtime camera session")
    if state.status == "error":
        raise RuntimeError("Session is in error state")

    dirs = _ensure_dirs(session_id)
    root = _session_root(session_id)

    async with _session_lock(session_id):
        frames = list_frames(session_id)
        frame_index = len(frames)
        frame_id = f"frame_{frame_index + 1:06d}"
        frame_path = dirs["frames"] / f"{frame_id}.jpg"

        with open(frame_path, "wb") as f:
            f.write(frame_bytes)

        ts = float(timestamp_sec) if timestamp_sec is not None else round(frame_index * state.frame_interval_sec, 3)
        frame_record = {
            "frame_id": frame_id,
            "frame_index": frame_index,
            "timestamp_sec": ts,
            "frame_path": str(frame_path),
            "frame_url": _to_public_path(frame_path),
            "overlay_url": None,
            "objects": [],
            "status": "pending",
            "error": None,
        }

        frames.append(frame_record)
        _write_json(_frames_index_path(session_id), frames)

        state.frames_total = len(frames)
        state.status = "live_capturing"
        state.stage = "live_capture"
        state.message = f"Captured {state.frames_total} frame(s). Segmentation running in background."
        state.progress = min(80, 2 + int(78 * (state.frames_segmented / max(1, state.frames_total))))
        persist_state(state)

    queue = _realtime_queues.setdefault(session_id, asyncio.Queue())
    await queue.put(frame_record)
    _append_event(session_id, "frame_uploaded", f"Frame {frame_id} uploaded", {"frame_id": frame_id, "timestamp_sec": ts})
    return frame_record


async def stop_realtime_session(session_id: str) -> VideoSessionState:
    state = load_state(session_id)
    if not state:
        raise RuntimeError("Session not found")

    queue = _realtime_queues.get(session_id)
    if queue:
        await queue.join()
        await queue.put(None)

    worker = _realtime_workers.get(session_id)
    if worker:
        try:
            await worker
        except Exception:
            pass

    state = load_state(session_id)
    if not state:
        raise RuntimeError("Session not found")

    if state.frames_total == 0:
        state.status = "error"
        state.stage = "failed"
        state.error = "No frames uploaded in realtime session"
        state.message = state.error
    else:
        state.status = "ready_for_selection"
        state.stage = "selection"
        state.progress = 100
        state.message = "Realtime capture stopped. Select segmented frames to generate scene."
    persist_state(state)
    _append_event(session_id, "capture_stopped", state.message, {"frames_total": state.frames_total, "frames_segmented": state.frames_segmented})
    return state


async def generate_scene_from_selection(session_id: str, selected_frame_ids: list[str]) -> dict[str, Any]:
    state = load_state(session_id)
    if not state:
        raise RuntimeError("Session not found")

    selected_ids = [str(fid) for fid in selected_frame_ids if str(fid).strip()]
    if not selected_ids:
        raise ValueError("No selected frame ids provided")

    frames = list_frames(session_id)
    frames_by_id = {str(f.get("frame_id")): f for f in frames}

    missing_ids = [fid for fid in selected_ids if fid not in frames_by_id]
    if missing_ids:
        raise ValueError(f"Selected frame ids not found: {', '.join(missing_ids[:8])}")

    selected = [frames_by_id[fid] for fid in selected_ids]
    selected_complete = [f for f in selected if f.get("status") == "complete"]
    if not selected_complete:
        raise ValueError("Selected frames are not segmented yet. Wait for segmentation to complete and retry.")

    _ensure_runtime_metadata(state)
    state.status = "generating_scene"
    state.stage = "gemini_scene_generation"
    state.progress = 10
    state.selected_frame_ids = selected_ids
    state.error = None
    state.message = (
        f"Generating scene from {len(selected_complete)} selected frames with Gemini model {state.gemini_model} "
        "(raw images only; Overshoot geometry retained for UI/missions)."
    )
    persist_state(state)
    _append_event(
        session_id,
        "gemini_scene_generation",
        state.message,
        {
            "stage": state.stage,
            "progress": state.progress,
            "selected_frame_ids": selected_ids,
            "gemini_model": state.gemini_model,
            "overshoot_adapter": state.overshoot_adapter,
            "overshoot_mode": state.overshoot_mode,
            "gemini_input_contract": "raw_selected_images_only_no_overshoot_geometry",
        },
    )

    try:
        gemini = GeminiSceneClient()
        scene = gemini.generate_scene_from_segments(selected_complete)
        _ensure_hidden_mac_mini_object(scene)

        state.progress = 55
        state.message = "Gemini layout draft ready. Synthesizing mission pack and play routes"
        persist_state(state)
        _append_event(
            session_id,
            "gemini_scene_ready",
            state.message,
            {
                "stage": state.stage,
                "progress": state.progress,
                "gemini_model": state.gemini_model,
            },
        )

        state.progress = 70
        state.message = "Generating mission pack from segmentation insights"
        persist_state(state)
        _append_event(session_id, "status", state.message, {"stage": state.stage, "progress": state.progress})

        missions = _build_missions(scene, selected_complete)
        mission_objects = _mission_objects(scene, missions)
        summary = _build_segmentation_summary(selected_complete)

        scene_id = f"scene_{session_id}_{uuid.uuid4().hex[:6]}"
        bundle = UnrealSceneBundle(
            session_id=session_id,
            scene_id=scene_id,
            map_name=f"RealmCastVideo_{session_id}",
            world_settings={
                "nanite": True,
                "lumen": True,
                "hardware_ray_tracing": True,
                "scalability": "Cinematic",
                "post_processing": {"ao": True, "ssr": True, "exposure": "auto"},
            },
            scene=scene,
            missions=missions,
            mission_objects=mission_objects,
            segmentation_summary=summary,
            notes=[
                "Generated from Overshoot segmentation + Gemini scene synthesis.",
                "Use mission_objects to wire browser gameplay objective triggers.",
                "Mandatory mission objective included: hidden Mac mini search.",
            ],
        )

        state.progress = 85
        state.message = "Persisting Unreal-ready payload"
        persist_state(state)

        play_routes = _play_routes(session_id)
        runtime_meta = _runtime_context()
        result_payload = {
            "session_id": session_id,
            "scene_id": scene_id,
            "created_at": _utc_now(),
            "selected_frame_ids": selected_ids,
            "selected_frames": selected_complete,
            "bundle": bundle.model_dump(),
            "models": {
                "gemini": state.gemini_model or runtime_meta["gemini_model"],
                "overshoot_adapter": state.overshoot_adapter or runtime_meta["overshoot_adapter"],
                "overshoot_mode": state.overshoot_mode or runtime_meta["overshoot_mode"],
            },
            "play_routes": play_routes,
        }

        _write_json(_result_path(session_id), result_payload)

        # Integrate with existing universe route surface by writing scene.json into static/games
        game_dir = Path(GAMES_DIR) / session_id
        game_dir.mkdir(parents=True, exist_ok=True)
        _write_json(game_dir / "scene.json", scene)
        _write_json(game_dir / "unreal_scene_bundle.video.json", bundle.model_dump())

        state.status = "complete"
        state.stage = "complete"
        state.progress = 100
        state.scene_id = scene_id
        state.error = None
        state.message = "Scene + mission bundle ready"
        persist_state(state)
        _append_event(
            session_id,
            "complete",
            state.message,
            {
                "scene_id": scene_id,
                "play_routes": play_routes,
                "gemini_model": state.gemini_model,
                "overshoot_adapter": state.overshoot_adapter,
                "overshoot_mode": state.overshoot_mode,
            },
        )

        return result_payload
    except Exception as exc:
        state.status = "error"
        state.stage = "failed"
        state.error = str(exc)
        state.message = f"Scene generation failed: {exc}"
        persist_state(state)
        _append_event(
            session_id,
            "error",
            state.message,
            {"stage": state.stage, "selected_frame_ids": selected_ids},
        )
        raise


def schedule_background(coro):
    return asyncio.create_task(coro)
