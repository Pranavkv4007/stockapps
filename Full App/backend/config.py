"""
Configuration for Stock Analysis Hub.
Paths, constants, and environment variable overrides.
"""

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

# LLM Model constants
OPENAI_MODEL = "gpt-4.1-mini-2025-04-14"
GPT4O = "gpt-4o-mini-2024-07-18"
GEMINI_MODEL = "gemini-3-pro-preview"
MODEL_OPTIONS = ["gemini", "openai", "gpt4o"]
