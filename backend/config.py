import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OVERSHOOT_API_KEY = os.getenv("OVERSHOOT_API_KEY", "")
OVERSHOOT_BASE_URL = os.getenv("OVERSHOOT_BASE_URL", "https://api.overshoot.ai")
OVERSHOOT_ADAPTER = os.getenv("OVERSHOOT_ADAPTER", "generic_v1")
OVERSHOOT_MOCK_MODE = os.getenv("OVERSHOOT_MOCK_MODE", "true")

# Model names — all use the same GEMINI_API_KEY
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")  # For text/vision tasks
NANOBANANA_MODEL = os.getenv(
    "NANOBANANA_MODEL", "gemini-3-pro-image-preview"
)  # NanoBanana image model
LYRIA_MODEL = "lyria"  # Audio generation (TBD — may use Gemini API key too)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
VIDEO_SESSIONS_DIR = os.path.join(UPLOAD_DIR, "video_sessions")
GAMES_DIR = os.path.join(os.path.dirname(__file__), "static", "games")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
FALLBACKS_DIR = os.path.join(os.path.dirname(__file__), "fallbacks")

MAP_SIZE = 1920
SUPPORTED_GENRES = ["fantasy", "cyberpunk", "horror"]

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VIDEO_SESSIONS_DIR, exist_ok=True)
os.makedirs(GAMES_DIR, exist_ok=True)
