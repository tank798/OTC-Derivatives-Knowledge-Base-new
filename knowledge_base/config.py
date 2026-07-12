import os
from pathlib import Path

PROGRAM_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PROGRAM_ROOT.parent
INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "regulations"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"

MAX_CHARS = 1200
TARGET_MIN_CHARS = 600
MIN_CHARS = 200
MAX_OVERLAP_ARTICLES = 2
ENABLE_SEMANTIC_CHUNKING = True
ENABLE_LLM_SEMANTIC_REVIEW = False
DEEPSEEK_API_KEY_FILE = Path(os.environ.get("DEEPSEEK_API_KEY_FILE", ""))
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
LLM_BATCH_UNITS = 30

SUPPORTED_SUFFIXES = {".doc", ".docx", ".pdf", ".txt", ".md", ".html", ".htm", ".xlsx"}
PARSER_VERSION = "1.3.5"
