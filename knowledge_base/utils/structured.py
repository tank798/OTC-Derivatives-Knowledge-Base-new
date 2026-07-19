from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import config
from models import ParsedDocument, SourceBlock
from utils.text import clean_text, compact


GUIDE_TOP_RE = re.compile(r"^[一二三四五六七八九十百]+[、.]\s*(.+)$")
GUIDE_SUB_RE = re.compile(r"^[（(][一二三四五六七八九十百]+[）)]\s*(.+)$")
GUIDE_PAREN_MINOR_RE = re.compile(r"^[（(]\d+[）)]\s*(.+)$")
GUIDE_MINOR_RE = re.compile(r"^\d+[.．、]\s*(.+)$")
GUIDE_NORMATIVE_RE = re.compile(r"(?:应当|应|不得|可以|可|负责|包括|主要职责|是指|须|建议)")
ATTACHMENT_RE = re.compile(r"^(?:附件|附录)(?:\s*[一二三四五六七八九十百\d]+)?(?:[:：\s]|$)")
NOTE_RE = re.compile(r"^(?:注|说明|备注)\s*[:：]")


def serialize_clean_text(document: ParsedDocument) -> tuple[str, dict[str, tuple[int, int]]]:
    """Serialize Chunk-eligible blocks once and assign stable source offsets."""

    parts: list[str] = []
    positions: dict[str, tuple[int, int]] = {}
    cursor = 0
    for block in document.blocks:
        value = clean_text(block.text)
        if not value:
            block.start_char = block.end_char = cursor
            continue
        if parts:
            parts.append("\n\n")
            cursor += 2
        start = cursor
        parts.append(value)
        cursor += len(value)
        block.start_char = start
        block.end_char = cursor
        block.source_page_end = block.source_page_end or block.page
        positions[block.block_id] = (start, cursor)
    return "".join(parts), positions


def clean_text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_short_heading(text: str, pattern: re.Pattern[str], limit: int) -> bool:
    match = pattern.fullmatch(text)
    if not match:
        return False
    remainder = clean_text(match.group(1))
    return (
        bool(remainder)
        and len(compact(remainder)) <= limit
        and not re.search(r"[。；;！？!?]", remainder)
        and not GUIDE_NORMATIVE_RE.search(remainder)
    )


def block_type(block: SourceBlock, document_title: str = "") -> str:
    text = clean_text(block.text)
    if block.source_kind == "table" or block.table_data:
        return "table"
    if block.source_kind == "formula" or block.formula_data:
        return "formula"
    if document_title and compact(text).lstrip("附件:：") == compact(document_title):
        return "document_title"
    if compact(text) in {"说明及声明", "说明和声明", "声明", "前言"}:
        return "guide_heading"
    if re.match(r"^第.+[编篇部分](?:\s|$)", text):
        return "part"
    if re.match(r"^第.+章(?:\s|$)", text):
        return "chapter"
    if re.match(r"^第.+节(?:\s|$)", text):
        return "section"
    if re.match(r"^第.+条(?:\s|$)", text):
        return "article"
    if ATTACHMENT_RE.match(text):
        return "attachment"
    if NOTE_RE.match(text):
        return "note"
    if _is_short_heading(text, GUIDE_TOP_RE, 36):
        return "guide_heading"
    if _is_short_heading(text, GUIDE_SUB_RE, 30):
        return "guide_subheading"
    if _is_short_heading(text, GUIDE_PAREN_MINOR_RE, 24):
        return "guide_minor_heading"
    if _is_short_heading(text, GUIDE_MINOR_RE, 24):
        return "guide_minor_heading"
    if re.search(r"(?:法定代表人|负责人)\s*[:：]?", text) and len(compact(text)) <= 120:
        return "signoff"
    return "paragraph"


def table_retrieval_text(table_data: dict[str, Any]) -> str:
    caption = clean_text(str(table_data.get("caption", "")))
    headers = table_data.get("headers", [])
    rows = table_data.get("rows", [])
    width = int(table_data.get("column_count", 0) or 0)
    labels: list[str] = []
    for column in range(width):
        values = [
            clean_text(row[column])
            for row in headers
            if column < len(row) and clean_text(row[column])
        ]
        labels.append(" / ".join(dict.fromkeys(values)) or f"第{column + 1}列")
    lines = [caption] if caption else []
    for row in rows:
        fields = [
            f"{labels[index]}：{clean_text(value)}"
            for index, value in enumerate(row[:width])
            if clean_text(value)
        ]
        if fields:
            lines.append("；".join(fields))
    return "\n".join(lines)


def legacy_markdown_table_data(text: str, table_id: str) -> dict[str, Any]:
    rows: list[list[str]] = []
    for line in clean_text(text).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        value = line.strip().strip("|")
        cells = [
            clean_text(cell.replace("<br>", "\n").replace("\\|", "|"))
            for cell in value.split("|")
        ]
        if cells and all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    width = max((len(row) for row in rows), default=0)
    warnings = ["由旧版Markdown恢复展示网格；合并单元格信息不可追溯"]
    if len({len(row) for row in rows}) > 1:
        warnings.append("旧版Markdown行列数不一致，HTML按各行原长度展示且未机械补列")
    return {
        "table_id": table_id,
        "caption": "",
        "headers": rows[:1],
        "rows": rows[1:],
        "cells": [
            {"row": row_index, "column": column_index, "text": cell, "rowspan": 1, "colspan": 1}
            for row_index, row in enumerate(rows)
            for column_index, cell in enumerate(row)
        ],
        "column_count": width,
        "source_page_start": 0,
        "source_page_end": 0,
        "source_fragments": [],
        "parsing_warnings": warnings,
        "recovery_source": "legacy_markdown",
    }


def structured_blocks(document: ParsedDocument) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    appendix_mode = False
    title = document.metadata.get("document_title", "")
    for block in document.blocks:
        kind = block_type(block, title)
        if kind == "attachment":
            appendix_mode = True
        region = "appendix" if appendix_mode else "body"
        block.region = region
        row: dict[str, Any] = {
            "block_id": block.block_id,
            "block_type": kind,
            "text": clean_text(block.text),
            "style": block.style,
            "source_kind": block.source_kind,
            "source_page_start": block.page,
            "source_page_end": block.source_page_end or block.page,
            "start_char": block.start_char,
            "end_char": block.end_char,
            "region": region,
        }
        if kind == "table":
            data = dict(block.table_data) if block.table_data else legacy_markdown_table_data(
                block.text,
                f"table_{block.block_id}",
            )
            if not data.get("caption") and result:
                previous_text = clean_text(result[-1].get("text", ""))
                if len(compact(previous_text)) <= 100 and re.search(r"(?:表|附件)", previous_text):
                    data["caption"] = previous_text
            data["retrieval_text"] = table_retrieval_text(data)
            data["parsing_warnings"] = list(dict.fromkeys(
                list(data.get("parsing_warnings", [])) + list(block.parsing_warnings)
            ))
            row["table_data"] = data
        if block.formula_data:
            row["formula_data"] = block.formula_data
        elif "【公式" in row["text"]:
            expressions = [
                clean_text(value)
                for value in re.findall(r"【公式[^】]*】\s*([^\n]+)", row["text"])
                if clean_text(value)
            ]
            if expressions:
                row["formula_data"] = {
                    "raw_text": row["text"],
                    "expressions": expressions,
                    "latex": "",
                    "formula_label": "公式",
                    "source_page": block.page,
                    "conversion_status": "verified_linearized_raw_text",
                }
        warnings = list(dict.fromkeys(block.parsing_warnings))
        if warnings:
            row["parsing_warnings"] = warnings
        result.append(row)
    return result


def structured_hash(blocks: list[dict[str, Any]]) -> str:
    encoded = json.dumps(blocks, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def content_hash(document: ParsedDocument) -> str:
    payload = [
        {
            "text": clean_text(block.text),
            "style": block.style,
            "source_kind": block.source_kind,
            "page": block.page,
            "source_page_end": block.source_page_end or block.page,
        }
        for block in document.blocks
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def document_to_row(document: ParsedDocument, document_id: str, file_hash: str) -> dict[str, Any]:
    normalized_text, _ = serialize_clean_text(document)
    display_blocks = structured_blocks(document)
    actual_clean_hash = clean_text_hash(normalized_text)
    front_matter = list(document.cleaning.get("removed_front_matter", []))
    return {
        "document_id": document_id,
        "file_name": document.file_path.name,
        "file_path": config.repository_path(document.file_path),
        "source_type": document.source_type,
        "file_sha256": file_hash,
        "content_sha256": content_hash(document),
        "metadata": document.metadata,
        "warnings": document.warnings,
        "extraction_status": document.extraction_status,
        "cleaning": document.cleaning,
        "original_text_sha256": document.cleaning.get("original_text_sha256", ""),
        "clean_text_sha256": document.cleaning.get("clean_text_sha256", content_hash(document)),
        "clean_text_hash": actual_clean_hash,
        "structured_blocks_sha256": structured_hash(display_blocks),
        "front_matter": front_matter,
        "body_blocks": [block for block in display_blocks if block["region"] == "body"],
        "appendices": [block for block in display_blocks if block["region"] == "appendix"],
        "clean_text": normalized_text,
        "structured_blocks": display_blocks,
        "normalized_text": normalized_text,
        "blocks": [
            {
                "block_id": block.block_id,
                "text": block.text,
                "style": block.style,
                "source_kind": block.source_kind,
                "page": block.page,
                "region": block.region,
                "source_page_end": block.source_page_end,
                "start_char": block.start_char,
                "end_char": block.end_char,
                "table_data": block.table_data,
                "formula_data": block.formula_data,
                "parsing_warnings": block.parsing_warnings,
                "layout": block.layout,
            }
            for block in document.blocks
        ],
    }


def row_to_document(row: dict[str, Any], current_path: Path | None = None) -> ParsedDocument:
    blocks = [SourceBlock(**block) for block in row.get("blocks", [])]
    return ParsedDocument(
        current_path or Path(row["file_path"]),
        row.get("source_type", ""),
        blocks,
        dict(row.get("metadata", {})),
        list(row.get("warnings", [])),
        row.get("extraction_status", "success"),
        dict(row.get("cleaning", {})),
    )


def save_document(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_document(path: Path, current_path: Path | None = None) -> tuple[ParsedDocument, dict[str, Any]]:
    row = json.loads(path.read_text(encoding="utf-8"))
    return row_to_document(row, current_path), row
