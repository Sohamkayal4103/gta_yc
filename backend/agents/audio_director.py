"""Agent 4: Audio Director — Generates soundtrack and sound effects.

Uses Lyria (DeepMind's audio model). The exact API integration may need
adjustment at the hackathon once we have access. Falls back gracefully.
"""

import os
from google import genai
from google.genai import types
from backend.config import GEMINI_API_KEY, LYRIA_MODEL
from backend.utils.llm_logging import start_call, finish_call

GENRE_AUDIO = {
    "fantasy": {
        "soundtrack_prompt": "Atmospheric medieval fantasy RPG background music. Ambient orchestral with soft strings, gentle flute melodies, and mystical chimes. Loopable, 30 seconds. Evokes exploring ancient dungeons and enchanted halls.",
        "sfx_prompts": {
            "interact": "Fantasy game interaction sound effect. Magical sparkle with a soft chime.",
            "complete": "Fantasy quest complete fanfare. Short triumphant brass and harp flourish.",
            "pickup": "Fantasy item pickup sound. Soft magical whoosh with crystal resonance.",
        }
    },
    "cyberpunk": {
        "soundtrack_prompt": "Dark cyberpunk ambient background music. Synthwave with deep bass, atmospheric pads, subtle glitch beats. Loopable, 30 seconds. Evokes neon-lit dystopian interiors and hacking.",
        "sfx_prompts": {
            "interact": "Cyberpunk UI interaction sound. Digital beep with electronic feedback.",
            "complete": "Cyberpunk mission complete sound. Ascending synth arpeggio with data burst.",
            "pickup": "Cyberpunk item pickup sound. Quick electronic scan and confirm beep.",
        }
    },
    "horror": {
        "soundtrack_prompt": "Creepy horror ambient background music. Dark drones, unsettling whispers, distant metallic scrapes, occasional heartbeat pulse. Loopable, 30 seconds. Evokes abandoned building exploration.",
        "sfx_prompts": {
            "interact": "Horror game interaction sound. Creaky door mixed with unsettling whisper.",
            "complete": "Horror objective complete. Tense stinger resolving to uneasy silence.",
            "pickup": "Horror item pickup. Quick scrape and rustle with subtle breathing.",
        }
    }
}


async def generate_soundtrack(
    genre: str,
    session_dir: str,
    session_id: str | None = None,
) -> str:
    """Generate background music for the game using Lyria."""
    audio_config = GENRE_AUDIO[genre]
    soundtrack_path = os.path.join(session_dir, "bgm.mp3")

    try:
        print(f"[AUDIO] Generating soundtrack with model={LYRIA_MODEL}")
        client = genai.Client(api_key=GEMINI_API_KEY)
        soundtrack_ctx = start_call(
            session_id,
            "audio_director",
            "generate_soundtrack",
            {
                "api": "client.models.generate_content",
                "model": LYRIA_MODEL,
                "contents": [{"type": "text", "text": audio_config["soundtrack_prompt"]}],
                "config": {"response_modalities": ["AUDIO"]},
                "genre": genre,
            },
        )
        try:
            response = client.models.generate_content(
                model=LYRIA_MODEL,
                contents=[audio_config["soundtrack_prompt"]],
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                ),
            )
            finish_call(
                soundtrack_ctx,
                response_payload={
                    "api": "client.models.generate_content",
                    "model": LYRIA_MODEL,
                    "response": response,
                },
            )
        except Exception as exc:
            finish_call(soundtrack_ctx, error=exc)
            raise

        print(f"[AUDIO] Response parts: {len(response.parts) if response.parts else 0}")
        for i, part in enumerate(response.parts):
            print(f"[AUDIO] Part {i}: text={part.text is not None}, inline_data={part.inline_data is not None}")
            if part.inline_data is not None:
                print(f"[AUDIO] Audio mime: {part.inline_data.mime_type}, data_len: {len(part.inline_data.data)}")
                with open(soundtrack_path, "wb") as f:
                    f.write(part.inline_data.data)
                return "bgm.mp3"

        raise RuntimeError("No audio in response")
    except Exception as e:
        import traceback
        print(f"[AUDIO] Soundtrack FAILED: {e}")
        traceback.print_exc()
        return _use_fallback_audio(genre, "bgm", session_dir)


async def generate_sfx(
    genre: str,
    session_dir: str,
    session_id: str | None = None,
) -> dict:
    """Generate sound effects for the game."""
    audio_config = GENRE_AUDIO[genre]
    sfx_files = {}

    for sfx_name, prompt in audio_config["sfx_prompts"].items():
        filename = f"sfx_{sfx_name}.mp3"
        sfx_path = os.path.join(session_dir, filename)

        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            sfx_ctx = start_call(
                session_id,
                "audio_director",
                f"generate_sfx_{sfx_name}",
                {
                    "api": "client.models.generate_content",
                    "model": LYRIA_MODEL,
                    "contents": [{"type": "text", "text": prompt}],
                    "config": {"response_modalities": ["AUDIO"]},
                    "genre": genre,
                    "sfx_name": sfx_name,
                },
            )
            try:
                response = client.models.generate_content(
                    model=LYRIA_MODEL,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                    ),
                )
                finish_call(
                    sfx_ctx,
                    response_payload={
                        "api": "client.models.generate_content",
                        "model": LYRIA_MODEL,
                        "response": response,
                    },
                )
            except Exception as exc:
                finish_call(sfx_ctx, error=exc)
                raise

            for part in response.parts:
                if part.inline_data is not None:
                    with open(sfx_path, "wb") as f:
                        f.write(part.inline_data.data)
                    sfx_files[sfx_name] = filename
                    break

            if sfx_name not in sfx_files:
                raise RuntimeError("No audio in response")
        except Exception as e:
            print(f"SFX {sfx_name} generation failed: {e}")
            sfx_files[sfx_name] = filename  # Reference it even if missing

    return sfx_files


async def generate_all_audio(
    genre: str,
    session_dir: str,
    session_id: str | None = None,
) -> dict:
    """Generate all audio assets."""
    import asyncio
    soundtrack, sfx = await asyncio.gather(
        generate_soundtrack(genre, session_dir, session_id=session_id),
        generate_sfx(genre, session_dir, session_id=session_id),
    )
    return {
        "soundtrack": soundtrack,
        "sfx": sfx,
    }


def _use_fallback_audio(genre: str, name: str, session_dir: str) -> str:
    """Copy fallback audio or return the filename anyway."""
    import shutil
    from backend.config import FALLBACKS_DIR
    fallback_path = os.path.join(FALLBACKS_DIR, "audio", f"{genre}_{name}.mp3")
    dest_path = os.path.join(session_dir, f"{name}.mp3")
    if os.path.exists(fallback_path):
        shutil.copy2(fallback_path, dest_path)
    return f"{name}.mp3"
