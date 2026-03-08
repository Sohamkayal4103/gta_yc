import os
import uuid
import asyncio
import json
from typing import Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import UPLOAD_DIR, GAMES_DIR, TEMPLATES_DIR, SUPPORTED_GENRES
from backend.utils.storage import load_manifest
from backend.services.video_scene_pipeline import (
    create_realtime_session,
    create_video_session,
    generate_scene_from_selection,
    get_result,
    ingest_realtime_frame,
    list_events,
    list_frames,
    load_state,
    persist_state,
    process_video_session,
    schedule_background,
    stop_realtime_session,
)

app = FastAPI(title="RealmCast")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated game assets
app.mount("/static/games", StaticFiles(directory=GAMES_DIR), name="game_assets")
# Serve uploaded assets (video frames, overlays, masks)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
# Serve old frontend (legacy pages)
_old_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend_old")
if os.path.isdir(_old_frontend):
    app.mount("/frontend", StaticFiles(directory=_old_frontend, html=True), name="frontend")
# Serve game JS
app.mount("/game", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "game"), html=True), name="game_files")

# In-memory session status tracking
session_status: dict[str, dict] = {}

# In-memory session log accumulator (terminal-style)
session_logs: dict[str, list[str]] = {}


def session_log(session_id: str, msg: str):
    """Append a timestamped log line for a session."""
    from datetime import datetime
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    if session_id not in session_logs:
        session_logs[session_id] = []
    session_logs[session_id].append(line)
    print(f"[{session_id}] {msg}")

ROOM_DIRECTIONS = ("front", "back", "left", "right", "up", "down")


def _session_output_dir(session_id: str) -> str:
    return os.path.join(GAMES_DIR, session_id)


def _scene_path(session_id: str) -> str:
    return os.path.join(_session_output_dir(session_id), "scene.json")


def _load_scene_data(session_id: str) -> dict[str, Any]:
    scene_path = _scene_path(session_id)
    if not os.path.exists(scene_path):
        raise HTTPException(404, "Scene not found")
    with open(scene_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_scene_asset_manifest(session_id: str, scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Create runtime-friendly asset manifest placeholders for Three/Godot/Unreal."""
    output_dir = _session_output_dir(session_id)
    manifest: list[dict[str, Any]] = []

    for direction in ROOM_DIRECTIONS:
        img_path = os.path.join(output_dir, f"cubemap_{direction}.jpg")
        if os.path.exists(img_path):
            manifest.append({
                "key": f"cubemap.{direction}",
                "type": "texture",
                "url": f"/api/universe/{session_id}/cubemap/{direction}",
                "engine": "shared",
            })

    # Canonical object asset placeholders
    for idx, obj in enumerate(scene.get("objects", [])):
        name = (obj.get("name") or f"object_{idx}").strip()
        slug = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_") or f"object_{idx}"
        asset_ref = obj.get("asset_ref") or f"/Game/RealmCast/Generated/{slug}"
        manifest.append({
            "key": f"object.{idx}.{slug}",
            "type": "other",
            "url": asset_ref,
            "asset_variant": obj.get("asset_variant"),
            "material_slots": obj.get("material_slots", []),
            "lod_group": obj.get("lod_group"),
            "engine": "unreal",
            "placeholder": True,
        })

    return manifest


def _build_scene_bundle(session_id: str) -> dict[str, Any]:
    scene = _load_scene_data(session_id)
    return {
        "session_id": session_id,
        "scene": scene,
        "asset_manifest": _build_scene_asset_manifest(session_id, scene),
        "dialogue_seeds": [
            "Scan the room and identify key interaction anchors.",
            "Prioritize cinematic traversal with high-fidelity materials.",
            "Enable physics colliders for nav blockers and interactables.",
        ],
    }


def _build_unreal_scene_bundle(session_id: str) -> dict[str, Any]:
    base_bundle = _build_scene_bundle(session_id)
    scene = base_bundle["scene"]

    return {
        "session_id": session_id,
        "runtime": "unreal",
        "engine_version": "5.x",
        "map_name": f"RealmCast_{session_id}",
        "streaming": {
            "pixel_streaming": {
                "signaling_url": os.getenv("UE_SIGNALING_URL", "ws://127.0.0.1:8888"),
                "player_url": os.getenv("UE_PLAYER_URL", "http://127.0.0.1:80"),
            }
        },
        "scene": scene,
        "asset_manifest": base_bundle["asset_manifest"],
        "spawn": {
            "default_player_start": [0.0, 100.0, 0.0],
            "spawn_tags": ["player_start", "runtime_generated"],
        },
        "world_settings": {
            "nanite": True,
            "lumen": True,
            "hardware_ray_tracing": True,
            "scalability": "Cinematic",
        },
        "notes": [
            "Asset paths are placeholders until Unreal content import pipeline is wired.",
            "Use object metadata fields to map Blueprints/StaticMesh assignments.",
        ],
    }


@app.get("/")
async def root():
    """Serve the upload page (legacy frontend)."""
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend_old", "index.html")
    if os.path.exists(frontend_path):
        with open(frontend_path, "r") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>RealmCast</h1><p>Frontend is served on <a href='http://localhost:3000/3d'>localhost:3000</a></p>")


@app.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "service": "realmcast-backend",
        "sessions_tracked": len(session_status),
    }


@app.post("/api/generate")
async def generate_game(
    selfie_video: UploadFile = File(...),
    genre: str = Form(...),
    ui_debug_log: str = Form(""),
    room_video: UploadFile | None = File(None),
    room_front_video: UploadFile | None = File(None),
    room_back_video: UploadFile | None = File(None),
    room_left_video: UploadFile | None = File(None),
    room_right_video: UploadFile | None = File(None),
    room_up_video: UploadFile | None = File(None),
    room_down_video: UploadFile | None = File(None),
):
    """Upload videos and start game generation pipeline."""
    if genre not in SUPPORTED_GENRES:
        raise HTTPException(400, f"Genre must be one of: {SUPPORTED_GENRES}")

    session_id = str(uuid.uuid4())[:8]
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # Save uploaded selfie
    selfie_path = os.path.join(session_dir, "selfie.mp4")
    with open(selfie_path, "wb") as f:
        content = await selfie_video.read()
        f.write(content)

    # Save room views (front/back/left/right/up/down)
    room_uploads = {
        "front": room_front_video,
        "back": room_back_video,
        "left": room_left_video,
        "right": room_right_video,
        "up": room_up_video,
        "down": room_down_video,
    }

    room_views: dict[str, str] = {}
    upload_receipt: dict = {
        "session_id": session_id,
        "genre": genre,
        "selfie": {},
        "room_views": {},
        "ui_debug_events_count": 0,
    }

    upload_receipt["selfie"] = {
        "filename": selfie_video.filename,
        "saved_path": selfie_path,
        "bytes": os.path.getsize(selfie_path),
        "content_type": selfie_video.content_type,
    }

    # Backward compatibility: a single room_video is treated as the "front" view
    if room_video and room_video.filename:
        legacy_path = os.path.join(session_dir, "room_front.mp4")
        with open(legacy_path, "wb") as f:
            content = await room_video.read()
            f.write(content)
        room_views["front"] = legacy_path
        upload_receipt["room_views"]["front"] = {
            "filename": room_video.filename,
            "saved_path": legacy_path,
            "bytes": os.path.getsize(legacy_path),
            "content_type": room_video.content_type,
            "source": "legacy_room_video",
        }

    for direction in ROOM_DIRECTIONS:
        upload = room_uploads[direction]
        if not upload or not upload.filename:
            continue

        ext = os.path.splitext(upload.filename)[1] or ".mp4"
        view_path = os.path.join(session_dir, f"room_{direction}{ext}")
        with open(view_path, "wb") as f:
            content = await upload.read()
            f.write(content)
        room_views[direction] = view_path
        upload_receipt["room_views"][direction] = {
            "filename": upload.filename,
            "saved_path": view_path,
            "bytes": os.path.getsize(view_path),
            "content_type": upload.content_type,
            "source": "directional_room_video",
        }

    if not room_views:
        raise HTTPException(
            400,
            "Upload at least one room video view. Best results use front/back/left/right/up/down.",
        )

    # Persist immediate upload receipt and UI interaction trace for observability.
    ui_events = []
    if ui_debug_log:
        try:
            ui_events = json.loads(ui_debug_log)
            if not isinstance(ui_events, list):
                ui_events = [{"raw_ui_debug_log": ui_debug_log}]
        except json.JSONDecodeError:
            ui_events = [{"raw_ui_debug_log": ui_debug_log}]
    upload_receipt["ui_debug_events_count"] = len(ui_events)

    with open(os.path.join(session_dir, "upload_receipt.json"), "w", encoding="utf-8") as f:
        json.dump(upload_receipt, f, indent=2)
    with open(os.path.join(session_dir, "ui_interactions.json"), "w", encoding="utf-8") as f:
        json.dump(ui_events, f, indent=2)

    # Initialize status
    session_status[session_id] = {
        "status": "processing",
        "stage": "initializing",
        "progress": 0,
        "message": f"Starting generation pipeline with {len(room_views)} room view(s)..."
    }

    # Start pipeline in background
    asyncio.create_task(
        run_pipeline(
            session_id,
            room_views,
            selfie_path,
            genre,
            ui_events=ui_events,
            upload_receipt=upload_receipt,
        )
    )

    return {"session_id": session_id, "status": "processing"}


async def run_pipeline(
    session_id: str,
    room_views: dict[str, str],
    selfie_path: str,
    genre: str,
    ui_events: list | None = None,
    upload_receipt: dict | None = None,
):
    """Run the full generation pipeline in background."""
    from backend.pipeline import run_generation_pipeline
    try:
        await run_generation_pipeline(
            session_id,
            room_views,
            selfie_path,
            genre,
            session_status,
            ui_events=ui_events or [],
            upload_receipt=upload_receipt or {},
        )
    except Exception as e:
        session_status[session_id] = {
            "status": "error",
            "stage": "failed",
            "progress": 0,
            "message": str(e)
        }


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    """Poll generation progress."""
    if session_id not in session_status:
        raise HTTPException(404, "Session not found")
    return session_status[session_id]


@app.get("/api/game/{session_id}/manifest.json")
async def get_manifest(session_id: str):
    """Get the game manifest."""
    manifest = load_manifest(session_id)
    if not manifest:
        raise HTTPException(404, "Game not found")
    return JSONResponse(manifest)


@app.get("/play/{session_id}")
async def serve_game(session_id: str):
    """Serve the playable game page."""
    manifest = load_manifest(session_id)
    if not manifest:
        raise HTTPException(404, "Game not found")

    template_path = os.path.join(TEMPLATES_DIR, "game.html")
    with open(template_path, "r") as f:
        html = f.read()

    html = html.replace("{{SESSION_ID}}", session_id)
    html = html.replace("{{GENRE}}", manifest.get("genre", "fantasy"))
    return HTMLResponse(html)


## ─── 3D Universe Mode ────────────────────────────────────────────────────────

@app.post("/api/generate-3d")
async def generate_3d_universe(
    room_front_image: UploadFile | None = File(None),
    room_back_image: UploadFile | None = File(None),
    room_left_image: UploadFile | None = File(None),
    room_right_image: UploadFile | None = File(None),
    room_up_image: UploadFile | None = File(None),
    room_down_image: UploadFile | None = File(None),
):
    """Upload directional images and start 3D universe generation."""
    session_id = str(uuid.uuid4())[:8]
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # Also create output dir for cubemap images and scene.json
    output_dir = os.path.join(GAMES_DIR, session_id)
    os.makedirs(output_dir, exist_ok=True)

    room_uploads = {
        "front": room_front_image,
        "back": room_back_image,
        "left": room_left_image,
        "right": room_right_image,
        "up": room_up_image,
        "down": room_down_image,
    }

    room_views: dict[str, str] = {}
    for direction in ROOM_DIRECTIONS:
        upload = room_uploads[direction]
        if not upload or not upload.filename:
            continue
        ext = os.path.splitext(upload.filename)[1] or ".jpg"
        # Save to upload dir for Gemini analysis
        view_path = os.path.join(session_dir, f"room_{direction}{ext}")
        content = await upload.read()
        with open(view_path, "wb") as f:
            f.write(content)
        room_views[direction] = view_path

        # Also save as cubemap image in output dir for serving to frontend
        cubemap_path = os.path.join(output_dir, f"cubemap_{direction}.jpg")
        with open(cubemap_path, "wb") as f:
            f.write(content)

    if not room_views:
        raise HTTPException(400, "Upload at least one directional room image.")

    msg = f"Starting 3D universe generation with {len(room_views)} view(s)..."
    session_log(session_id, msg)
    session_status[session_id] = {
        "status": "processing",
        "stage": "initializing",
        "progress": 5,
        "message": msg,
    }

    asyncio.create_task(run_3d_pipeline(session_id, room_views))
    return {"session_id": session_id, "status": "processing"}


async def run_3d_pipeline(session_id: str, room_views: dict[str, str]):
    """Run the 3D universe generation pipeline in background."""
    from backend.agents.universe_builder import build_universe

    def on_progress(stage, progress, message):
        session_log(session_id, message)
        session_status[session_id] = {
            "status": "processing",
            "stage": stage,
            "progress": progress,
            "message": message,
        }

    try:
        result = await build_universe(
            room_views,
            session_id=session_id,
            on_progress=on_progress,
            on_log=lambda msg: session_log(session_id, msg),
        )

        # Save scene.json to disk
        output_dir = os.path.join(GAMES_DIR, session_id)
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "scene.json"), "w", encoding="utf-8") as f:
            json.dump(result["scene"], f, indent=2)

        # Save descriptions for debug
        with open(os.path.join(output_dir, "descriptions.txt"), "w", encoding="utf-8") as f:
            f.write(result["descriptions"])

        session_log(session_id, "Scene JSON saved. 3D Universe ready!")
        session_status[session_id] = {
            "status": "complete",
            "stage": "complete",
            "progress": 100,
            "message": "3D Universe ready!",
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        session_log(session_id, f"CRITICAL ERROR: {e}")
        session_status[session_id] = {
            "status": "error",
            "stage": "failed",
            "progress": 0,
            "message": str(e),
        }


@app.get("/api/logs/{session_id}")
async def get_logs(session_id: str):
    """Return accumulated log lines for a session."""
    return {"logs": session_logs.get(session_id, [])}


@app.get("/api/universe/{session_id}/scene.json")
async def get_scene_json(session_id: str):
    """Serve the scene JSON for a session."""
    return JSONResponse(_load_scene_data(session_id))


@app.get("/api/universe/{session_id}/bundle")
async def get_scene_bundle(session_id: str):
    """Canonical runtime scene bundle consumed by web runtimes."""
    return JSONResponse(_build_scene_bundle(session_id))


@app.get("/api/universe/{session_id}/asset-manifest")
async def get_scene_asset_manifest(session_id: str):
    scene = _load_scene_data(session_id)
    return JSONResponse({
        "session_id": session_id,
        "asset_manifest": _build_scene_asset_manifest(session_id, scene),
    })


@app.get("/api/universe/{session_id}/unreal/scene-bundle")
async def get_unreal_scene_bundle(session_id: str):
    """Unreal-friendly scene payload with placeholder manifest and stream settings."""
    return JSONResponse(_build_unreal_scene_bundle(session_id))


@app.get("/api/universe/{session_id}/cubemap/{direction}")
async def get_cubemap_image(session_id: str, direction: str):
    """Serve a cubemap image for a session."""
    if direction not in ROOM_DIRECTIONS:
        raise HTTPException(400, f"Direction must be one of: {ROOM_DIRECTIONS}")
    image_path = os.path.join(GAMES_DIR, session_id, f"cubemap_{direction}.jpg")
    if not os.path.exists(image_path):
        raise HTTPException(404, f"Cubemap image not found for direction: {direction}")
    return FileResponse(image_path, media_type="image/jpeg")


## ─── Video Segmentation → Scene Generation Pipeline ──────────────────────────

@app.post("/api/video-segmentation/sessions")
async def create_video_segmentation_session(
    video: UploadFile = File(...),
    frame_interval_sec: float = Form(10.0),
):
    """Create a video-driven segmentation session and start frame extraction + segmentation."""
    if frame_interval_sec <= 0:
        raise HTTPException(400, "frame_interval_sec must be > 0")

    session_id, video_path, state = await create_video_session(video.filename or "input.mp4", frame_interval_sec)

    with open(video_path, "wb") as f:
        f.write(await video.read())

    state.message = (
        "Video uploaded. Starting frame extraction and Overshoot segmentation "
        f"({state.overshoot_mode}/{state.overshoot_adapter}); Gemini model={state.gemini_model}."
    )
    state.progress = 5
    persist_state(state)

    schedule_background(process_video_session(session_id))

    return {
        "session_id": session_id,
        "status": state.status,
        "stage": state.stage,
        "progress": state.progress,
        "message": state.message,
    }


@app.get("/api/video-segmentation/sessions/{session_id}")
async def get_video_segmentation_session(session_id: str):
    state = load_state(session_id)
    if not state:
        raise HTTPException(404, "Session not found")
    return state.model_dump()


@app.get("/api/video-segmentation/sessions/{session_id}/frames")
async def get_video_segmentation_frames(session_id: str):
    state = load_state(session_id)
    if not state:
        raise HTTPException(404, "Session not found")
    return {
        "session_id": session_id,
        "status": state.status,
        "frames": list_frames(session_id),
    }


@app.post("/api/video-segmentation/realtime/sessions")
async def create_realtime_video_segmentation_session(
    frame_interval_sec: float = Form(10.0),
    capture_mode: str = Form("interval"),
):
    if frame_interval_sec <= 0:
        raise HTTPException(400, "frame_interval_sec must be > 0")
    if capture_mode not in {"interval", "scene_change"}:
        raise HTTPException(400, "capture_mode must be interval or scene_change")

    state = await create_realtime_session(frame_interval_sec=frame_interval_sec, capture_mode=capture_mode)
    return state.model_dump()


@app.post("/api/video-segmentation/realtime/sessions/{session_id}/frames")
async def upload_realtime_frame(
    session_id: str,
    frame: UploadFile = File(...),
    timestamp_sec: float | None = Form(None),
):
    if not frame.filename:
        raise HTTPException(400, "Frame file is required")

    raw = await frame.read()
    max_upload_mb = float(os.getenv("REALTIME_MAX_UPLOAD_MB", "8"))
    if len(raw) > max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Frame too large. Max {max_upload_mb}MB")

    try:
        payload = await ingest_realtime_frame(session_id, raw, timestamp_sec=timestamp_sec)
        return {"session_id": session_id, "accepted": True, "frame": payload}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/video-segmentation/realtime/sessions/{session_id}/stop")
async def stop_realtime_video_segmentation_session(session_id: str):
    try:
        state = await stop_realtime_session(session_id)
        return state.model_dump()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/video-segmentation/sessions/{session_id}/events")
async def get_video_segmentation_events(
    session_id: str,
    since: int = Query(0, ge=0),
):
    state = load_state(session_id)
    if not state:
        raise HTTPException(404, "Session not found")
    return {
        "session_id": session_id,
        "since": since,
        "latest": state.event_seq,
        "events": list_events(session_id, since_seq=since),
    }


@app.post("/api/video-segmentation/sessions/{session_id}/scene")
async def submit_selected_frames_for_scene(
    session_id: str,
    payload: dict = Body(...),
):
    selected_frame_ids = payload.get("selected_frame_ids") or []
    if not isinstance(selected_frame_ids, list) or not selected_frame_ids:
        raise HTTPException(400, {"code": "INVALID_SELECTION", "message": "selected_frame_ids must be a non-empty list"})

    try:
        result = await generate_scene_from_selection(session_id, selected_frame_ids)
        return {
            "session_id": session_id,
            "scene_id": result.get("scene_id"),
            "status": "complete",
            "result": result,
        }
    except ValueError as exc:
        raise HTTPException(400, {"code": "INVALID_SELECTION", "message": str(exc)})
    except RuntimeError as exc:
        raise HTTPException(404, {"code": "SESSION_NOT_FOUND", "message": str(exc)})
    except Exception as exc:
        raise HTTPException(500, {"code": "SCENE_GENERATION_FAILED", "message": str(exc)})


@app.get("/api/video-segmentation/sessions/{session_id}/result")
async def get_video_segmentation_result(session_id: str):
    result = get_result(session_id)
    if not result:
        raise HTTPException(404, "Result not found")
    return result


@app.post("/api/video-segmentation/sessions/{session_id}/missions")
async def regenerate_video_segmentation_missions(session_id: str):
    """Alias endpoint for mission generation integrated with scene output."""
    state = load_state(session_id)
    if not state:
        raise HTTPException(404, "Session not found")
    result = get_result(session_id)
    if not result:
        raise HTTPException(409, "Scene not generated yet. Submit selected frames first.")
    return {
        "session_id": session_id,
        "scene_id": result.get("scene_id"),
        "missions": result.get("bundle", {}).get("missions", []),
        "mission_objects": result.get("bundle", {}).get("mission_objects", []),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
