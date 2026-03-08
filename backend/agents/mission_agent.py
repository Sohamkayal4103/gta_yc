"""Agent 2: Mission Agent — Generates GTA-style missions from room layout."""

import json
from google import genai
from google.genai import types
from backend.config import GEMINI_API_KEY, GEMINI_MODEL
from backend.utils.llm_logging import start_call, finish_call

GENRE_CONTEXTS = {
    "fantasy": {
        "setting": "a medieval fantasy dungeon/castle",
        "role": "a brave adventurer",
        "flavor": "Use medieval fantasy language. Objects become magical artifacts, enchanted items, ancient relics.",
        "transforms": {
            "desk": "enchanting table",
            "bookshelf": "ancient tome repository",
            "couch": "throne of rest",
            "lamp": "magical orb",
            "door": "portal gate",
            "window": "crystal viewport",
            "chair": "stone seat",
            "tv": "scrying mirror",
            "bed": "resting quarters",
            "table": "war planning table",
            "closet": "armory chest",
            "plant": "enchanted flora",
        }
    },
    "cyberpunk": {
        "setting": "a neon-lit cyberpunk safehouse in a dystopian megacity",
        "role": "a rogue hacker/mercenary",
        "flavor": "Use cyberpunk slang and tech jargon. Objects become tech, terminals, and gear.",
        "transforms": {
            "desk": "hacking terminal",
            "bookshelf": "data archive rack",
            "couch": "neural recovery pod",
            "lamp": "holographic projector",
            "door": "blast door",
            "window": "reinforced viewport",
            "chair": "command seat",
            "tv": "surveillance feed",
            "bed": "cryo-recovery unit",
            "table": "ops table",
            "closet": "weapons cache",
            "plant": "bio-filter unit",
        }
    },
    "horror": {
        "setting": "an abandoned building with dark secrets",
        "role": "a survivor trying to escape",
        "flavor": "Use tense, creepy language. Objects hide dangers and clues. Everything feels wrong.",
        "transforms": {
            "desk": "blood-stained desk",
            "bookshelf": "dusty bookcase (something moves behind it)",
            "couch": "torn, decaying couch",
            "lamp": "flickering light source",
            "door": "barricaded exit",
            "window": "boarded-up window",
            "chair": "overturned chair",
            "tv": "static-filled screen",
            "bed": "disturbed resting place",
            "table": "examination table",
            "closet": "locked storage (scratching inside)",
            "plant": "withered growth",
        }
    }
}

MISSION_PROMPT = """You are a GTA-style mission designer for a {genre} top-down game.

The player is {role} in {setting}.

Here is the room layout with real objects that exist in the game world:
{room_layout}

{flavor}

Generate exactly 3 missions that chain together into a story arc. Each mission must reference
REAL objects from the room layout above as interaction targets.

Object name transformations for this genre:
{transforms}

Output ONLY valid JSON (no markdown, no code blocks):

{{
  "missions": [
    {{
      "id": "mission_1",
      "title": "<catchy mission title, 3-6 words>",
      "description": "<1-2 sentence mission briefing>",
      "genre_flavor": "<atmospheric description of what the player sees>",
      "steps": [
        {{
          "instruction": "<what the player must do>",
          "target_object": "<exact name of an object from the room>",
          "action": "go_to|interact|collect|talk_to",
          "dialogue": "<what is said/shown when this step completes>"
        }}
      ],
      "reward_text": "<what the player receives or unlocks>",
      "npc_name": "<name of an NPC associated with this mission, or null>"
    }}
  ],
  "npcs": [
    {{
      "name": "<NPC name>",
      "personality": "<brief personality>",
      "x_percent": <0.0-1.0>,
      "y_percent": <0.0-1.0>,
      "dialogue_lines": ["<greeting>", "<hint>", "<farewell>"]
    }}
  ]
}}

Rules:
- Each mission has 2-4 steps
- Steps MUST reference objects that exist in the room layout
- Use the genre-transformed object names in dialogue/descriptions
- Missions should escalate in tension: mission 1 = exploration, mission 2 = discovery, mission 3 = climax
- Create 1-2 NPCs placed near interactable objects
- Make the dialogue feel like a real game, not generic AI output
"""


async def generate_missions(room_layout: dict, genre: str, session_id: str | None = None) -> dict:
    """Generate contextual missions based on room layout and genre."""
    ctx = GENRE_CONTEXTS[genre]

    # Build object list with transforms
    objects = room_layout.get("objects", [])
    interactable_objects = [o for o in objects if o.get("is_interactable")]
    object_names = [o["name"] for o in interactable_objects]

    transform_text = "\n".join(
        f"  {k} → {v}" for k, v in ctx["transforms"].items()
        if any(k in name.lower() for name in object_names)
    )
    if not transform_text:
        transform_text = "\n".join(f"  {k} → {v}" for k, v in list(ctx["transforms"].items())[:5])

    prompt = MISSION_PROMPT.format(
        genre=genre,
        role=ctx["role"],
        setting=ctx["setting"],
        room_layout=json.dumps(room_layout, indent=2),
        flavor=ctx["flavor"],
        transforms=transform_text,
    )

    client = genai.Client(api_key=GEMINI_API_KEY)

    llm_ctx = start_call(
        session_id,
        "mission_agent",
        "generate_missions",
        {
            "api": "client.models.generate_content",
            "model": GEMINI_MODEL,
            "contents": [{"type": "text", "text": prompt}],
            "config": {
                "response_mime_type": "application/json",
                "temperature": 0.7,
            },
            "genre": genre,
        },
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
        finish_call(
            llm_ctx,
            response_payload={
                "api": "client.models.generate_content",
                "model": GEMINI_MODEL,
                "response": response,
            },
        )
    except Exception as exc:
        finish_call(llm_ctx, error=exc)
        raise

    result = json.loads(response.text)

    # Add genre-transformed game_names to room objects
    for obj in room_layout.get("objects", []):
        name_lower = obj["name"].lower()
        for key, transformed in ctx["transforms"].items():
            if key in name_lower:
                obj["game_name"] = transformed
                break
        if "game_name" not in obj:
            obj["game_name"] = f"{genre} {obj['name']}"

    return result
