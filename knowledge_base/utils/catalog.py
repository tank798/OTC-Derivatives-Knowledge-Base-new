from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from utils.metadata import compact_title
from utils.text import clean_text, compact, stable_id


METADATA_FIELDS = (
    "document_title", "issuing_authority", "document_number", "publication_date",
    "effective_date", "validity_status", "version", "official_url", "catalog_group",
    "catalog_index", "local_file_path", "source_status",
)


def load_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def catalog_by_filename(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = clean_text(row.get("file_name", ""))
        if name:
            if name in result:
                raise ValueError(f"元数据目录存在重复文件名：{name}")
            result[name] = row
    return result


def resolve_catalog_record(path: Path, by_filename: dict[str, dict[str, Any]]) -> dict[str, Any]:
    exact = by_filename.get(clean_text(path.name))
    if exact:
        return dict(exact)
    stem = compact_title(path.stem)
    candidates = [row for name, row in by_filename.items() if compact_title(Path(name).stem) == stem]
    if len(candidates) == 1:
        return dict(candidates[0])
    if len(candidates) > 1:
        raise ValueError(f"文件无法唯一匹配元数据：{path.name}")
    return {}


def merge_metadata(parsed: dict[str, Any], authoritative: dict[str, Any]) -> dict[str, Any]:
    merged = dict(parsed)
    for field in METADATA_FIELDS:
        value = authoritative.get(field)
        if value not in (None, ""):
            merged[field] = value
    if authoritative.get("document_id"):
        merged["legacy_document_id"] = authoritative["document_id"]
    merged["document_title_source"] = "authoritative_catalog" if authoritative else merged.get("document_title_source", "")
    return merged


def canonical_document_id(metadata: dict[str, Any], path: Path) -> str:
    title = compact_title(str(metadata.get("document_title") or path.stem))
    number = compact(str(metadata.get("document_number") or ""))
    authority = compact(str(metadata.get("issuing_authority") or ""))
    version = compact(str(metadata.get("version") or ""))
    identity = [title, number, authority, version]
    if not title:
        raise ValueError(f"无法生成稳定文档ID，标题为空：{path.name}")
    return "doc_" + stable_id(*identity, length=24)


def metadata_hash(metadata: dict[str, Any]) -> str:
    payload = {field: metadata.get(field, "") for field in METADATA_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

