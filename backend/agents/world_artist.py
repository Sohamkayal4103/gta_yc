"""Agent 3: World & Character Artist — Generates game map and character sprites.

Uses Nano Banana image generation via NANOBANANA_MODEL.
Same API key as Gemini, different model name.
"""

import os
import asyncio
from google import genai
from google.genai import types
from PIL import Image as PILImage
from backend.config import GEMINI_API_KEY, NANOBANANA_MODEL, MAP_SIZE, FALLBACKS_DIR
from backend.utils.video_processing import extract_frames
from backend.utils.llm_logging import start_call, finish_call

GENRE_STYLES = {
    "fantasy": {
        "map_style": "medieval fantasy dungeon with stone floors, magical glowing runes, torchlight ambiance, wooden furniture transformed into enchanted versions, warm golden and purple lighting",
        "character_style": "fantasy RPG warrior/mage with medieval armor or robes",
        "palette": "warm golds, deep purples, stone grays, magical greens",
    },
    "cyberpunk": {
        "map_style": "neon-lit cyberpunk interior with dark metallic surfaces, holographic displays, glowing circuit patterns on floors, futuristic tech versions of furniture, cyan and magenta neon lighting",
        "character_style": "cyberpunk hacker/mercenary with tech augmentations, neon accents",
        "palette": "neon cyan, hot magenta, dark chrome, electric blue",
    },
    "horror": {
        "map_style": "abandoned horror interior with decayed textures, blood stains, flickering dim lights, broken and distorted furniture, dark shadows, eerie green/red accents",
        "character_style": "horror survivor with torn clothes, flashlight, scared expression",
        "palette": "dark grays, blood reds, sickly greens, pitch black shadows",
    }
}

MAP_PROMPT = """Create a top-down bird's eye view game map image.
Style: {style}
Color palette: {palette}

Here is a detailed description of the real room this map is based on:
{room_description}

The room contains these objects at these positions (percentages of room size):
{object_list}

Requirements:
- Perfectly top-down perspective, looking straight down from above
- Square image
- Rich detailed textures for floor and all objects
- Clear visual distinction between walkable floor and furniture/obstacles
- Game-ready aesthetic similar to classic top-down RPGs
- Objects should be positioned approximately matching the given percentages
- Include walls around the room edges
- Floor type: {floor_type}
- Lighting mood: {lighting}
"""

CHARACTER_PROMPT = """Create a 2D top-down game character sprite.
Style: {style}

Here is a detailed description of the real person this character is based on:
{selfie_description}

The character should resemble this person but styled for a {genre} game.

Requirements:
- Top-down perspective (looking down at the character from above)
- Character facing downward (default walking direction)
- 64x64 pixels, clean pixel art style
- Transparent background
- {genre} themed outfit/equipment matching the person's build and appearance
- Clear, recognizable silhouette
"""

NPC_PROMPT = """Create a 2D top-down game NPC character sprite.
Style: {style}
Character: {npc_name} - {personality}

Requirements:
- Top-down perspective (looking down from above)
- 64x64 pixels, clean pixel art style
- Transparent background
- {genre} themed appearance
- Distinct from the player character
"""


def _get_client():
    return genai.Client(api_key=GEMINI_API_KEY)


async def generate_map(
    room_layout: dict,
    genre: str,
    session_dir: str,
    room_description: str = "",
    session_id: str | None = None,
) -> str:
    """Generate the top-down game map image using NanoBanana 2."""
    style = GENRE_STYLES[genre]
    objects = room_layout.get("objects", [])

    object_list = "\n".join(
        f"- {obj['name']}: at ({obj['x_percent']:.0%}, {obj['y_percent']:.0%}), "
        f"size ({obj['width_percent']:.0%} x {obj['height_percent']:.0%})"
        + (" [INTERACTABLE - should glow/highlight]" if obj.get("is_interactable") else "")
        for obj in objects
    )

    prompt = MAP_PROMPT.format(
        style=style["map_style"],
        palette=style["palette"],
        object_list=object_list,
        map_size=MAP_SIZE,
        floor_type=room_layout.get("floor_type", "hardwood"),
        lighting=room_layout.get("lighting", "dim"),
        room_description=room_description[:1000] if room_description else "A standard room",
    )

    map_path = os.path.join(session_dir, "map.png")

    try:
        print(f"[MAP] Generating map with model={NANOBANANA_MODEL}")
        print(f"[MAP] Prompt length: {len(prompt)} chars")
        client = _get_client()
        map_ctx = start_call(
            session_id,
            "world_artist",
            "generate_map",
            {
                "api": "client.models.generate_content",
                "model": NANOBANANA_MODEL,
                "contents": [{"type": "text", "text": prompt}],
                "config": {"response_modalities": ["TEXT", "IMAGE"]},
                "genre": genre,
            },
        )
        try:
            response = client.models.generate_content(
                model=NANOBANANA_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            finish_call(
                map_ctx,
                response_payload={
                    "api": "client.models.generate_content",
                    "model": NANOBANANA_MODEL,
                    "response": response,
                },
            )
        except Exception as exc:
            finish_call(map_ctx, error=exc)
            raise

        print(f"[MAP] Response received. Candidates: {len(response.candidates) if response.candidates else 0}")
        print(f"[MAP] Parts count: {len(response.parts) if response.parts else 0}")

        # Save generated image
        for i, part in enumerate(response.parts):
            print(f"[MAP] Part {i}: text={part.text is not None}, inline_data={part.inline_data is not None}")
            if part.text is not None:
                print(f"[MAP] Text content: {part.text[:200]}")
            if part.inline_data is not None:
                print(f"[MAP] Image mime: {part.inline_data.mime_type}, data_len: {len(part.inline_data.data)}")
                image = part.as_image()
                image.save(map_path)
                print(f"[MAP] Saved to {map_path}")
                return "map.png"

        raise RuntimeError("No image part found in response")
    except Exception as e:
        import traceback
        print(f"[MAP] FAILED: {e}")
        traceback.print_exc()
        return _use_fallback_map(genre, session_dir)


async def generate_character(
    selfie_path: str,
    genre: str,
    session_dir: str,
    selfie_description: str = "",
    session_id: str | None = None,
) -> str:
    """Generate the player character sprite from a selfie using NanoBanana 2."""
    style = GENRE_STYLES[genre]

    prompt = CHARACTER_PROMPT.format(
        style=style["character_style"],
        selfie_description=selfie_description[:1200] if selfie_description else "No selfie description available.",
        genre=genre,
    )

    player_path = os.path.join(session_dir, "player.png")

    try:
        # Extract a frame from selfie video
        frames_dir = os.path.join(session_dir, "selfie_frames")
        frames = extract_frames(selfie_path, frames_dir, num_frames=1)
        print(f"[CHAR] Extracted {len(frames)} selfie frames")

        contents = [prompt]
        request_images = []
        if frames:
            selfie_image = PILImage.open(frames[0])
            contents.append(selfie_image)
            with open(frames[0], "rb") as f:
                request_images.append(
                    {
                        "path": frames[0],
                        "mime_type": "image/jpeg",
                        "bytes": f.read(),
                    }
                )
            print(f"[CHAR] Selfie image size: {selfie_image.size}")

        print(f"[CHAR] Generating character with model={NANOBANANA_MODEL}")
        client = _get_client()
        char_ctx = start_call(
            session_id,
            "world_artist",
            "generate_character",
            {
                "api": "client.models.generate_content",
                "model": NANOBANANA_MODEL,
                "contents": [
                    {"type": "text", "text": prompt},
                    *request_images,
                ],
                "config": {"response_modalities": ["TEXT", "IMAGE"]},
                "genre": genre,
            },
        )
        try:
            response = client.models.generate_content(
                model=NANOBANANA_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            finish_call(
                char_ctx,
                response_payload={
                    "api": "client.models.generate_content",
                    "model": NANOBANANA_MODEL,
                    "response": response,
                },
            )
        except Exception as exc:
            finish_call(char_ctx, error=exc)
            raise

        print(f"[CHAR] Response parts: {len(response.parts) if response.parts else 0}")
        for i, part in enumerate(response.parts):
            print(f"[CHAR] Part {i}: text={part.text is not None}, inline_data={part.inline_data is not None}")
            if part.inline_data is not None:
                print(f"[CHAR] Image data_len: {len(part.inline_data.data)}")
                image = part.as_image()
                image.save(player_path)
                print(f"[CHAR] Saved player sprite")
                return "player.png"

        raise RuntimeError("No image in response")
    except Exception as e:
        import traceback
        print(f"[CHAR] FAILED: {e}")
        traceback.print_exc()
        return _use_fallback_sprite("player", session_dir)


async def generate_npcs(
    npcs: list,
    genre: str,
    session_dir: str,
    session_id: str | None = None,
) -> list[str]:
    """Generate NPC sprites using NanoBanana 2."""
    style = GENRE_STYLES[genre]
    npc_files = []

    for i, npc in enumerate(npcs[:3]):  # Max 3 NPCs
        filename = f"npc_{i}.png"
        npc_path = os.path.join(session_dir, filename)

        try:
            prompt = NPC_PROMPT.format(
                style=style["character_style"],
                npc_name=npc.get("name", f"NPC {i}"),
                personality=npc.get("personality", "mysterious"),
                genre=genre,
            )

            client = _get_client()
            npc_ctx = start_call(
                session_id,
                "world_artist",
                f"generate_npc_{i}",
                {
                    "api": "client.models.generate_content",
                    "model": NANOBANANA_MODEL,
                    "contents": [{"type": "text", "text": prompt}],
                    "config": {"response_modalities": ["TEXT", "IMAGE"]},
                    "genre": genre,
                    "npc_name": npc.get("name", f"NPC {i}"),
                },
            )
            try:
                response = client.models.generate_content(
                    model=NANOBANANA_MODEL,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                finish_call(
                    npc_ctx,
                    response_payload={
                        "api": "client.models.generate_content",
                        "model": NANOBANANA_MODEL,
                        "response": response,
                    },
                )
            except Exception as exc:
                finish_call(npc_ctx, error=exc)
                raise

            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    image.save(npc_path)
                    npc_files.append(filename)
                    break
        except Exception as e:
            print(f"NPC {i} generation failed: {e}")
            fallback = _use_fallback_sprite(f"npc_{i}", session_dir)
            npc_files.append(fallback)

    return npc_files


async def generate_all_art(
    room_layout: dict,
    selfie_path: str,
    genre: str,
    npcs: list,
    session_dir: str,
    room_description: str = "",
    selfie_description: str = "",
    session_id: str | None = None,
) -> dict:
    """Generate all art assets in parallel where possible."""
    map_task = generate_map(
        room_layout,
        genre,
        session_dir,
        room_description=room_description,
        session_id=session_id,
    )
    char_task = generate_character(
        selfie_path,
        genre,
        session_dir,
        selfie_description=selfie_description,
        session_id=session_id,
    )
    npc_task = generate_npcs(
        npcs,
        genre,
        session_dir,
        session_id=session_id,
    )

    map_file, player_file, npc_files = await asyncio.gather(
        map_task, char_task, npc_task
    )

    return {
        "map": map_file,
        "player": player_file,
        "npcs": npc_files,
        "items": [],
    }


def _use_fallback_map(genre: str, session_dir: str) -> str:
    import shutil
    fallback_path = os.path.join(FALLBACKS_DIR, "maps", f"{genre}_default.png")
    dest_path = os.path.join(session_dir, "map.png")
    if os.path.exists(fallback_path):
        shutil.copy2(fallback_path, dest_path)
    else:
        _create_placeholder_map(dest_path, genre)
    return "map.png"


def _use_fallback_sprite(name: str, session_dir: str) -> str:
    filename = f"{name}.png"
    dest_path = os.path.join(session_dir, filename)
    _create_placeholder_sprite(dest_path)
    return filename


def _create_placeholder_map(path: str, genre: str):
    from PIL import Image, ImageDraw
    colors = {"fantasy": (40, 30, 20), "cyberpunk": (10, 10, 30), "horror": (15, 10, 10)}
    bg = colors.get(genre, (20, 20, 20))
    img = Image.new("RGB", (MAP_SIZE, MAP_SIZE), bg)
    draw = ImageDraw.Draw(img)
    for i in range(0, MAP_SIZE, 64):
        line_color = tuple(min(c + 15, 255) for c in bg)
        draw.line([(i, 0), (i, MAP_SIZE)], fill=line_color, width=1)
        draw.line([(0, i), (MAP_SIZE, i)], fill=line_color, width=1)
    wall_color = tuple(min(c + 40, 255) for c in bg)
    draw.rectangle([0, 0, MAP_SIZE - 1, MAP_SIZE - 1], outline=wall_color, width=8)
    img.save(path)


def _create_placeholder_sprite(path: str):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 4, 56, 56], fill=(100, 150, 255, 255))
    draw.ellipse([20, 12, 44, 32], fill=(200, 180, 160, 255))
    img.save(path)
