"""Pipeline orchestrator — chains all 4 agents to produce a playable game."""

import os
import json as _json
import asyncio
import re
import shutil
from backend.config import MAP_SIZE
from backend.utils.storage import get_session_dir, save_manifest, save_debug_log
from backend.agents.spatial_analyst import analyze_room, describe_selfie
from backend.agents.mission_agent import generate_missions
from backend.agents.world_artist import generate_all_art
from backend.agents.audio_director import generate_all_audio


DEFAULT_RUNTIME_METADATA = {
    "asset_ref": None,
    "asset_variant": None,
    "material_slots": [],
    "collider_type": "box",
    "nav_blocker": None,
    "interaction_anchor": None,
    "animation_profile": None,
    "audio_profile": None,
    "lod_group": None,
    "spawn_tags": [],
}


def _apply_runtime_metadata_defaults(obj: dict) -> dict:
    """Attach canonical runtime metadata fields to an object in-place."""
    for key, value in DEFAULT_RUNTIME_METADATA.items():
        if key not in obj:
            if isinstance(value, list):
                obj[key] = list(value)
            elif isinstance(value, dict):
                obj[key] = dict(value)
            else:
                obj[key] = value
    return obj


def _update_status(session_status: dict, session_id: str, stage: str, progress: int, message: str):
    session_status[session_id] = {
        "status": "processing",
        "stage": stage,
        "progress": progress,
        "message": message,
    }


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _find_best_object_index(target_name: str, objects: list[dict]) -> int | None:
    target_normalized = _normalize_name(target_name)
    if not target_normalized:
        return None

    target_tokens = set(target_normalized.split())
    best_idx = None
    best_score = 0.0

    for idx, obj in enumerate(objects):
        obj_name = obj.get("name", "")
        obj_normalized = _normalize_name(obj_name)
        if not obj_normalized:
            continue

        if obj_normalized == target_normalized:
            return idx

        score = 0.0
        if target_normalized in obj_normalized or obj_normalized in target_normalized:
            score = max(score, 0.95)

        obj_tokens = set(obj_normalized.split())
        if target_tokens and obj_tokens:
            overlap = len(target_tokens & obj_tokens) / len(target_tokens | obj_tokens)
            score = max(score, overlap)

        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx is None or best_score < 0.35:
        return None
    return best_idx


def _ensure_mission_targets_reachable(room_layout: dict, mission_data: dict):
    """Make sure all mission targets can be interacted with in gameplay."""
    objects = room_layout.get("objects", [])
    if not objects:
        return

    for mission in mission_data.get("missions", []):
        for step in mission.get("steps", []):
            target_name = step.get("target_object")
            if not target_name:
                continue

            obj_idx = _find_best_object_index(target_name, objects)
            if obj_idx is not None:
                matched_obj = objects[obj_idx]
                matched_name = matched_obj.get("name", target_name)

                if not matched_obj.get("is_interactable"):
                    print(
                        f"[PIPELINE] Marking mission target as interactable: "
                        f"'{matched_name}' for step target '{target_name}'"
                    )
                    matched_obj["is_interactable"] = True

                if _normalize_name(target_name) != _normalize_name(matched_name):
                    print(
                        f"[PIPELINE] Normalizing mission step target '{target_name}' "
                        f"-> '{matched_name}'"
                    )
                    step["target_object"] = matched_name
                continue

            fallback_idx = next(
                (i for i, obj in enumerate(objects) if obj.get("is_interactable")),
                0,
            )
            fallback_name = objects[fallback_idx].get("name", target_name)
            objects[fallback_idx]["is_interactable"] = True
            step["target_object"] = fallback_name
            print(
                f"[PIPELINE] WARNING: Unknown target '{target_name}'. "
                f"Rewriting step target to '{fallback_name}'."
            )


def _extract_generated_asset_paths(session_dir: str, art_assets: dict, audio_assets: dict) -> list[str]:
    relative_paths: list[str] = []

    def _add_if_exists(filename: str | None):
        if not filename:
            return
        path = os.path.join(session_dir, filename)
        if os.path.exists(path) and os.path.isfile(path):
            relative_paths.append(filename)

    _add_if_exists(art_assets.get("map"))
    _add_if_exists(art_assets.get("player"))
    for npc_file in art_assets.get("npcs", []):
        _add_if_exists(npc_file)

    _add_if_exists(audio_assets.get("soundtrack"))
    for sfx_file in audio_assets.get("sfx", {}).values():
        _add_if_exists(sfx_file)

    # Deduplicate while preserving order
    return list(dict.fromkeys(relative_paths))


def _collect_llm_call_artifacts(session_dir: str) -> list[dict]:
    llm_logs_dir = os.path.join(session_dir, "llm_logs")
    if not os.path.exists(llm_logs_dir):
        return []

    calls: list[dict] = []
    for call_id in sorted(os.listdir(llm_logs_dir)):
        call_dir = os.path.join(llm_logs_dir, call_id)
        if not os.path.isdir(call_dir):
            continue

        request_json = os.path.join(call_dir, "request.json")
        response_json = os.path.join(call_dir, "response.json")
        response_blobs_dir = os.path.join(call_dir, "response_blobs")
        response_blobs = []
        if os.path.isdir(response_blobs_dir):
            response_blobs = sorted(
                os.path.join("llm_logs", call_id, "response_blobs", name)
                for name in os.listdir(response_blobs_dir)
                if os.path.isfile(os.path.join(response_blobs_dir, name))
            )

        calls.append(
            {
                "call_id": call_id,
                "request_json": os.path.join("llm_logs", call_id, "request.json")
                if os.path.exists(request_json) else None,
                "response_json": os.path.join("llm_logs", call_id, "response.json")
                if os.path.exists(response_json) else None,
                "response_blobs": response_blobs,
            }
        )
    return calls


def _write_run_artifacts_overview(session_id: str, session_dir: str, art_assets: dict, audio_assets: dict) -> None:
    run_artifacts_dir = os.path.join(session_dir, "run_artifacts")
    assets_dir = os.path.join(run_artifacts_dir, "assets")
    responses_dir = os.path.join(run_artifacts_dir, "responses")
    os.makedirs(assets_dir, exist_ok=True)
    os.makedirs(responses_dir, exist_ok=True)

    generated_assets = _extract_generated_asset_paths(session_dir, art_assets, audio_assets)
    for rel_path in generated_assets:
        src = os.path.join(session_dir, rel_path)
        dst = os.path.join(assets_dir, os.path.basename(rel_path))
        if os.path.exists(src):
            shutil.copy2(src, dst)

    llm_calls = _collect_llm_call_artifacts(session_dir)
    for call in llm_calls:
        response_src = call.get("response_json")
        if not response_src:
            continue
        response_src_path = os.path.join(session_dir, response_src)
        if not os.path.exists(response_src_path):
            continue
        response_dst = os.path.join(responses_dir, f"{call['call_id']}_response.json")
        shutil.copy2(response_src_path, response_dst)

    llm_logs_dir = os.path.join(session_dir, "llm_logs")
    logs_symlink = os.path.join(run_artifacts_dir, "logs")
    if os.path.isdir(llm_logs_dir) and not os.path.exists(logs_symlink):
        try:
            os.symlink(os.path.relpath(llm_logs_dir, run_artifacts_dir), logs_symlink)
        except OSError:
            pass

    overview = {
        "session_id": session_id,
        "run_directory": session_dir,
        "assets_directory": "run_artifacts/assets",
        "responses_directory": "run_artifacts/responses",
        "generated_assets": generated_assets,
        "llm_logs_directory": "llm_logs",
        "llm_calls": llm_calls,
        "upload_receipt_file": "00_upload_receipt.json",
        "ui_interactions_file": "00_ui_interactions.json",
        "notes": "Generated assets are copied into run_artifacts/assets. Full request/response traces live in llm_logs/.",
    }

    with open(os.path.join(run_artifacts_dir, "overview.json"), "w", encoding="utf-8") as f:
        _json.dump(overview, f, indent=2)


async def run_generation_pipeline(
    session_id: str,
    room_input: str | dict[str, str],
    selfie_path: str,
    genre: str,
    session_status: dict,
    ui_events: list | None = None,
    upload_receipt: dict | None = None,
):
    """Run the full generation pipeline."""
    session_dir = get_session_dir(session_id)

    print(f"\n{'='*60}")
    print(f"[PIPELINE] Starting for session={session_id}, genre={genre}")
    if isinstance(room_input, dict):
        print(f"[PIPELINE] Room videos by direction: {room_input}")
    else:
        print(f"[PIPELINE] Room video: {room_input}")
    print(f"[PIPELINE] Selfie: {selfie_path}")
    print(f"[PIPELINE] Output dir: {session_dir}")
    print(f"{'='*60}\n")

    if upload_receipt:
        save_debug_log(session_id, "00_upload_receipt.json", _json.dumps(upload_receipt, indent=2))
    if ui_events is not None:
        save_debug_log(session_id, "00_ui_interactions.json", _json.dumps(ui_events, indent=2))

    # ── Stage 1: Describe + Analyze Room ──
    _update_status(session_status, session_id, "spatial_analysis", 5,
                   "AI is watching your room video...")

    print("[PIPELINE] Stage 1a: Describing room video...")
    room_layout = await analyze_room(room_input, session_id=session_id)

    # Save the room description as a debug file
    room_desc = room_layout.pop("_room_description_detailed", "")
    view_descriptions = room_layout.pop("_view_descriptions", {})
    view_layouts = room_layout.pop("_view_layouts", {})

    save_debug_log(session_id, "01_room_description.txt", room_desc)
    if view_descriptions:
        save_debug_log(session_id, "01b_room_descriptions_by_view.json", _json.dumps(view_descriptions, indent=2))
        for direction, text in view_descriptions.items():
            save_debug_log(session_id, f"01c_room_description_{direction}.txt", text)
    if view_layouts:
        save_debug_log(session_id, "02b_room_layouts_by_view.json", _json.dumps(view_layouts, indent=2))
    for obj in room_layout.get("objects", []):
        _apply_runtime_metadata_defaults(obj)

    save_debug_log(session_id, "02_room_layout.json", _json.dumps(room_layout, indent=2))

    obj_count = len(room_layout.get("objects", []))
    interactable_count = sum(1 for o in room_layout.get("objects", []) if o.get("is_interactable"))
    print(f"[PIPELINE] Spatial analysis complete: {obj_count} objects, {interactable_count} interactable")
    print(f"[PIPELINE] Objects: {[o['name'] for o in room_layout.get('objects', [])]}")

    _update_status(session_status, session_id, "spatial_analysis", 25,
                   f"Found {obj_count} objects in your space.")

    # ── Stage 1b: Describe Selfie ──
    _update_status(session_status, session_id, "spatial_analysis", 28,
                   "Analyzing your selfie video...")

    print("[PIPELINE] Stage 1b: Describing selfie video...")
    selfie_description = await describe_selfie(selfie_path, session_id=session_id)
    save_debug_log(session_id, "03_selfie_description.txt", selfie_description)

    _update_status(session_status, session_id, "spatial_analysis", 30,
                   "Selfie analyzed.")

    # ── Stage 2: Mission Generation ──
    _update_status(session_status, session_id, "missions", 35,
                   "Generating GTA-style missions...")

    print("[PIPELINE] Stage 2: Mission Generation...")
    mission_data = await generate_missions(room_layout, genre, session_id=session_id)
    _ensure_mission_targets_reachable(room_layout, mission_data)
    save_debug_log(session_id, "04_missions.json", _json.dumps(mission_data, indent=2))

    mission_count = len(mission_data.get("missions", []))
    npc_count = len(mission_data.get("npcs", []))
    print(f"[PIPELINE] Missions: {mission_count}, NPCs: {npc_count}")
    for m in mission_data.get("missions", []):
        print(f"[PIPELINE]   Mission: {m.get('title', 'untitled')} ({len(m.get('steps', []))} steps)")

    _update_status(session_status, session_id, "missions", 45,
                   f"Generated {mission_count} missions.")

    # ── Stage 3 & 4: Art + Audio (parallel) ──
    _update_status(session_status, session_id, "art", 50,
                   "Creating your game world and character...")

    print("[PIPELINE] Stage 3+4: Art + Audio (parallel)...")

    # Pass descriptions to art generation
    art_task = generate_all_art(
        room_layout, selfie_path, genre,
        mission_data.get("npcs", []), session_dir,
        room_description=room_desc,
        selfie_description=selfie_description,
        session_id=session_id,
    )
    audio_task = generate_all_audio(genre, session_dir, session_id=session_id)

    art_assets, audio_assets = await asyncio.gather(art_task, audio_task)
    print(f"[PIPELINE] Art assets: {art_assets}")
    print(f"[PIPELINE] Audio assets: {audio_assets}")

    # Log file sizes
    print(f"\n[PIPELINE] === Generated Files ===")
    for f in sorted(os.listdir(session_dir)):
        fpath = os.path.join(session_dir, f)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            print(f"[PIPELINE]   {f}: {size:,} bytes")
    print()

    _update_status(session_status, session_id, "assembly", 85,
                   "Assembling your universe...")

    # ── Stage 5: Assembly ──
    collision_rects = []
    interactables = []

    for i, obj in enumerate(room_layout.get("objects", [])):
        _apply_runtime_metadata_defaults(obj)

        x = obj["x_percent"] * MAP_SIZE
        y = obj["y_percent"] * MAP_SIZE
        w = obj["width_percent"] * MAP_SIZE
        h = obj["height_percent"] * MAP_SIZE

        collision_rects.append({
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "object_name": obj["name"],
            "collider_type": obj.get("collider_type", "box"),
            "nav_blocker": obj.get("nav_blocker"),
        })

        if obj.get("is_interactable"):
            interactables.append({
                "id": f"obj_{i}",
                "name": obj["name"],
                "game_name": obj.get("game_name", obj["name"]),
                "x": x + w / 2,
                "y": y + h / 2,
                "w": w,
                "h": h,
                "description": obj.get("description", ""),
                "asset_ref": obj.get("asset_ref"),
                "asset_variant": obj.get("asset_variant"),
                "material_slots": obj.get("material_slots", []),
                "collider_type": obj.get("collider_type", "box"),
                "nav_blocker": obj.get("nav_blocker"),
                "interaction_anchor": obj.get("interaction_anchor"),
                "animation_profile": obj.get("animation_profile"),
                "audio_profile": obj.get("audio_profile"),
                "lod_group": obj.get("lod_group"),
                "spawn_tags": obj.get("spawn_tags", []),
            })

    # Find spawn point away from objects
    spawn_x = MAP_SIZE / 2
    spawn_y = MAP_SIZE / 2
    occupied = {(int(r["x"] / 64), int(r["y"] / 64)) for r in collision_rects}
    for test_y in range(MAP_SIZE // 2, MAP_SIZE, 64):
        for test_x in range(MAP_SIZE // 2, MAP_SIZE, 64):
            grid = (test_x // 64, test_y // 64)
            if grid not in occupied:
                spawn_x = float(test_x)
                spawn_y = float(test_y)
                break
        else:
            continue
        break

    manifest = {
        "session_id": session_id,
        "genre": genre,
        "room_layout": room_layout,
        "missions": mission_data,
        "assets": art_assets,
        "audio": audio_assets,
        "map_width": MAP_SIZE,
        "map_height": MAP_SIZE,
        "collision_rects": collision_rects,
        "spawn_point": {"x": spawn_x, "y": spawn_y},
        "interactables": interactables,
        "debug": {
            "run_artifacts_overview": "run_artifacts/overview.json",
            "llm_logs_dir": "llm_logs",
        },
    }

    save_manifest(session_id, manifest)
    _write_run_artifacts_overview(session_id, session_dir, art_assets, audio_assets)

    print(f"[PIPELINE] === COMPLETE === Session: {session_id}")
    print(f"[PIPELINE] Play at: /play/{session_id}\n")

    session_status[session_id] = {
        "status": "complete",
        "stage": "complete",
        "progress": 100,
        "message": "Your universe is ready!",
    }
