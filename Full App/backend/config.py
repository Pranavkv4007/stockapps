"""
Configuration for Stock Analysis Hub.
Paths, constants, and environment variable overrides.
"""

import json
import os
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(os.path.dirname(PROJECT_ROOT), ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH, override=True)

# Allow STOCK_HUB_ROOT env var to override base path
HUB_ROOT = os.environ.get("STOCK_HUB_ROOT", os.path.dirname(PROJECT_ROOT))

SECTOR_DIR = os.path.join(HUB_ROOT, "Sector")
INDIVIDUAL_DIR = os.path.join(HUB_ROOT, "Individual_Stocks")
SCORES_JSON = os.path.join(HUB_ROOT, "scores.json")
COMBINED_CSV = os.path.join(SECTOR_DIR, "Sector_Combined.csv")

# Score tier thresholds and colors
TIER_THRESHOLDS = [
    (80, "Excellent", "#2d6a4f", "white"),
    (60, "Good", "#52b788", "white"),
    (40, "Average", "#f4a261", "black"),
    (0, "Weak", "#e76f51", "white"),
]

SIGNAL_COLORS = {
    "Strong Buy": "#2d6a4f",
    "Moderate Buy": "#52b788",
    "Mixed": "#f4a261",
    "Avoid": "#e76f51",
    "Financials Strong, Concall Weak": "#e9c46a",
    "Concall Strong, Financials Weak": "#e9c46a",
    "Concall Missing": "#adb5bd",
    "Financials Missing": "#adb5bd",
}

# LLM Model constants — loaded from models.json at project root
_MODELS_JSON = os.path.join(os.path.dirname(PROJECT_ROOT), "models.json")
with open(_MODELS_JSON) as _f:
    _MODELS_CFG = json.load(_f)
OPENAI_MODEL = _MODELS_CFG["models"]["openai"]
GPT4O = _MODELS_CFG["models"]["gpt4o"]
GEMINI_MODEL = _MODELS_CFG["models"]["gemini"]
CLAUDE_HAIKU = _MODELS_CFG["models"]["claude-haiku"]
CLAUDE_SONNET = _MODELS_CFG["models"]["claude-sonnet"]
CLAUDE_OPUS = _MODELS_CFG["models"]["claude-opus"]
GEMINI_FLASH = _MODELS_CFG["models"]["gemini-flash"]
MODEL_OPTIONS = _MODELS_CFG["model_options"]
