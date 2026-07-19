from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any

import config
from chunkers import chunk_document
from chunkers.structure import is_embedded_part_heading, is_official_footnote_heading, is_standalone_part_heading
from exporters import export_all, export_file, export_structured_documents
from parsers import parse_file
from utils.catalog import canonical_document_id, catalog_by_filename, load_catalog, merge_metadata, metadata_hash, resolve_catalog_record
from utils.front_matter import clean_front_matter
from utils.structured import clean_text_hash, content_hash, document_to_row, load_document, save_document
from utils.text import body_char_count, compact, sha256_file, stable_id
from utils.validation import article_number, validate_outputs

LOGGER = logging.getLogger("regulatory_chunker")


def scan_files(input_dir: Path) -> list[Path]:
    return sorted(
        (path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in config.SUPPORTED_SUFFIXES and not path.name.startswith(("~$", "."))),
        key=lambda path: str(path.relative_to(input_dir)),
    )


def scan_inventory(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((value for value in input_dir.rglob("*") if value.is_file()), key=lambda value: str(value.relative_to(input_dir))):
        supported = path.suffix.lower() in config.SUPPORTED_SUFFIXES
        temporary = path.name.startswith(("~$", "."))
        selected = supported and not temporary
        reason = "系统或Office临时文件" if temporary else ("不支持的文件类型" if not supported else "")
        rows.append({"file_name": path.name, "file_path": config.repository_path(path), "suffix": path.suffix.lower(), "size_bytes": path.stat().st_size, "selected": selected, "reason": reason})
    return rows


def chunk_locator(draft, body: str) -> str:
    hierarchy = draft.hierarchy
    units = draft.units
    values = [
        hierarchy.get("attachment_name", ""), hierarchy.get("part_title", ""),
        hierarchy.get("chapter_title", ""), hierarchy.get("section_title", ""),
        next((unit.article_start for unit in units if unit.article_start), ""),
        next((unit.article_end for unit in reversed(units) if unit.article_end), ""),
        hierarchy.get("paragraph_title", ""), stable_id(compact(body), length=16),
    ]
    return "|".join(values)


def chunker_version_for(document) -> str:
    if any(is_official_footnote_heading(block.text) or is_embedded_part_heading(block.text) for block in document.blocks):
        return config.CHUNKER_VERSION
    if sum(is_standalone_part_heading(block.text) for block in document.blocks) >= 2:
        return config.CHUNKER_MULTIPART_VERSION
    return config.CHUNKER_BASE_VERSION


def build_rows(document, drafts, rendered, document_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: Counter[str] = Counter()
    for index, (draft, text_values) in enumerate(zip(drafts, rendered), start=1):
        article_values: list[str] = []
        article_ends: list[str] = []
        last_article: int | None = None
        for unit in draft.units:
            start_value = article_number(unit.article_start)
            end_value = article_number(unit.article_end)
            if unit.article_start and (start_value is None or last_article is None or start_value >= last_article):
                article_values.append(unit.article_start)
                article_ends.append(unit.article_end or unit.article_start)
                if end_value is not None:
                    last_article = end_value
        attachment = next((unit.attachment_name for unit in draft.units if unit.attachment_name), draft.hierarchy.get("attachment_name", ""))
        body = text_values["body"]
        locator = chunk_locator(draft, body)
        base_id = "chunk_" + stable_id(document_id, locator, length=24)
        seen_ids[base_id] += 1
        chunk_id = base_id if seen_ids[base_id] == 1 else base_id + f"_{seen_ids[base_id]}"
        row = {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "file_name": document.file_path.name,
            "file_path": config.repository_path(document.file_path),
            "document_title": document.metadata.get("document_title", ""),
            "document_title_source": document.metadata.get("document_title_source", ""),
            "issuing_authority": document.metadata.get("issuing_authority", ""),
            "document_number": document.metadata.get("document_number", ""),
            "publication_date": document.metadata.get("publication_date", ""),
            "effective_date": document.metadata.get("effective_date", ""),
            "validity_status": document.metadata.get("validity_status", ""),
            "version": document.metadata.get("version", ""),
            "official_url": document.metadata.get("official_url", ""),
            "text_source_path": document.metadata.get("text_source_path", ""),
            "part_title": draft.hierarchy.get("part_title", ""),
            "chapter_title": draft.hierarchy.get("chapter_title", ""),
            "section_title": draft.hierarchy.get("section_title", ""),
            "article_start": article_values[0] if article_values else "",
            "article_end": article_ends[-1] if article_ends else "",
            "paragraph_range": draft.hierarchy.get("paragraph_title", ""),
            "attachment_name": attachment,
            "chunk_index": index,
            "character_count": body_char_count(body),
            "is_overlapping": draft.is_overlapping,
            "overlap_source_chunk_id": "",
            "is_oversized": draft.is_oversized or body_char_count(body) > config.MAX_CHARS,
            "oversized_reason": draft.oversized_reason or ("切分后完整语义或表格单元仍超过上限" if body_char_count(body) > config.MAX_CHARS else ""),
            "source_type": document.source_type,
            "source_block_ids": sorted({block_id for unit in draft.units for block_id in unit.block_ids}),
            "primary_block_ids": list(draft.primary_block_ids),
            "overlap_block_ids": list(draft.overlap_block_ids),
            "body_text": body,
            "text": text_values["text"],
        }
        rows.append(row)
    for index, draft in enumerate(drafts):
        if draft.overlap_source_index is not None and 0 <= draft.overlap_source_index < len(rows):
            rows[index]["overlap_source_chunk_id"] = rows[draft.overlap_source_index]["chunk_id"]
    return rows


def _literal_overlap(left: str, right: str, limit: int = 480) -> int:
    """Return only an exact designed suffix/prefix overlap; never fuzzy-delete."""

    maximum = min(len(left), len(right), limit)
    for size in range(maximum, 0, -1):
        if left[-size:] == right[:size]:
            return size
    return 0


def enrich_chunk_positions(rows: list[dict[str, Any]], structured_row: dict[str, Any]) -> None:
    """Attach clean-text coordinates without changing retrieval text or IDs."""

    blocks = {
        block["block_id"]: block
        for block in structured_row.get("structured_blocks", [])
        if block.get("block_id")
    }
    block_paths: dict[str, list[str]] = {}
    hierarchy = {"part": "", "chapter": "", "section": "", "minor": "", "article": ""}
    for block in sorted(blocks.values(), key=lambda item: int(item.get("start_char", -1))):
        kind = block.get("block_type", "")
        text = block.get("text", "")
        if kind == "part":
            hierarchy.update({"part": text, "chapter": "", "section": "", "minor": "", "article": ""})
        elif kind in {"chapter", "guide_heading"}:
            hierarchy.update({"chapter": text, "section": "", "minor": "", "article": ""})
        elif kind in {"section", "guide_subheading"}:
            hierarchy.update({"section": text, "minor": "", "article": ""})
        elif kind == "guide_minor_heading":
            hierarchy.update({"minor": text, "article": ""})
        elif kind == "article":
            article_match = re.match(r"^(第.+?条)", text)
            hierarchy["article"] = article_match.group(1) if article_match else text
        block_paths[block["block_id"]] = [
            value for value in hierarchy.values() if value
        ]
    by_id = {row["chunk_id"]: row for row in rows}
    clean_hash = structured_row.get("clean_text_hash", "")
    for row in rows:
        source_ids = list(dict.fromkeys(row.get("source_block_ids", [])))
        overlap_ids = list(dict.fromkeys(row.get("overlap_block_ids", [])))
        primary_ids = list(dict.fromkeys(row.get("primary_block_ids", [])))
        if not primary_ids:
            source = by_id.get(row.get("overlap_source_chunk_id", ""))
            shared = set(source_ids) & set(source.get("source_block_ids", [])) if source else set()
            inferred = [block_id for block_id in source_ids if block_id not in shared]
            primary_ids = inferred or source_ids
            overlap_ids = [block_id for block_id in source_ids if block_id in shared] if inferred else []
        spans = [
            (int(blocks[block_id].get("start_char", -1)), int(blocks[block_id].get("end_char", -1)))
            for block_id in primary_ids if block_id in blocks
        ]
        spans = [span for span in spans if span[0] >= 0 and span[1] >= span[0]]
        pages = [
            (
                int(blocks[block_id].get("source_page_start", 0) or 0),
                int(blocks[block_id].get("source_page_end", 0) or 0),
            )
            for block_id in source_ids if block_id in blocks
        ]
        source = by_id.get(row.get("overlap_source_chunk_id", ""))
        overlap_left = _literal_overlap(
            source.get("body_text", ""),
            row.get("body_text", ""),
        ) if source and row.get("is_overlapping") else 0
        first_primary_path = next(
            (block_paths[block_id] for block_id in primary_ids if block_id in block_paths),
            [],
        )
        row.update({
            "start_char": min((start for start, _ in spans), default=-1),
            "end_char": max((end for _, end in spans), default=-1),
            "source_page_start": min((start for start, _ in pages if start > 0), default=0),
            "source_page_end": max((end for _, end in pages if end > 0), default=0),
            "section_path": first_primary_path or [
                value for value in (
                    row.get("part_title", ""),
                    row.get("chapter_title", ""),
                    row.get("section_title", ""),
                    row.get("article_start", ""),
                ) if value
            ],
            "block_ids": source_ids,
            "primary_block_ids": primary_ids,
            "overlap_block_ids": overlap_ids,
            "overlap_left": overlap_left,
            "overlap_right": 0,
            "clean_text_hash": clean_hash,
        })
        chunk_payload = {
            key: row.get(key, "")
            for key in (
                "document_title", "chapter_title", "section_title",
                "article_start", "article_end", "text",
            )
        }
        row["chunk_hash"] = hashlib.sha256(
            json.dumps(
                chunk_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def refresh_chunk_metadata(rows: list[dict[str, Any]], document, document_id: str) -> None:
    for index, row in enumerate(rows, start=1):
        row.update({
            "document_id": document_id,
            "file_name": document.file_path.name,
            "file_path": config.repository_path(document.file_path),
            "document_title": document.metadata.get("document_title", ""),
            "document_title_source": document.metadata.get("document_title_source", ""),
            "issuing_authority": document.metadata.get("issuing_authority", ""),
            "document_number": document.metadata.get("document_number", ""),
            "publication_date": document.metadata.get("publication_date", ""),
            "effective_date": document.metadata.get("effective_date", ""),
            "validity_status": document.metadata.get("validity_status", ""),
            "version": document.metadata.get("version", ""),
            "official_url": document.metadata.get("official_url", ""),
            "text_source_path": document.metadata.get("text_source_path", ""),
            "chunk_index": index,
        })


def summarize(document, rows: list[dict[str, Any]], document_id: str) -> dict[str, Any]:
    source_ids = {block.block_id for block in document.blocks}
    covered_ids = {block_id for row in rows for block_id in row.get("source_block_ids", [])}
    missing_ids = sorted(source_ids - covered_ids)
    unique_bodies = {compact(row.get("body_text") or row.get("text", "")) for row in rows if not row.get("is_overlapping")}
    warnings = list(document.warnings)
    missing_metadata = [
        label for key, label in (("document_title", "文件正式标题"), ("issuing_authority", "发文机关"), ("document_number", "文号"), ("publication_date", "发布日期"), ("validity_status", "效力状态"))
        if not document.metadata.get(key)
    ]
    if missing_metadata:
        warnings.append("元数据仍待补充：" + "、".join(missing_metadata))
    if missing_ids:
        warnings.append(f"有{len(missing_ids)}个源文本单元未通过block_id覆盖校验")
    return {
        "document_id": document_id,
        "file_name": document.file_path.name,
        "file_path": config.repository_path(document.file_path),
        "source_type": document.source_type,
        "status": document.extraction_status,
        "chunk_count": len(rows),
        "source_character_count": sum(body_char_count(block.text) for block in document.blocks),
        "unique_chunk_character_count": sum(len(value) for value in unique_bodies),
        "has_structure": any(row.get("part_title") or row.get("chapter_title") or row.get("section_title") or row.get("article_start") or row.get("attachment_name") for row in rows),
        "coverage_status": "pass" if not missing_ids else "review",
        "missing_block_ids": missing_ids,
        "warnings": warnings,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def resolve_manifest_artifact(manifest_path: Path, value: str) -> Path | None:
    return manifest_path.parent / value if value else None


def relative_artifact(manifest_path: Path, value: Path) -> str:
    try:
        return str(value.resolve().relative_to(manifest_path.parent.resolve()))
    except ValueError:
        return str(value.resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description="中国金融监管法规增量解析与结构化切分器")
    parser.add_argument("--input-dir", type=Path, default=config.INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    parser.add_argument("--document-output-dir", type=Path, default=config.DOCUMENT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=config.MANIFEST_PATH)
    parser.add_argument("--metadata", type=Path, default=config.METADATA_PATH)
    parser.add_argument("--force", action="store_true", help="忽略增量缓存，重新解析和切分所有文件")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前N个文件，用于调试；不应用于正式构建")
    parser.add_argument("--file", action="append", default=[], help="仅处理文件名中包含该文本的文件")
    parser.add_argument("--reparse-file", action="append", default=[], help="强制重新解析匹配文件，其余文档仍复用缓存")
    parser.add_argument("--disable-semantic", action="store_true")
    parser.add_argument("--disable-llm", action="store_true", help="禁用DeepSeek语义边界复核")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    document_output_dir = args.document_output_dir.resolve()
    manifest_path = args.manifest.resolve()
    if not input_dir.exists():
        raise SystemExit(f"输入目录不存在：{input_dir}")
    config.ENABLE_SEMANTIC_CHUNKING = config.ENABLE_SEMANTIC_CHUNKING and not args.disable_semantic
    config.ENABLE_LLM_SEMANTIC_REVIEW = config.ENABLE_LLM_SEMANTIC_REVIEW and not args.disable_llm
    semantic_profile = "deepseek" if config.ENABLE_LLM_SEMANTIC_REVIEW else "local_rules"
    output_dir.mkdir(parents=True, exist_ok=True)
    document_output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    old_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() and not args.force else {"documents": {}}
    old_documents = old_manifest.get("documents", {})
    old_by_relative = {value.get("source_relative_path", ""): value for value in old_documents.values()}
    catalog_rows = load_catalog(args.metadata.resolve())
    catalog_map = catalog_by_filename(catalog_rows)
    inventory = scan_inventory(input_dir)
    excluded_records = {
        clean_name: record for clean_name, record in catalog_map.items()
        if str(record.get("source_status", "")).startswith("excluded_")
    }
    for row in inventory:
        record = excluded_records.get(row["file_name"])
        if record:
            row["selected"] = False
            row["reason"] = record.get("exclusion_reason", "权威目录标记为不进入正式知识库")
    all_files = [path for path in scan_files(input_dir) if path.name not in excluded_records]
    for previous in old_documents.values():
        if previous.get("file_name") not in excluded_records:
            continue
        for key in ("structured_json", "chunk_jsonl"):
            artifact = resolve_manifest_artifact(manifest_path, previous.get(key, ""))
            if artifact and artifact.exists():
                artifact.unlink()
        markdown = output_dir / "markdown" / f"{previous.get('document_id', '')}.md"
        if markdown.exists():
            markdown.unlink()
    files = all_files
    if args.file:
        files = [path for path in files if any(token in path.name for token in args.file)]
    if args.limit:
        files = files[:args.limit]
    partial = len(files) != len(all_files)
    LOGGER.info("待处理文件：%d（目录有效文件：%d）", len(files), len(all_files))

    all_rows: list[dict[str, Any]] = []
    structured_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    new_documents: dict[str, dict[str, Any]] = {}
    selected_paths = {str(path.relative_to(input_dir)) for path in files}

    for position, path in enumerate(all_files, start=1):
        relative = str(path.relative_to(input_dir))
        if partial and relative not in selected_paths:
            previous = old_by_relative.get(relative)
            if previous:
                chunk_path = resolve_manifest_artifact(manifest_path, previous.get("chunk_jsonl", ""))
                structured_path = resolve_manifest_artifact(manifest_path, previous.get("structured_json", ""))
                if chunk_path and chunk_path.exists() and structured_path and structured_path.exists():
                    all_rows.extend(load_jsonl(chunk_path))
                    structured_rows.append(json.loads(structured_path.read_text(encoding="utf-8")))
                    summaries.append(previous.get("summary", {}))
                    new_documents[previous["document_id"]] = previous
            continue

        file_hash = sha256_file(path)
        force_file = any(token in path.name for token in args.reparse_file)
        auxiliary_source = config.OFFICIAL_TEXT_CACHE_DIR / f"{path.stem}.html" if path.suffix.lower() == ".pdf" else None
        auxiliary_hash = sha256_file(auxiliary_source) if auxiliary_source and auxiliary_source.exists() else ""
        parser_version = config.parser_version_for_path(path, uses_official_cache=bool(auxiliary_source and auxiliary_source.exists()))
        catalog_record = resolve_catalog_record(path, catalog_map)
        if not catalog_record:
            LOGGER.warning("未在权威元数据目录匹配：%s", path.name)
        seed_metadata = merge_metadata({}, catalog_record)
        document_id = canonical_document_id(seed_metadata, path)
        previous = old_documents.get(document_id) or old_by_relative.get(relative, {})
        structured_path = document_output_dir / "json" / f"{document_id}.json"
        previous_structured = resolve_manifest_artifact(manifest_path, previous.get("structured_json", ""))
        previous_structured_row: dict[str, Any] = {}
        if previous_structured and previous_structured.exists():
            previous_structured_row = json.loads(previous_structured.read_text(encoding="utf-8"))
        parser_reused = False

        if (
            not args.force and not force_file
            and previous.get("file_sha256") == file_hash
            and previous.get("auxiliary_source_sha256", "") == auxiliary_hash
            and previous.get("parser_version") == parser_version
            and previous_structured and previous_structured.exists()
        ):
            document, _ = load_document(previous_structured, path)
            parser_reused = True
            LOGGER.info("[%d/%d] 复用解析 %s", position, len(all_files), relative)
        else:
            LOGGER.info("[%d/%d] 解析原件 %s", position, len(all_files), relative)
            try:
                document = parse_file(path)
            except Exception as exc:
                LOGGER.exception("解析失败：%s", relative)
                failures.append({"file_name": path.name, "file_path": config.repository_path(path), "reason": str(exc)})
                continue

        document.file_path = path
        document.metadata = merge_metadata(document.metadata, catalog_record)
        document = clean_front_matter(document)
        document_id = previous.get("document_id") or canonical_document_id(document.metadata, path)
        # 权威元数据可能改变规范化 document_id；输出文件名必须跟随最终 ID，
        # 不能继续沿用解析缓存中的旧路径。
        structured_path = document_output_dir / "json" / f"{document_id}.json"
        meta_hash = metadata_hash(document.metadata)
        text_hash = content_hash(document)
        chunker_version = chunker_version_for(document)
        structured_row = document_to_row(document, document_id, file_hash)
        save_document(structured_path, structured_row)
        structured_rows.append(structured_row)

        previous_chunk = resolve_manifest_artifact(manifest_path, previous.get("chunk_jsonl", ""))
        previous_clean_hash = (
            previous.get("clean_text_hash", "")
            or previous_structured_row.get("clean_text_hash", "")
            or clean_text_hash(previous_structured_row.get("clean_text") or previous_structured_row.get("normalized_text", ""))
        )
        chunk_reused = (
            not args.force and previous_clean_hash == structured_row["clean_text_hash"]
            and previous.get("chunker_version") == chunker_version
            and previous.get("semantic_profile") == semantic_profile
            and previous_chunk is not None and previous_chunk.exists()
        )
        drafts = []
        if document.extraction_status != "success" or not document.blocks:
            rows = []
        elif chunk_reused:
            rows = load_jsonl(previous_chunk)
            refresh_chunk_metadata(rows, document, document_id)
            LOGGER.info("[%d/%d] 复用Chunk %s", position, len(all_files), relative)
        else:
            LOGGER.info("[%d/%d] 结构化切分 %s", position, len(all_files), relative)
            drafts, rendered, llm_warnings = chunk_document(document, output_dir / ".semantic_cache.json")
            document.warnings.extend(llm_warnings)
            rows = build_rows(document, drafts, rendered, document_id)

        enrich_chunk_positions(rows, structured_row)
        summary = summarize(document, rows, document_id)
        jsonl_rel, markdown_rel = export_file(output_dir, document_id, path, rows)
        summary["jsonl"] = jsonl_rel
        summary["markdown"] = markdown_rel
        all_rows.extend(rows)
        summaries.append(summary)
        chunk_absolute = output_dir / jsonl_rel
        new_documents[document_id] = {
            "document_id": document_id,
            "source_relative_path": relative,
            "file_name": path.name,
            "file_sha256": file_hash,
            "auxiliary_source_sha256": auxiliary_hash,
            "content_sha256": text_hash,
            "original_text_sha256": document.cleaning.get("original_text_sha256", ""),
            "clean_text_sha256": document.cleaning.get("clean_text_sha256", text_hash),
            "clean_text_hash": structured_row["clean_text_hash"],
            "structured_blocks_sha256": structured_row["structured_blocks_sha256"],
            "structured_schema_version": config.STRUCTURED_SCHEMA_VERSION,
            "cleaning_rule_version": config.CLEANING_RULE_VERSION,
            "cleaning_status": document.cleaning.get("status", "unchanged"),
            "cleaning_rule_hits": document.cleaning.get("rule_hits", []),
            "metadata_sha256": meta_hash,
            "parser_version": parser_version,
            "chunker_version": chunker_version,
            "semantic_profile": semantic_profile,
            "parser_reused": parser_reused,
            "chunk_reused": chunk_reused,
            "structured_json": relative_artifact(manifest_path, structured_path),
            "chunk_jsonl": relative_artifact(manifest_path, chunk_absolute),
            "chunk_ids": [row["chunk_id"] for row in rows],
            "summary": summary,
        }

    if not partial:
        intended_structured = {
            resolve_manifest_artifact(manifest_path, record.get("structured_json", "")).resolve()
            for record in new_documents.values()
            if record.get("structured_json")
        }
        for stale_path in (document_output_dir / "json").glob("*.json"):
            if stale_path.resolve() not in intended_structured:
                stale_path.unlink()
        intended_chunks = {
            resolve_manifest_artifact(manifest_path, record.get("chunk_jsonl", "")).resolve()
            for record in new_documents.values()
            if record.get("chunk_jsonl")
        }
        for stale_path in (output_dir / "jsonl").glob("doc_*.jsonl"):
            if stale_path.resolve() not in intended_chunks:
                stale_path.unlink()
        intended_markdown = {f"{document_id}.md" for document_id in new_documents}
        for stale_path in (output_dir / "markdown").glob("doc_*.md"):
            if stale_path.name not in intended_markdown:
                stale_path.unlink()

    document_ids = list(new_documents)
    if len(document_ids) != len(set(document_ids)):
        raise RuntimeError("发现重复document_id")
    chunk_ids = [row["chunk_id"] for row in all_rows]
    duplicate_ids = [value for value, count in Counter(chunk_ids).items() if count > 1]
    if duplicate_ids:
        raise RuntimeError(f"发现重复chunk_id：{duplicate_ids[:5]}")

    validation = validate_outputs(all_rows, summaries, config.MAX_CHARS)
    export_all(output_dir, all_rows, summaries, failures, validation, inventory)
    export_structured_documents(document_output_dir, structured_rows)
    manifest = {
        "schema_version": 4,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parser_version": config.PARSER_VERSION,
        "chunker_version": config.CHUNKER_VERSION,
        "cleaning_rule_version": config.CLEANING_RULE_VERSION,
        "structured_schema_version": config.STRUCTURED_SCHEMA_VERSION,
        "semantic_profile": semantic_profile,
        "input_dir": config.repository_path(input_dir),
        "metadata_path": config.repository_path(args.metadata),
        "document_count": len(new_documents),
        "chunk_count": len(all_rows),
        "raw_file_count": sum(bool(row.get("selected")) for row in inventory),
        "excluded_sources": [
            {"file_name": record.get("file_name", ""), "source_status": record.get("source_status", ""), "reason": record.get("exclusion_reason", "")}
            for record in excluded_records.values()
        ],
        "documents": new_documents,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    failed_count = len(failures) + sum(row.get("status") == "failed" for row in summaries)
    result = {
        "scanned": len(inventory), "files": len(new_documents), "success": sum(row.get("status") == "success" for row in summaries),
        "needs_ocr": sum(row.get("status") == "needs_ocr" for row in summaries), "failed": failed_count,
        "chunks": len(all_rows), "oversized": sum(row.get("is_oversized") for row in all_rows),
        "overlapping": sum(row.get("is_overlapping") for row in all_rows), "validation_passed": validation["passed"],
        "quality_critical": validation.get("severity_counts", {}).get("critical", 0),
        "quality_major": validation.get("severity_counts", {}).get("major", 0),
        "quality_minor": validation.get("severity_counts", {}).get("minor", 0),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failed_count and validation["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
