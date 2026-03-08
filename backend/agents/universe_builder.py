"""Agent: Universe Builder — Analyzes 6 directional room images and generates
a JSON scene description for Three.js rendering.

Two-step process:
1. Upload all images to Gemini and get rich spatial descriptions
2. Ask Gemini to generate a JSON scene description based on the analysis
"""

import asyncio
import json
import re
from google import genai
from google.genai import types
from backend.config import GEMINI_API_KEY, GEMINI_MODEL
from backend.utils.llm_logging import start_call, finish_call, log_file_upload

DIRECTION_ORDER = ("front", "back", "left", "right", "up", "down")

DIRECTION_HINTS = {
    "front": "User is at room center looking toward the front wall.",
    "back": "User is at room center turned 180 degrees from front.",
    "left": "User is at room center rotated left from front.",
    "right": "User is at room center rotated right from front.",
    "up": "User is at room center looking straight up at the ceiling.",
    "down": "User is at room center looking straight down at the floor.",
}

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

# ── Step 1 prompt: rich spatial description per image ──────────────────────

DESCRIBE_DIRECTION_PROMPT = """You are describing a room photo for someone who cannot see it, as if
creating a spatial audio description for a visually impaired person exploring this space.

The viewer is standing in the CENTER of the room looking in the {direction} direction.
{direction_hint}

Describe EVERYTHING you observe in rich detail using this scan order:
1. Overall impression: what is directly ahead, how far away is the wall/boundary.
2. Objects from LEFT to RIGHT in this view: name, size (in feet/inches), distance from center,
   material, color, condition.
3. Objects from FLOOR to CEILING: anything on the ground, at desk height, at eye level, above.
4. Lighting visible from this angle.
5. Any doorways, windows, or openings.
6. Floor and ceiling details visible.
7. EDGE OVERLAP: Carefully describe what is visible at the LEFT EDGE and RIGHT EDGE of this photo.
   These edges overlap with adjacent direction photos. For example, the left edge of the FRONT photo
   overlaps with the right edge of the LEFT photo. Describe any objects or features that span these
   edges so we can properly stitch the scene together.

For EVERY object, include:
- Approximate physical size (width x height x depth in feet)
- Approximate distance from the center of the room
- Exact relative position (e.g., "against the left wall, 3 feet from the corner")
- Material, color, and any distinguishing features

Be extremely detailed and specific. This description will be used to recreate
this room as a 3D navigable universe.
"""

# ── Step 2 prompt: generate JSON scene from all descriptions ─────────────

GENERATE_SCENE_JSON_PROMPT = """You are an expert 3D spatial analyst. Given 6 directional photo descriptions of a room taken from the center, generate a precise JSON scene description.

{all_descriptions}

TASK: Analyze ALL descriptions and output a JSON object describing the room for a Three.js renderer.

CRITICAL — EDGE OVERLAP DEDUPLICATION:
Adjacent photos overlap at their edges. The left edge of the FRONT photo shows the same objects as
the right edge of the LEFT photo (that's the front-left corner). Use these overlaps to:
1. DEDUPLICATE: If the same object appears in two adjacent views, place it ONCE at the correct corner/edge position.
2. CONFIRM POSITIONS: Overlapping objects confirm where corners are. A desk visible at the left edge
   of FRONT and right edge of LEFT is at the front-left corner (negative X, negative Z).
3. ADJACENCY MAP:
   - FRONT left edge  ↔ LEFT right edge   (front-left corner, -X, -Z)
   - FRONT right edge ↔ RIGHT left edge   (front-right corner, +X, -Z)
   - BACK left edge   ↔ RIGHT right edge  (back-right corner, +X, +Z)
   - BACK right edge  ↔ LEFT left edge    (back-left corner, -X, +Z)

JSON SCHEMA (follow exactly):
{{
  "room": {{
    "width": <number in meters — make sure this is realistic, typical rooms are 4-8m>,
    "depth": <number in meters — make sure this is realistic, typical rooms are 4-8m>,
    "height": <number in meters — typical ceiling 2.4-3.5m>,
    "floor_color": "<hex color>",
    "wall_color": "<hex color>",
    "ceiling_color": "<hex color>"
  }},
  "lights": [
    {{ "type": "ambient", "color": "<hex>", "intensity": <0-1> }},
    {{ "type": "point", "color": "<hex>", "intensity": <0-2>, "position": [x, y, z] }},
    {{ "type": "directional", "color": "<hex>", "intensity": <0-2>, "position": [x, y, z] }}
  ],
  "objects": [
    {{
      "name": "<descriptive name>",
      "shape": "box" | "sphere" | "cylinder" | "plane",
      "position": [x, y, z],
      "size": [width, height, depth],
      "rotation": [rx, ry, rz],
      "color": "<hex color>",
      "material": "wood" | "metal" | "plastic" | "fabric" | "glass" | "concrete" | "default",
      "roughness": <0-1>,
      "metalness": <0-1>,
      "interaction": "none" | "sit" | "write" | "use" | "open" | "toggle",
      "asset_ref": "<optional canonical asset id/path>",
      "asset_variant": "<optional skin/variant tag>",
      "material_slots": ["<optional material slot names>"],
      "collider_type": "none" | "box" | "sphere" | "capsule" | "mesh",
      "nav_blocker": <true|false|null>,
      "interaction_anchor": {{"x": <number>, "y": <number>, "z": <number>}},
      "animation_profile": "<optional animation profile id>",
      "audio_profile": "<optional audio profile id>",
      "lod_group": "<optional lod group id>",
      "spawn_tags": ["<optional spawn tags>"],
      "children": [ ... same object schema ... ]
    }}
  ],
  "people": [
    {{
      "name": "<identifier>",
      "position": [x, 0, z],
      "pose": "standing" | "sitting",
      "facing": <degrees 0-360>,
      "height": <meters>,
      "shirt_color": "<hex>",
      "pants_color": "<hex>",
      "skin_color": "<hex>"
    }}
  ]
}}

COORDINATE SYSTEM:
- Y is up. Floor is at y=0.
- Object positions are the CENTER of the object.
- For objects on the floor, position.y = height/2.
- Room center is (0, 0, 0). Front is -Z, back is +Z, left is -X, right is +X.

ACCURACY REQUIREMENTS:
- Place objects EXACTLY where described. Use distances from descriptions.
- Convert feet to meters (1 ft = 0.3048 m).
- Match colors from descriptions as closely as possible.
- Include ALL objects mentioned across all 6 views — but DEDUPLICATE objects at edges.
- Use appropriate roughness/metalness: wood (0.7/0.1), metal (0.3/0.8), plastic (0.5/0.2), fabric (0.9/0.0), glass (0.1/0.5).
- Room dimensions MUST be realistic. Standard rooms: 4-8m wide, 4-8m deep, 2.4-3.5m ceiling. Err larger.

INTERACTION TYPES — assign to each object:
- "sit": chairs, couches, sofas, benches, stools
- "write": whiteboards, blackboards, chalkboards, dry-erase boards
- "use": laptops, monitors, computers, TVs, microwaves, printers, phones, coffee machines, any electronic device
- "open": doors, cabinets, drawers, fridges, closets
- "toggle": light switches, lamps, fans
- "none": walls, structural elements, shelves (non-interactive), decorations

OUTPUT: Return ONLY the raw JSON. No markdown fences, no explanation.
"""


ENRICH_SCENE_PROMPT = """You are enriching a 3D scene with imaginative details. Given the scene JSON below, generate additional details that aren't visible in photos but would make the scene feel real and interactive.

SCENE JSON:
{scene_json}

Generate a JSON object with these keys:

1. "door_reveals": For each door/closet object, imagine what's behind it:
   - "object_name": exact name from scene
   - "room_type": e.g. "bathroom", "closet", "hallway", "bedroom"
   - "floor_color": hex color
   - "wall_color": hex color
   - "visible_objects": array of 1-3 objects visible inside, each with name, shape (box/sphere/cylinder), color (hex), size [w,h,d] in meters, offset [x,y,z] relative to door center

2. "container_contents": For suitcases, cabinets, drawers — imagine items inside:
   - "object_name": exact name from scene
   - "items": array of 2-4 items, each with name, shape, color (hex), size [w,h,d] in meters, offset [x,y,z] inside container

3. "person_details": For each person, add physical features:
   - "person_name": exact name from scene
   - "hair_style": "short" | "long" | "bald"
   - "hair_color": hex color
   - "eye_color": hex color
   - "facial_hair": "none" | "beard" | "mustache" | "goatee"
   - "shoe_color": hex color
   - "gender_presentation": "masculine" | "feminine" | "neutral"

4. "object_details": For interesting objects, add sub-type info:
   - "object_name": exact name from scene
   - "sub_type": e.g. "rolling_suitcase", "french_door", "potted_fern"
   - "accent_color": hex color for trim/accent
   - "texture_hint": e.g. "leather", "woven", "glossy"

Return ONLY valid JSON. No markdown fences, no explanation.
"""


async def _enrich_scene(
    client, scene: dict, session_id: str = None, log=None,
) -> dict:
    """Make a second Gemini call to enrich the scene with imagined details."""
    if log is None:
        log = _noop_log
    scene_json = json.dumps(scene, indent=2)
    prompt = ENRICH_SCENE_PROMPT.format(scene_json=scene_json)

    log("Enriching scene with imagined details...")
    ctx = start_call(
        session_id, "universe_builder", "enrich_scene",
        {"model": GEMINI_MODEL, "prompt_length": len(prompt)},
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.7),
        )
        finish_call(ctx, response_payload={"response": response})
    except Exception as exc:
        finish_call(ctx, error=exc)
        log(f"Enrichment failed: {exc}")
        return {}

    raw_text = response.text or ""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines)
    raw_text = raw_text.strip()

    try:
        enrichment = json.loads(raw_text)
        log(f"Enrichment: {len(enrichment.get('door_reveals', []))} doors, "
            f"{len(enrichment.get('container_contents', []))} containers, "
            f"{len(enrichment.get('person_details', []))} people, "
            f"{len(enrichment.get('object_details', []))} objects")
        return enrichment
    except json.JSONDecodeError as exc:
        log(f"Failed to parse enrichment JSON: {exc}")
        return {}


def _noop_log(msg: str):
    print(f"[UNIVERSE] {msg}")


def _apply_runtime_metadata_defaults(obj: dict):
    for key, value in DEFAULT_RUNTIME_METADATA.items():
        if key not in obj:
            if isinstance(value, list):
                obj[key] = list(value)
            elif isinstance(value, dict):
                obj[key] = dict(value)
            else:
                obj[key] = value


def _apply_runtime_metadata_defaults_recursive(objects: list[dict]):
    for obj in objects:
        _apply_runtime_metadata_defaults(obj)
        children = obj.get("children") or []
        if isinstance(children, list):
            _apply_runtime_metadata_defaults_recursive(children)


async def _upload_and_wait(client, file_path: str, session_id: str = None, label: str = "image", log=_noop_log):
    """Upload a file to Gemini Files API and wait for processing."""
    log(f"Uploading file: {file_path}")

    upload_ctx = log_file_upload(
        session_id, "universe_builder", f"{label}_upload", file_path,
        metadata={"api": "client.files.upload", "label": label},
    )
    try:
        uploaded_file = client.files.upload(file=file_path)
        finish_call(upload_ctx, response_payload={
            "api": "client.files.upload", "label": label, "response": uploaded_file,
        })
    except Exception as exc:
        finish_call(upload_ctx, error=exc)
        raise

    log(f"Upload complete: {uploaded_file.name}, state: {uploaded_file.state.name}")

    while uploaded_file.state.name == "PROCESSING":
        await asyncio.sleep(2)
        poll_ctx = start_call(
            session_id, "universe_builder", f"{label}_poll",
            {"api": "client.files.get", "name": uploaded_file.name},
        )
        try:
            uploaded_file = client.files.get(name=uploaded_file.name)
            finish_call(poll_ctx, response_payload={"response": uploaded_file})
        except Exception as exc:
            finish_call(poll_ctx, error=exc)
            raise
        log(f"File state: {uploaded_file.state.name}")

    if uploaded_file.state.name == "FAILED":
        raise RuntimeError(f"File processing failed for {label}")

    return uploaded_file


def _delete_uploaded_file(client, file_name: str, session_id: str = None, operation: str = "delete"):
    """Clean up uploaded file from Gemini."""
    ctx = start_call(session_id, "universe_builder", operation, {"name": file_name})
    try:
        client.files.delete(name=file_name)
        finish_call(ctx, response_payload={"deleted": True})
    except Exception as exc:
        finish_call(ctx, error=exc)


async def _describe_direction(
    client, file_path: str, direction: str, session_id: str = None, log=_noop_log,
) -> tuple[str, str]:
    """Upload one directional image, get a rich description, return (direction, description)."""
    label = f"room_{direction}"
    uploaded_file = await _upload_and_wait(client, file_path, session_id=session_id, label=label, log=log)

    prompt = DESCRIBE_DIRECTION_PROMPT.format(
        direction=direction.upper(),
        direction_hint=DIRECTION_HINTS.get(direction, ""),
    )

    log(f"Describing {direction} view...")
    ctx = start_call(
        session_id, "universe_builder", f"{label}_describe",
        {"model": GEMINI_MODEL, "direction": direction},
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, uploaded_file],
            config=types.GenerateContentConfig(temperature=0.3),
        )
        finish_call(ctx, response_payload={"response": response, "direction": direction})
    except Exception as exc:
        finish_call(ctx, error=exc)
        raise

    description = response.text or ""
    log(f"{direction} description: {len(description)} chars")

    # Cleanup
    _delete_uploaded_file(client, uploaded_file.name, session_id, f"{label}_delete")

    return direction, description


async def _generate_scene_json(
    client, all_descriptions: str, session_id: str = None, log=_noop_log,
) -> dict:
    """Send combined descriptions to Gemini and get JSON scene back."""
    prompt = GENERATE_SCENE_JSON_PROMPT.format(all_descriptions=all_descriptions)

    log(f"Generating scene JSON from {len(all_descriptions)} chars of descriptions...")
    ctx = start_call(
        session_id, "universe_builder", "generate_scene_json",
        {"model": GEMINI_MODEL, "prompt_length": len(prompt)},
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.4),
        )
        finish_call(ctx, response_payload={"response": response})
    except Exception as exc:
        finish_call(ctx, error=exc)
        raise

    raw_text = response.text or ""

    # Strip markdown code fences if present
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines)

    raw_text = raw_text.strip()
    log(f"Raw JSON text: {len(raw_text)} chars")

    # Parse JSON
    scene = json.loads(raw_text)
    log(f"Parsed scene: {len(scene.get('objects', []))} objects, {len(scene.get('people', []))} people")

    # Basic validation
    if "room" not in scene:
        raise ValueError("Scene JSON missing 'room' key")
    if "objects" not in scene:
        scene["objects"] = []
    if "lights" not in scene:
        scene["lights"] = [{"type": "ambient", "color": "#ffffff", "intensity": 0.6}]
    if "people" not in scene:
        scene["people"] = []

    _apply_runtime_metadata_defaults_recursive(scene["objects"])

    return scene


async def build_universe(
    room_views: dict[str, str],
    session_id: str = None,
    on_progress=None,
    on_log=None,
) -> dict:
    """Main entry point: analyze 6 directional images and generate JSON scene.

    Args:
        room_views: dict mapping direction -> image file path
        session_id: optional session ID for logging
        on_progress: optional callback(stage, progress, message)
        on_log: optional callback(message) for debug logging

    Returns:
        dict with keys: scene (JSON dict), descriptions (raw text for debug)
    """
    log = on_log or _noop_log
    client = genai.Client(api_key=GEMINI_API_KEY)

    log("Initializing Gemini client...")
    if on_progress:
        on_progress("spatial_analysis", 10, "Uploading and analyzing room images...")

    # Step 1: Describe each direction sequentially (Gemini Files API rate limits)
    descriptions = {}
    total_views = len(room_views)
    for i, direction in enumerate(DIRECTION_ORDER):
        path = room_views.get(direction)
        if not path:
            continue
        dir_name, description = await _describe_direction(
            client, path, direction, session_id=session_id, log=log,
        )
        descriptions[dir_name] = description

        if on_progress:
            progress = 10 + int(60 * (i + 1) / total_views)
            on_progress(
                "spatial_analysis", progress,
                f"Analyzed {dir_name} view ({i + 1}/{total_views})...",
            )

    # Combine all descriptions
    all_descriptions = "\n\n".join(
        f"=== {direction.upper()} VIEW ===\n{desc}"
        for direction, desc in descriptions.items()
    )

    if on_progress:
        on_progress("generating_universe", 75, "Generating 3D universe from spatial data...")

    # Step 2: Generate JSON scene
    scene = await _generate_scene_json(client, all_descriptions, session_id=session_id, log=log)

    if on_progress:
        on_progress("enriching_scene", 85, "Adding imagined details to scene...")

    # Step 3: Enrich scene with imagined details
    enrichment = await _enrich_scene(client, scene, session_id=session_id, log=log)
    if enrichment:
        scene["enrichment"] = enrichment

    if on_progress:
        on_progress("complete", 100, "3D Universe generated!")

    return {
        "scene": scene,
        "descriptions": all_descriptions,
    }
