from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import config
from models import ParsedDocument, SourceBlock
from utils.text import clean_text


def content_hash(document: ParsedDocument) -> str:
    payload = [
        {
            "text": clean_text(block.text),
            "style": block.style,
            "source_kind": block.source_kind,
            "page": block.page,
        }
        for block in document.blocks
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def document_to_row(document: ParsedDocument, document_id: str, file_hash: str) -> dict[str, Any]:
    normalized_text = "\n\n".join(clean_text(block.text) for block in document.blocks if clean_text(block.text))
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
        "normalized_text": normalized_text,
        "blocks": [
            {
                "block_id": block.block_id,
                "text": block.text,
                "style": block.style,
                "source_kind": block.source_kind,
                "page": block.page,
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
    )


def save_document(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_document(path: Path, current_path: Path | None = None) -> tuple[ParsedDocument, dict[str, Any]]:
    row = json.loads(path.read_text(encoding="utf-8"))
    return row_to_document(row, current_path), row
