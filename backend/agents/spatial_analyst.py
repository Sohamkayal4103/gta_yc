"""Agent 1: Spatial Analyst — Analyzes room video to extract spatial layout.

Two-step process:
1. Describe the video in rich detail (like audio description for visually impaired)
2. Extract structured spatial JSON from the description + video
"""

import json
import asyncio
from collections import Counter
from google import genai
from google.genai import types
from backend.config import GEMINI_API_KEY, GEMINI_MODEL
from backend.utils.llm_logging import start_call, finish_call, log_file_upload

DESCRIBE_ROOM_PROMPT = """You are describing a room video for someone who cannot see it.
Describe EVERYTHING you observe in rich detail, as if creating an audio description
for a visually impaired person exploring this space:

Use this strict scan order:
1. Overall room first: shape, estimated dimensions, likely purpose.
2. Left wall sweep (from near side to far side): list every object in order.
3. Far wall sweep (left to right): list every object in order.
4. Right wall sweep (far side to near side): list every object in order.
5. Center area and walking paths.
6. Floor and ceiling details.
7. Lighting, doors, windows, and notable features.

For EVERY object you mention, include:
- Approximate physical size in hand spans and foot lengths.
- Approximate distance from the camera/viewpoint in foot lengths.
- Exact relative position (e.g., against left wall, near far-right corner, two feet from desk).
- Material, color, condition, and anything unusual.

Be extremely detailed and specific. This description will be used to recreate
this room as a game environment.
"""

DESCRIBE_SELFIE_PROMPT = """You are describing a person from a selfie video for a character artist.
Describe in rich detail:

1. Physical appearance: hair color/style, skin tone, facial features
2. Body type and build
3. What they're wearing: clothing colors, style, accessories
4. Their expression and vibe/energy
5. Any distinguishing features

Be specific and detailed. This description will be used to create a game character
sprite that resembles this person.
"""

SPATIAL_PROMPT = """You are analyzing a room to create a top-down 2D game map.

Here is a detailed description of the room:
{room_description}

Using this description AND the video, extract spatial information.

Output ONLY valid JSON matching this exact schema (no markdown, no code blocks):

{{
  "room_width_meters": <float estimated room width>,
  "room_height_meters": <float estimated room height>,
  "objects": [
    {{
      "name": "<descriptive name like desk, bed, bookshelf>",
      "object_type": "<furniture|electronics|decoration|storage|appliance>",
      "x_percent": <0.0-1.0 position from left wall>,
      "y_percent": <0.0-1.0 position from top wall (far wall)>,
      "width_percent": <0.0-1.0 fraction of room width>,
      "height_percent": <0.0-1.0 fraction of room depth>,
      "is_interactable": <true for 5-8 interesting objects, false for background>,
      "description": "<brief description of the object>"
    }}
  ],
  "walls": [
    {{"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 0.0}},
    {{"x1": 1.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}},
    {{"x1": 0.0, "y1": 1.0, "x2": 1.0, "y2": 1.0}},
    {{"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 1.0}}
  ],
  "door_positions": [{{"x_percent": <float>, "y_percent": <float>}}],
  "room_description": "<one sentence describing the room>",
  "lighting": "<bright|dim|natural|artificial>",
  "floor_type": "<hardwood|carpet|tile|concrete|other>"
}}

Rules:
- Estimate positions as percentages of room dimensions (0.0 = left/top, 1.0 = right/bottom)
- Include ALL visible objects (at least 8-12)
- Mark exactly 5-8 objects as is_interactable=true (these become game objectives)
- Always include 4 wall segments forming the room boundary
- Include at least 1 door position
"""

DIRECTION_ORDER = ("front", "left", "right", "back", "up", "down")

DIRECTION_HINTS = {
    "front": "User is at room center looking toward the front side.",
    "left": "User is at room center rotated left from front.",
    "right": "User is at room center rotated right from front.",
    "back": "User is at room center turned around from front.",
    "up": "User is at room center looking upward at ceiling/high fixtures.",
    "down": "User is at room center looking downward at floor/low fixtures.",
}


def _normalize_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in (value or "")).strip()


def _clamp_percent(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick_most_common(values: list[str], fallback: str) -> str:
    cleaned = [v for v in values if v]
    if not cleaned:
        return fallback
    return Counter(cleaned).most_common(1)[0][0]


def _build_directional_description_prompt(direction: str) -> str:
    direction_hint = DIRECTION_HINTS.get(direction, "")
    return (
        f"{DESCRIBE_ROOM_PROMPT}\n\n"
        f"Directional context:\n"
        f"- View direction: {direction.upper()}\n"
        f"- {direction_hint}\n"
        "- Prioritize what is visible from this direction.\n"
        "- Mention occlusions or hidden areas from this view.\n"
    )


def _ensure_minimum_interactables(layout: dict, minimum: int = 5) -> None:
    objects = layout.get("objects", [])
    interactable_count = sum(1 for obj in objects if obj.get("is_interactable"))
    if interactable_count >= minimum:
        return

    # Promote larger objects first for stability.
    promotable = sorted(
        [obj for obj in objects if not obj.get("is_interactable")],
        key=lambda obj: _to_float(obj.get("width_percent", 0.0), 0.0) * _to_float(obj.get("height_percent", 0.0), 0.0),
        reverse=True,
    )
    for obj in promotable:
        if interactable_count >= minimum:
            break
        obj["is_interactable"] = True
        interactable_count += 1


def _merge_view_layouts(view_layouts: dict[str, dict]) -> dict:
    if not view_layouts:
        raise RuntimeError("No room view layouts were provided for merge")

    widths = []
    heights = []
    lighting_values = []
    floor_values = []
    door_positions = []
    combined_descriptions = []

    object_acc: dict[str, dict] = {}

    for direction, layout in view_layouts.items():
        widths.append(_to_float(layout.get("room_width_meters", 5.0), 5.0))
        heights.append(_to_float(layout.get("room_height_meters", 5.0), 5.0))
        lighting_values.append(layout.get("lighting", ""))
        floor_values.append(layout.get("floor_type", ""))
        combined_descriptions.append(
            f"[{direction.upper()} VIEW]\n{layout.get('_room_description_detailed', '').strip()}"
        )

        for door in layout.get("door_positions", []):
            x = _clamp_percent(_to_float(door.get("x_percent", 0.5), 0.5))
            y = _clamp_percent(_to_float(door.get("y_percent", 0.5), 0.5))
            key = (round(x, 2), round(y, 2))
            door_positions.append({"key": key, "x_percent": x, "y_percent": y})

        for obj in layout.get("objects", []):
            name = (obj.get("name") or "").strip()
            if not name:
                continue
            key = _normalize_name(name)
            if not key:
                continue

            acc = object_acc.setdefault(
                key,
                {
                    "names": [],
                    "types": [],
                    "descriptions": [],
                    "x_sum": 0.0,
                    "y_sum": 0.0,
                    "w_sum": 0.0,
                    "h_sum": 0.0,
                    "count": 0,
                    "interactable_hits": 0,
                },
            )

            acc["names"].append(name)
            acc["types"].append(obj.get("object_type", "furniture"))
            acc["descriptions"].append(obj.get("description", ""))
            acc["x_sum"] += _clamp_percent(_to_float(obj.get("x_percent", 0.5), 0.5))
            acc["y_sum"] += _clamp_percent(_to_float(obj.get("y_percent", 0.5), 0.5))
            acc["w_sum"] += _clamp_percent(_to_float(obj.get("width_percent", 0.1), 0.1))
            acc["h_sum"] += _clamp_percent(_to_float(obj.get("height_percent", 0.1), 0.1))
            acc["count"] += 1
            if obj.get("is_interactable"):
                acc["interactable_hits"] += 1

    merged_objects = []
    for acc in object_acc.values():
        count = max(1, acc["count"])
        names = acc["names"] or ["object"]
        descriptions = [desc for desc in acc["descriptions"] if desc]
        merged_objects.append(
            {
                "name": Counter(names).most_common(1)[0][0],
                "object_type": _pick_most_common(acc["types"], "furniture"),
                "x_percent": _clamp_percent(acc["x_sum"] / count),
                "y_percent": _clamp_percent(acc["y_sum"] / count),
                "width_percent": max(0.03, _clamp_percent(acc["w_sum"] / count)),
                "height_percent": max(0.03, _clamp_percent(acc["h_sum"] / count)),
                "is_interactable": acc["interactable_hits"] > 0,
                "description": max(descriptions, key=len) if descriptions else "",
            }
        )

    merged_objects.sort(key=lambda obj: (obj["y_percent"], obj["x_percent"], obj["name"]))

    deduped_doors = []
    seen_doors = set()
    for door in door_positions:
        if door["key"] in seen_doors:
            continue
        seen_doors.add(door["key"])
        deduped_doors.append(
            {
                "x_percent": door["x_percent"],
                "y_percent": door["y_percent"],
            }
        )
    if not deduped_doors:
        deduped_doors = [{"x_percent": 0.5, "y_percent": 1.0}]

    first_layout = next(iter(view_layouts.values()))
    merged = {
        "room_width_meters": sum(widths) / len(widths) if widths else 5.0,
        "room_height_meters": sum(heights) / len(heights) if heights else 5.0,
        "objects": merged_objects,
        "walls": first_layout.get("walls") or [
            {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 0.0},
            {"x1": 1.0, "y1": 0.0, "x2": 1.0, "y2": 1.0},
            {"x1": 0.0, "y1": 1.0, "x2": 1.0, "y2": 1.0},
            {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 1.0},
        ],
        "door_positions": deduped_doors,
        "room_description": f"Merged multi-view room analysis from {len(view_layouts)} directional uploads.",
        "lighting": _pick_most_common(lighting_values, "natural"),
        "floor_type": _pick_most_common(floor_values, "other"),
        "_room_description_detailed": "\n\n".join(combined_descriptions).strip(),
        "_view_descriptions": {
            direction: layout.get("_room_description_detailed", "")
            for direction, layout in view_layouts.items()
        },
        "_view_layouts": {
            direction: {
                key: value
                for key, value in layout.items()
                if not key.startswith("_")
            }
            for direction, layout in view_layouts.items()
        },
    }

    _ensure_minimum_interactables(merged, minimum=5)
    return merged


def _delete_uploaded_file(client, file_name: str, session_id: str | None, operation: str):
    delete_ctx = start_call(
        session_id,
        "spatial_analyst",
        operation,
        {
            "api": "client.files.delete",
            "name": file_name,
        },
    )
    try:
        client.files.delete(name=file_name)
        finish_call(
            delete_ctx,
            response_payload={
                "api": "client.files.delete",
                "name": file_name,
                "deleted": True,
            },
        )
    except Exception as exc:
        finish_call(delete_ctx, error=exc)


async def _upload_and_wait(
    client,
    video_path: str,
    session_id: str | None = None,
    label: str = "video",
):
    """Upload a video and wait for processing."""
    print(f"[SPATIAL] Uploading video: {video_path}")

    upload_ctx = log_file_upload(
        session_id,
        "spatial_analyst",
        f"{label}_upload",
        video_path,
        metadata={"api": "client.files.upload", "label": label},
    )
    try:
        video_file = client.files.upload(file=video_path)
        finish_call(
            upload_ctx,
            response_payload={
                "api": "client.files.upload",
                "label": label,
                "response": video_file,
            },
        )
    except Exception as exc:
        finish_call(upload_ctx, error=exc)
        raise

    print(f"[SPATIAL] Upload complete, file name: {video_file.name}, state: {video_file.state.name}")

    while video_file.state.name == "PROCESSING":
        await asyncio.sleep(2)
        poll_ctx = start_call(
            session_id,
            "spatial_analyst",
            f"{label}_poll",
            {
                "api": "client.files.get",
                "label": label,
                "name": video_file.name,
            },
        )
        try:
            video_file = client.files.get(name=video_file.name)
            finish_call(
                poll_ctx,
                response_payload={
                    "api": "client.files.get",
                    "label": label,
                    "response": video_file,
                },
            )
        except Exception as exc:
            finish_call(poll_ctx, error=exc)
            raise

        print(f"[SPATIAL] File state: {video_file.state.name}")

    if video_file.state.name == "FAILED":
        raise RuntimeError("Video processing failed")

    return video_file


async def describe_video(
    video_path: str,
    prompt: str,
    label: str,
    session_id: str | None = None,
) -> str:
    """Ask Gemini to describe a video in detail."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    label_key = label.lower()
    video_file = await _upload_and_wait(client, video_path, session_id=session_id, label=label_key)

    print(f"[{label}] Asking Gemini to describe the video...")
    describe_ctx = start_call(
        session_id,
        "spatial_analyst",
        f"{label_key}_describe_generate_content",
        {
            "api": "client.models.generate_content",
            "model": GEMINI_MODEL,
            "contents": [
                {"type": "text", "text": prompt},
                {"type": "uploaded_file", "file_ref": video_file},
            ],
            "config": {
                "temperature": 0.3,
            },
        },
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, video_file],
            config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )
        finish_call(
            describe_ctx,
            response_payload={
                "api": "client.models.generate_content",
                "model": GEMINI_MODEL,
                "response": response,
            },
        )
    except Exception as exc:
        finish_call(describe_ctx, error=exc)
        raise

    description = response.text or ""
    print(f"[{label}] Description received ({len(description)} chars):")
    print(f"[{label}] --- START DESCRIPTION ---")
    print(description)
    print(f"[{label}] --- END DESCRIPTION ---")

    # Clean up
    _delete_uploaded_file(
        client,
        video_file.name,
        session_id=session_id,
        operation=f"{label_key}_delete_uploaded_file",
    )

    return description


async def _analyze_room_view(
    video_path: str,
    direction: str,
    session_id: str | None = None,
) -> dict:
    """Analyze one directional room video."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    direction_key = direction.lower()

    description_prompt = _build_directional_description_prompt(direction_key)
    room_description = await describe_video(
        video_path,
        description_prompt,
        f"ROOM_{direction_key.upper()}",
        session_id=session_id,
    )

    video_file = await _upload_and_wait(
        client,
        video_path,
        session_id=session_id,
        label=f"room_{direction_key}_spatial",
    )

    spatial_prompt = SPATIAL_PROMPT.format(
        room_description=(
            f"Directional context: {DIRECTION_HINTS.get(direction_key, direction_key)}\n\n"
            f"{room_description}"
        )
    )

    print(f"[SPATIAL] Extracting spatial JSON for direction={direction_key}...")
    spatial_ctx = start_call(
        session_id,
        "spatial_analyst",
        f"room_{direction_key}_spatial_generate_content",
        {
            "api": "client.models.generate_content",
            "model": GEMINI_MODEL,
            "contents": [
                {"type": "text", "text": spatial_prompt},
                {"type": "uploaded_file", "file_ref": video_file},
            ],
            "config": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
            "direction": direction_key,
        },
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[spatial_prompt, video_file],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        finish_call(
            spatial_ctx,
            response_payload={
                "api": "client.models.generate_content",
                "model": GEMINI_MODEL,
                "response": response,
                "direction": direction_key,
            },
        )
    except Exception as exc:
        finish_call(spatial_ctx, error=exc)
        raise

    response_text = response.text or ""
    print(f"[SPATIAL] Raw JSON response for {direction_key} ({len(response_text)} chars):")
    print(response_text[:500])

    if not response_text:
        raise RuntimeError(f"Spatial JSON response was empty for direction={direction_key}")

    result = json.loads(response_text)
    result["_room_description_detailed"] = room_description
    result["_direction"] = direction_key
    _ensure_minimum_interactables(result, minimum=5)

    obj_count = len(result.get("objects", []))
    interactable_count = sum(1 for obj in result.get("objects", []) if obj.get("is_interactable"))
    print(f"[SPATIAL] Parsed direction={direction_key}: {obj_count} objects, {interactable_count} interactable")

    _delete_uploaded_file(
        client,
        video_file.name,
        session_id=session_id,
        operation=f"room_{direction_key}_spatial_delete_uploaded_file",
    )

    return result


async def analyze_room(room_input: str | dict[str, str], session_id: str | None = None) -> dict:
    """Analyze room using single or multi-view videos."""
    if isinstance(room_input, str):
        return await _analyze_room_view(room_input, "front", session_id=session_id)

    room_views = {
        direction: path
        for direction, path in room_input.items()
        if direction in DIRECTION_ORDER and path
    }
    if not room_views:
        raise RuntimeError("No room videos were provided for spatial analysis")

    view_layouts: dict[str, dict] = {}
    for direction in DIRECTION_ORDER:
        path = room_views.get(direction)
        if not path:
            continue
        view_layouts[direction] = await _analyze_room_view(path, direction, session_id=session_id)

    if len(view_layouts) == 1:
        only_direction = next(iter(view_layouts.keys()))
        print(f"[SPATIAL] Single view provided ({only_direction}); using direct layout.")
        return view_layouts[only_direction]

    print(f"[SPATIAL] Merging {len(view_layouts)} directional analyses into one room layout...")
    return _merge_view_layouts(view_layouts)


async def describe_selfie(selfie_path: str, session_id: str | None = None) -> str:
    """Get a detailed description of the person in the selfie video."""
    return await describe_video(
        selfie_path,
        DESCRIBE_SELFIE_PROMPT,
        "SELFIE",
        session_id=session_id,
    )
