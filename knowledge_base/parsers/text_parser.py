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


class _OfficialBodyHTML(HTMLParser):
    """Extract paragraph text only from an official TRS editor body."""

    def __init__(self) -> None:
        super().__init__()
        self.editor_depth = 0
        self.paragraph_depth = 0
        self.current: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        classes = dict(attrs).get("class", "").split()
        if tag == "div" and "TRS_Editor" in classes and self.editor_depth == 0:
            self.editor_depth = 1
        elif self.editor_depth and tag == "div":
            self.editor_depth += 1
        if self.editor_depth and tag == "p":
            self.paragraph_depth += 1
            if self.paragraph_depth == 1:
                self.current = []

    def handle_endtag(self, tag: str) -> None:
        if self.editor_depth and tag == "p" and self.paragraph_depth:
            self.paragraph_depth -= 1
            if self.paragraph_depth == 0:
                value = clean_text("".join(self.current))
                article_note = re.match(r"^(第\s*[一二三四五六七八九十百千万零〇两\d]+\s*条)\[\[FOOTNOTE_(\d+)\]\]\s*(.*)$", value)
                if article_note:
                    value = clean_text(article_note.group(1) + " " + article_note.group(3))
                else:
                    note = re.match(r"^\[\[FOOTNOTE_(\d+)\]\]\s*(.*)$", value)
                    if note:
                        value = f"修订注{note.group(1)}：{note.group(2)}"
                if value:
                    self.parts.append(value)
                self.current = []
        if self.editor_depth and tag == "div":
            self.editor_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.editor_depth and self.paragraph_depth and clean_text(data):
            for index, marker in enumerate("①②③④⑤⑥⑦⑧⑨⑩", start=1):
                data = data.replace(marker, f"[[FOOTNOTE_{index}]]")
            self.current.append(data)


def parse_official_html_cache(cache_path: Path, original_path: Path) -> ParsedDocument:
    raw = cache_path.read_text(encoding="utf-8", errors="replace")
    parser = _OfficialBodyHTML()
    parser.feed(raw)
    blocks = [SourceBlock(text, source_kind="official_html", block_id=f"b{index:05d}") for index, text in enumerate(parser.parts, start=1)]
    if len(blocks) < 20:
        return ParsedDocument(original_path, "pdf", [], {}, [f"官方网页正文缓存不可用：{cache_path}"], "needs_ocr")
    metadata = infer_metadata(blocks, original_path)
    metadata["text_source_path"] = f"data/raw/official_text_cache/{cache_path.name}"
    return ParsedDocument(
        original_path,
        "pdf+official_html",
        blocks,
        metadata,
        [f"原PDF文本层不足；正文改用本地缓存的官方网页版本：{cache_path.name}"],
    )


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
