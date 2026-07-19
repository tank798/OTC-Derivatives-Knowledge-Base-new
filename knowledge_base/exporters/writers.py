from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from utils.text import safe_stem


CSV_FIELDS = [
    "chunk_id", "document_id", "file_name", "file_path", "document_title", "document_title_source", "issuing_authority",
    "document_number", "publication_date", "effective_date", "validity_status", "version",
    "part_title", "chapter_title", "section_title", "article_start", "article_end",
    "paragraph_range", "attachment_name", "chunk_index", "character_count", "is_overlapping",
    "overlap_source_chunk_id", "overlap_left", "overlap_right", "start_char", "end_char",
    "source_page_start", "source_page_end", "clean_text_hash", "chunk_hash",
    "is_oversized", "oversized_reason", "source_type", "official_url", "text_preview",
]


def export_file(output_dir: Path, document_id: str, source_path: Path, chunks: list[dict[str, Any]]) -> tuple[str, str]:
    jsonl_rel = f"jsonl/{document_id}.jsonl"
    markdown_rel = f"markdown/{document_id}.md"
    jsonl_path = output_dir / jsonl_rel
    markdown_path = output_dir / markdown_rel
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in chunks:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    lines = [f"# {source_path.name}", ""]
    for row in chunks:
        lines.extend([
            f"## Chunk {row['chunk_index']:03d}", "",
            f"- 文件名称：{row['document_title']}",
            f"- 发文机关：{row['issuing_authority']}",
            f"- 文号：{row['document_number']}",
            f"- 章：{row['chapter_title']}",
            f"- 节：{row['section_title']}",
            f"- 条款范围：{row['article_start']}" + (f" 至 {row['article_end']}" if row['article_end'] and row['article_end'] != row['article_start'] else ""),
            f"- 字符数：{row['character_count']}",
            f"- 是否包含重叠：{'是' if row['is_overlapping'] else '否'}",
            f"- 是否超过上限：{'是' if row['is_oversized'] else '否'}",
            "", "正文：", "", row["text"], "",
        ])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return jsonl_rel, markdown_rel


def export_all(output_dir: Path, chunks: list[dict[str, Any]], summaries: list[dict[str, Any]], failures: list[dict[str, str]], validation: dict[str, Any], inventory: list[dict[str, Any]]) -> None:
    jsonl_dir = output_dir / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    with (jsonl_dir / "all_chunks.jsonl").open("w", encoding="utf-8") as handle:
        for row in chunks:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (output_dir / "chunk_index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in chunks:
            output = {key: row.get(key, "") for key in CSV_FIELDS}
            output["text_preview"] = row.get("text", "")[:200].replace("\n", " ")
            writer.writerow(output)
    (output_dir / "自动校验结果.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    issue_fields = ["severity", "check", "file_name", "document_id", "chunk_id", "detail"]
    with (output_dir / "Chunk质量问题.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=issue_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: issue.get(field, "") for field in issue_fields} for issue in validation.get("issues", []))
    with (output_dir / "文件扫描清单.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file_name", "file_path", "suffix", "size_bytes", "selected", "reason"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory)
    counts = [int(row.get("character_count", 0)) for row in chunks]
    oversized = [row for row in chunks if row.get("is_oversized")]
    overlaps = [row for row in chunks if row.get("is_overlapping")]
    no_structure = [row for row in summaries if not row.get("has_structure") and row.get("status") == "success"]
    needs_ocr = [row for row in summaries if row.get("status") == "needs_ocr"]
    warnings = [row for row in summaries if row.get("warnings")]
    lines = [
        "# 知识库切分报告", "",
        "## 总体结果", "",
        f"- 目录扫描文件总数：{len(inventory)}",
        f"- 纳入处理文件数：{sum(bool(row['selected']) for row in inventory)}",
        f"- 忽略非业务或临时文件：{sum(not bool(row['selected']) for row in inventory)}",
        f"- 成功处理文件数：{sum(row.get('status') == 'success' for row in summaries)}",
        f"- 需要OCR或人工复核：{len(needs_ocr)}",
        f"- 失败文件数：{len(failures) + sum(row.get('status') == 'failed' for row in summaries)}",
        f"- 文本块总数：{len(chunks)}",
        f"- 平均正文字符数：{mean(counts):.1f}" if counts else "- 平均正文字符数：0",
        f"- 中位数正文字符数：{median(counts):.1f}" if counts else "- 中位数正文字符数：0",
        f"- 最大正文字符数：{max(counts) if counts else 0}",
        f"- 超限块：{len(oversized)}",
        f"- 包含结构化重叠的块：{len(overlaps)}", "",
        "## 扫描口径", "",
        "完整逐文件清单见 `文件扫描清单.csv`。`.DS_Store`、Word/Office 临时锁文件和不支持的扩展名不进入正文切分。", "",
        "## 自动验收", "",
        f"- 总体结果：{'通过' if validation.get('passed') else '需要复核'}",
        f"- Critical：{validation.get('severity_counts', {}).get('critical', 0)}",
        f"- Major：{validation.get('severity_counts', {}).get('major', 0)}",
        f"- Minor：{validation.get('severity_counts', {}).get('minor', 0)}",
    ]
    lines.extend(f"- {name}：{'通过' if passed else '未通过'}" for name, passed in validation.get("checks", {}).items())
    lines.extend([
        "",
        "## 逐文件结果", "",
        "| 文件 | 类型 | 状态 | 块数 | 原文字符 | 非重叠块字符 | 结构 | 覆盖校验 | 问题 |",
        "|---|---|---|---:|---:|---:|---|---|---|",
    ])
    for row in summaries:
        lines.append(
            f"| {row['file_name']} | {row['source_type']} | {row['status']} | {row['chunk_count']} | "
            f"{row.get('source_character_count', 0)} | {row.get('unique_chunk_character_count', 0)} | "
            f"{'已识别' if row.get('has_structure') else '未识别'} | {row.get('coverage_status', '')} | "
            f"{'；'.join(row.get('warnings', []))[:240]} |"
        )
    lines.extend(["", "## 超限块", ""])
    if oversized:
        lines.extend(["| chunk_id | 文件 | 字符数 | 原因 |", "|---|---|---:|---|"])
        lines.extend(f"| {row['chunk_id']} | {row['file_name']} | {row['character_count']} | {row['oversized_reason']} |" for row in oversized)
    else:
        lines.append("无。")
    lines.extend(["", "## 未识别出章节或条款结构的文件", ""])
    lines.extend(f"- {row['file_name']}" for row in no_structure) if no_structure else lines.append("无。")
    lines.extend(["", "## 空白或疑似扫描件", ""])
    lines.extend(f"- {row['file_name']}：{'；'.join(row.get('warnings', []))}" for row in needs_ocr) if needs_ocr else lines.append("无。")
    lines.extend(["", "## 解析失败", ""])
    lines.extend(f"- {row['file_name']}：{row['reason']}" for row in failures) if failures else lines.append("无。")
    lines.extend(["", "## 需要人工复核的解析提示", ""])
    lines.extend(f"- {row['file_name']}：{'；'.join(row.get('warnings', []))}" for row in warnings) if warnings else lines.append("无。")
    lines.extend(["", "## Chunk质量问题", ""])
    if validation.get("issues"):
        lines.extend(["| 级别 | 检查项 | 文件 | Chunk | 说明 |", "|---|---|---|---|---|"])
        for issue in validation["issues"]:
            lines.append(f"| {issue.get('severity', '')} | {issue.get('check', '')} | {issue.get('file_name', '')} | {issue.get('chunk_id', '')} | {issue.get('detail', '')} |")
    else:
        lines.append("无。")
    (output_dir / "切分报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_structured_documents(output_dir: Path, documents: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "all_documents.jsonl").open("w", encoding="utf-8") as handle:
        for row in sorted(documents, key=lambda item: item["document_id"]):
            compact_row = {key: value for key, value in row.items() if key != "blocks"}
            compact_row["block_count"] = len(row.get("blocks", []))
            handle.write(json.dumps(compact_row, ensure_ascii=False, sort_keys=True) + "\n")
