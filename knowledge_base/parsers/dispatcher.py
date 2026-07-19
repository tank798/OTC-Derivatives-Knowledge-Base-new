from __future__ import annotations

from pathlib import Path

from models import ParsedDocument
from parsers.docx_parser import parse_docx
from parsers.legacy_doc_parser import parse_legacy_doc
from parsers.pdf_parser import parse_pdf
from parsers.text_parser import parse_text
from parsers.xlsx_parser import parse_xlsx


def parse_file(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix in {".doc", ".docx"}:
        # 不能只相信扩展名：WPS/交易所下载文件可能出现.doc内实际为
        # OOXML，或.docx内仍为OLE复合文档的情况。
        with path.open("rb") as handle:
            signature = handle.read(8)
        if signature == bytes.fromhex("D0CF11E0A1B11AE1"):
            return parse_legacy_doc(path)
        if signature.startswith(b"PK"):
            return parse_docx(path)
        return parse_docx(path) if suffix == ".docx" else parse_legacy_doc(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".xlsx":
        return parse_xlsx(path)
    if suffix in {".txt", ".md", ".html", ".htm"}:
        return parse_text(path)
    return ParsedDocument(path, suffix.lstrip("."), [], {}, ["不支持的文件类型"], "failed")
