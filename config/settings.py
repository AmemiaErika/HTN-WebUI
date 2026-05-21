from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
ASSET_DIR = BASE_DIR / "assets"
DATA_DIR = BASE_DIR / "data"
ASSETS_JSON = DATA_DIR / "assets.json"
RESULTS_JSON = DATA_DIR / "generation_results.json"

for p in [UPLOAD_DIR, OUTPUT_DIR, ASSET_DIR, DATA_DIR]:
    p.mkdir(parents=True, exist_ok=True)

DEFAULT_LIST_ANALYZER = os.getenv("DEFAULT_LIST_ANALYZER", "gemini")
DEFAULT_IMAGE_GENERATOR = os.getenv("DEFAULT_IMAGE_GENERATOR", "gemini")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
