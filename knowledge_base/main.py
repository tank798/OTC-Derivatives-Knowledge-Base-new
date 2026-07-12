from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
from pathlib import Path
import sys
from typing import Any

import config
from chunkers import chunk_document
from exporters import export_all, export_file
from parsers import parse_file
from utils.text import body_char_count, safe_stem, sha256_file, stable_id
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
        reason = ""
        if temporary:
            reason = "系统或Office临时文件"
        elif not supported:
            reason = "不支持的文件类型"
        rows.append({"file_name": path.name, "file_path": str(path.resolve()), "suffix": path.suffix.lower(), "size_bytes": path.stat().st_size, "selected": selected, "reason": reason})
    return rows


def build_rows(document, drafts, rendered, file_hash: str) -> list[dict[str, Any]]:
    relative = str(document.file_path.resolve().relative_to(config.PROJECT_ROOT.resolve()))
    document_id = "doc_" + stable_id(relative, file_hash)
    rows: list[dict[str, Any]] = []
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
        row = {
            "chunk_id": "chunk_" + stable_id(document_id, str(index), body),
            "document_id": document_id,
            "file_name": document.file_path.name,
            "file_path": str(document.file_path.resolve()),
            "document_title": document.metadata.get("document_title", ""),
            "document_title_source": document.metadata.get("document_title_source", ""),
            "issuing_authority": document.metadata.get("issuing_authority", ""),
            "document_number": document.metadata.get("document_number", ""),
            "publication_date": document.metadata.get("publication_date", ""),
            "effective_date": document.metadata.get("effective_date", ""),
            "validity_status": document.metadata.get("validity_status", ""),
            "version": document.metadata.get("version", ""),
            "part_title": draft.hierarchy.get("part_title", ""),
            "chapter_title": draft.hierarchy.get("chapter_title", ""),
            "section_title": draft.hierarchy.get("section_title", ""),
            "article_start": article_values[0] if article_values else "",
            "article_end": article_ends[-1] if article_ends else "",
            "paragraph_range": "",
            "attachment_name": attachment,
            "chunk_index": index,
            "character_count": body_char_count(body),
            "is_overlapping": draft.is_overlapping,
            "overlap_source_chunk_id": "",
            "is_oversized": draft.is_oversized or body_char_count(body) > config.MAX_CHARS,
            "oversized_reason": draft.oversized_reason or ("切分后完整语义或表格单元仍超过上限" if body_char_count(body) > config.MAX_CHARS else ""),
            "source_type": document.source_type,
            "source_block_ids": sorted({block_id for unit in draft.units for block_id in unit.block_ids}),
            "text": text_values["text"],
        }
        rows.append(row)
    for index, draft in enumerate(drafts):
        if draft.overlap_source_index is not None and 0 <= draft.overlap_source_index < len(rows):
            rows[index]["overlap_source_chunk_id"] = rows[draft.overlap_source_index]["chunk_id"]
    return rows


def summarize(document, rows: list[dict[str, Any]], drafts) -> dict[str, Any]:
    source_ids = {block.block_id for block in document.blocks}
    covered_ids = {block_id for row in rows for block_id in row.get("source_block_ids", [])}
    source_chars = sum(body_char_count(block.text) for block in document.blocks)
    unique_units = {}
    for draft in drafts:
        for unit in draft.units:
            unique_units.setdefault(unit.sequence_index, unit.body_text)
    unique_chars = sum(body_char_count(text) for text in unique_units.values())
    has_structure = any(row["part_title"] or row["chapter_title"] or row["section_title"] or row["article_start"] or row["attachment_name"] for row in rows)
    missing_ids = sorted(source_ids - covered_ids)
    warnings = list(document.warnings)
    missing_metadata = [
        label for key, label in (("document_title", "文件正式标题"), ("issuing_authority", "发文机关"), ("document_number", "文号"), ("publication_date", "发布日期"), ("effective_date", "实施日期"), ("validity_status", "效力状态"))
        if not document.metadata.get(key)
    ]
    if missing_metadata:
        warnings.append("未能从原文明确确认元数据：" + "、".join(missing_metadata))
    if missing_ids:
        warnings.append(f"有{len(missing_ids)}个源文本单元未通过block_id覆盖校验")
    return {
        "file_name": document.file_path.name,
        "file_path": str(document.file_path.resolve()),
        "source_type": document.source_type,
        "status": document.extraction_status,
        "chunk_count": len(rows),
        "source_character_count": source_chars,
        "unique_chunk_character_count": unique_chars,
        "has_structure": has_structure,
        "coverage_status": "pass" if not missing_ids else "review",
        "missing_block_ids": missing_ids,
        "warnings": warnings,
    }


def process_file(path: Path, semantic_cache_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    file_hash = sha256_file(path)
    document = parse_file(path)
    if document.extraction_status != "success" or not document.blocks:
        return [], summarize(document, [], [])
    drafts, rendered, llm_warnings = chunk_document(document, semantic_cache_path)
    document.warnings.extend(llm_warnings)
    rows = build_rows(document, drafts, rendered, file_hash)
    return rows, summarize(document, rows, drafts)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="中国金融监管法规结构化切分器")
    parser.add_argument("--input-dir", type=Path, default=config.INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    parser.add_argument("--force", action="store_true", help="忽略增量缓存，重新处理所有文件")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前N个文件，用于调试")
    parser.add_argument("--file", action="append", default=[], help="仅处理文件名中包含该文本的文件")
    parser.add_argument("--disable-semantic", action="store_true")
    parser.add_argument("--disable-llm", action="store_true", help="禁用DeepSeek语义边界复核")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not input_dir.exists():
        raise SystemExit(f"输入目录不存在：{input_dir}")
    config.ENABLE_SEMANTIC_CHUNKING = config.ENABLE_SEMANTIC_CHUNKING and not args.disable_semantic
    config.ENABLE_LLM_SEMANTIC_REVIEW = config.ENABLE_LLM_SEMANTIC_REVIEW and not args.disable_llm
    semantic_profile = "deepseek" if config.ENABLE_LLM_SEMANTIC_REVIEW else "local_rules"
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / ".incremental_state.json"
    old_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() and not args.force else {"files": {}}
    inventory = scan_inventory(input_dir)
    files = scan_files(input_dir)
    if args.file:
        files = [path for path in files if any(token in path.name for token in args.file)]
    if args.limit:
        files = files[:args.limit]
    LOGGER.info("待处理文件：%d", len(files))
    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    new_state = {"parser_version": config.PARSER_VERSION, "files": {}}
    for position, path in enumerate(files, start=1):
        relative = str(path.relative_to(input_dir))
        file_hash = sha256_file(path)
        previous = old_state.get("files", {}).get(relative, {})
        previous_jsonl = output_dir / previous.get("jsonl", "") if previous.get("jsonl") else None
        if not args.force and previous.get("sha256") == file_hash and previous.get("parser_version") == config.PARSER_VERSION and previous.get("semantic_profile") == semantic_profile and previous_jsonl and previous_jsonl.exists():
            rows = load_jsonl(previous_jsonl)
            summary = previous.get("summary", {})
            LOGGER.info("[%d/%d] 增量复用 %s", position, len(files), relative)
        else:
            LOGGER.info("[%d/%d] 解析切分 %s", position, len(files), relative)
            try:
                rows, summary = process_file(path, output_dir / ".semantic_cache.json")
            except Exception as exc:
                LOGGER.exception("处理失败：%s", relative)
                failures.append({"file_name": path.name, "file_path": str(path.resolve()), "reason": str(exc)})
                continue
            jsonl_rel, markdown_rel = export_file(output_dir, path, rows)
            summary["jsonl"] = jsonl_rel
            summary["markdown"] = markdown_rel
        summaries.append(summary)
        all_rows.extend(rows)
        new_state["files"][relative] = {"sha256": file_hash, "parser_version": config.PARSER_VERSION, "semantic_profile": semantic_profile, "jsonl": summary.get("jsonl", previous.get("jsonl", "")), "markdown": summary.get("markdown", previous.get("markdown", "")), "summary": summary}
    chunk_ids = [row["chunk_id"] for row in all_rows]
    duplicate_ids = [value for value, count in Counter(chunk_ids).items() if count > 1]
    if duplicate_ids:
        raise RuntimeError(f"发现重复chunk_id：{duplicate_ids[:5]}")
    invalid_limits = [row for row in all_rows if row["character_count"] > config.MAX_CHARS and not row["is_oversized"]]
    if invalid_limits:
        raise RuntimeError(f"发现未标记的超限块：{len(invalid_limits)}")
    validation = validate_outputs(all_rows, summaries, config.MAX_CHARS)
    export_all(output_dir, all_rows, summaries, failures, validation, inventory)
    state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed_count = len(failures) + sum(row.get("status") == "failed" for row in summaries)
    result = {"scanned": len(inventory), "files": len(files), "ignored": sum(not row["selected"] for row in inventory), "success": sum(row.get("status") == "success" for row in summaries), "needs_ocr": sum(row.get("status") == "needs_ocr" for row in summaries), "failed": failed_count, "chunks": len(all_rows), "oversized": sum(row["is_oversized"] for row in all_rows), "overlapping": sum(row["is_overlapping"] for row in all_rows), "validation_passed": validation["passed"]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failed_count else 2


if __name__ == "__main__":
    sys.exit(main())
