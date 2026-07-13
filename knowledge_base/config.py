import os
from pathlib import Path

PROGRAM_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PROGRAM_ROOT.parent
INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "监管文件"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
DOCUMENT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "documents"
MANIFEST_PATH = PROJECT_ROOT / "data" / "processed" / "build_manifest.json"
METADATA_PATH = PROJECT_ROOT / "data" / "metadata" / "regulations.jsonl"
OFFICIAL_TEXT_CACHE_DIR = Path(os.environ.get("OFFICIAL_TEXT_CACHE_DIR", PROJECT_ROOT / "data" / "raw" / "official_text_cache"))


def repository_path(value: str | Path) -> str:
    """Serialize project files portably while preserving external paths."""
    resolved = Path(value).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)

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
PARSER_VERSION = "2.4.2-cross-page-continuations+clean-pdf-table-cells"
DOCX_PARSER_VERSION = "2.3.1-smarttag-text+toc-style-scope+front-metadata"
LEGACY_DOC_PARSER_VERSION = "2.3.0-direct-text-preserve-preface"
OFFICIAL_HTML_PARSER_VERSION = "2.2.0-footnote-structure"
CHUNKER_BASE_VERSION = "3.2.0-inline-list-markers"
CHUNKER_MULTIPART_VERSION = "3.2.0-inline-list-markers+multipart-reset"
CHUNKER_VERSION = "3.2.0-inline-list-markers+embedded-part+official-footnote"


def parser_version_for_suffix(suffix: str, *, uses_official_cache: bool = False) -> str:
    """Return a cache version scoped to the parser that can affect the file."""
    normalized = suffix.lower()
    if normalized == ".docx":
        return f"{PARSER_VERSION}:{DOCX_PARSER_VERSION}"
    if normalized == ".doc":
        return f"{PARSER_VERSION}:{LEGACY_DOC_PARSER_VERSION}"
    if normalized == ".pdf" and uses_official_cache:
        return f"{PARSER_VERSION}:{OFFICIAL_HTML_PARSER_VERSION}"
    return PARSER_VERSION
