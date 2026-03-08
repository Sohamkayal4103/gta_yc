import os
import json
import re
from backend.config import GAMES_DIR


def get_next_run_number() -> int:
    """Find the next run number by checking existing run_N folders."""
    max_run = 0
    if os.path.exists(GAMES_DIR):
        for name in os.listdir(GAMES_DIR):
            match = re.match(r"run_(\d+)", name)
            if match:
                max_run = max(max_run, int(match.group(1)))
    return max_run + 1


def get_session_dir(session_id: str) -> str:
    """Get or create a run-numbered directory for this session."""
    run_num = get_next_run_number()
    run_name = f"run_{run_num}_{session_id}"
    session_dir = os.path.join(GAMES_DIR, run_name)
    os.makedirs(session_dir, exist_ok=True)

    # Also create a symlink with just the session_id for the API to find
    symlink_path = os.path.join(GAMES_DIR, session_id)
    if os.path.exists(symlink_path) or os.path.islink(symlink_path):
        os.remove(symlink_path)
    os.symlink(run_name, symlink_path)

    print(f"[STORAGE] Created {run_name}/ (symlinked from {session_id})")
    return session_dir


def save_manifest(session_id: str, manifest: dict) -> str:
    """Save the game manifest JSON."""
    # Find the actual dir via symlink
    session_dir = os.path.join(GAMES_DIR, session_id)
    if os.path.islink(session_dir):
        session_dir = os.path.join(GAMES_DIR, os.readlink(session_dir))
    manifest_path = os.path.join(session_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path


def save_debug_log(session_id: str, filename: str, content: str):
    """Save a debug log file in the session directory."""
    session_dir = os.path.join(GAMES_DIR, session_id)
    if os.path.islink(session_dir):
        session_dir = os.path.join(GAMES_DIR, os.readlink(session_dir))
    filepath = os.path.join(session_dir, filename)
    with open(filepath, "w") as f:
        f.write(content)


def load_manifest(session_id: str) -> dict | None:
    """Load a game manifest if it exists."""
    manifest_path = os.path.join(GAMES_DIR, session_id, "manifest.json")
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path, "r") as f:
        return json.load(f)
