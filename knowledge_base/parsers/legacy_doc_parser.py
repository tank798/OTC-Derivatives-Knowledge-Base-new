from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import re

from models import ParsedDocument
from parsers.docx_parser import parse_docx
from utils.metadata import infer_metadata
from utils.text import clean_text
from models import SourceBlock


def parse_legacy_doc(path: Path) -> ParsedDocument:
    soffice = shutil.which("soffice") or "/opt/homebrew/bin/soffice"
    with tempfile.TemporaryDirectory(prefix="regulatory_doc_") as temp_dir:
        command = [soffice, "--headless", "--convert-to", "docx", "--outdir", temp_dir, str(path)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        converted = Path(temp_dir) / (path.stem + ".docx")
        if completed.returncode == 0 and converted.exists():
            parsed = parse_docx(converted)
            parsed.file_path = path
            parsed.source_type = "doc"
            parsed.metadata = infer_metadata(parsed.blocks, path)
            parsed.warnings.append("旧DOC在临时目录经LibreOffice转换为DOCX后解析，原文件未修改")
            if parsed.blocks:
                return parsed
    textutil = shutil.which("textutil")
    if textutil:
        completed = subprocess.run([textutil, "-convert", "txt", "-stdout", str(path)], capture_output=True, timeout=120)
        if completed.returncode == 0 and completed.stdout:
            text = completed.stdout.decode("utf-8", errors="replace")
            text = re.sub(r"\b(?:HYPERLINK|PAGEREF|REF)\s+(?:\"[^\"]*\"|\S+)(?:\s+\\[a-z]+)*", "", text, flags=re.I)
            text = re.sub(r"\b(?:PAGE|NUMPAGES)\s+\\\*\s+MERGEFORMAT\s*\d*", "", text, flags=re.I)
            text = re.sub(r"(?m)^\s*PAGE\s*$", "", text, flags=re.I)
            paragraphs = [clean_text(value) for value in text.splitlines() if clean_text(value)]
            blocks = [SourceBlock(value, block_id=f"b{index:05d}") for index, value in enumerate(paragraphs, start=1)]
            if blocks:
                return ParsedDocument(path, "doc", blocks, infer_metadata(blocks, path), ["LibreOffice转换失败，旧DOC通过macOS textutil只读抽取并清理域代码，原文件未修改"])
    return ParsedDocument(path, "doc", [], {}, ["旧DOC的LibreOffice转换和textutil抽取均失败"], "failed")
