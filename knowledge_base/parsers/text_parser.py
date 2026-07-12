from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re

from models import ParsedDocument, SourceBlock
from utils.metadata import infer_metadata
from utils.text import clean_text


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if clean_text(data):
            self.parts.append(clean_text(data))


def parse_text(path: Path) -> ParsedDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        parser = _HTMLText()
        parser.feed(raw)
        paragraphs = parser.parts
    else:
        paragraphs = [clean_text(part) for part in re.split(r"\n\s*\n|(?m)(?=^#{1,6}\s+)", raw) if clean_text(part)]
    blocks = [SourceBlock(text, block_id=f"b{index:05d}") for index, text in enumerate(paragraphs, start=1)]
    return ParsedDocument(path, path.suffix.lower().lstrip("."), blocks, infer_metadata(blocks, path), [])
