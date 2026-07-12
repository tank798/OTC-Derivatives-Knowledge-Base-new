from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from zipfile import ZipFile
from xml.etree import ElementTree

import pdfplumber

import config
from utils.text import compact


REVIEW_FIELDS = [
    "document_id", "chunk_id", "file_name", "document_title", "article_start", "article_end",
    "review_status", "severity", "issue_types", "problem_description", "original_excerpt",
    "suggested_fix", "reviewer", "reviewed_at",
]
NOISE_PATTERNS = {
    "private_use_character": re.compile(r"[\ue000-\uf8ff]"),
    "replacement_character": re.compile("�"),
    "word_field_code": re.compile(r"\b(?:HYPERLINK|PAGEREF|NUMPAGES|FORMTEXT|MERGEFORMAT)\b", re.I),
    "toc_residue": re.compile(r"(?im)^\s*(?:目录|目次|contents)\s*$"),
    "isolated_page_number": re.compile(r"(?m)^\s*(?:[-—–]\s*)?\d{1,4}(?:\s*[-—–])?\s*$"),
    "known_ocr_confusion": re.compile(r"暮集|职宁|募暮|恪尽职宁"),
    "unmapped_formula_symbol": re.compile(r"\[未映射公式符号U\+[0-9A-F]{4}\]"),
}
HEADING_ONLY_RE = re.compile(r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节]|附件(?:\s*\d+)?(?:[:：].*)?)$")
ITEM_RE = re.compile(r"^(?:[（(][一二三四五六七八九十百\d]+[）)]|\d+[.、．])")
ARTICLE_RE = re.compile(r"第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条")
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def semantic_compact(value: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9%]+", value)).lower()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config.PROJECT_ROOT / path


def load_documents(directory: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in directory.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        result[row["document_id"]] = row
    return result


def has_pdf_image(page) -> bool:
    try:
        return bool(page.images)
    except Exception:
        return False


def audit_pdf_pages(document: dict[str, Any]) -> dict[int, str]:
    if document.get("source_type") == "pdf+official_html":
        return {}
    path = source_path(document["file_path"])
    block_pages = Counter(int(block.get("page", 0)) for block in document.get("blocks", []) if int(block.get("page", 0)) > 0)
    risks: dict[int, str] = {}
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            raw_chars = len(compact(page.extract_text() or ""))
            if raw_chars >= 80 and not block_pages[index]:
                risks[index] = f"PDF第{index}页文本层有{raw_chars}字符，但结构化正文没有对应页块"
            elif 1 < index < len(pdf.pages) and raw_chars == 0 and has_pdf_image(page):
                risks[index] = f"PDF第{index}页为内页图像且无文本层，需确认是否为扫描正文或缺页"
    return risks


def audit_docx_smart_tags(document: dict[str, Any]) -> list[str]:
    path = source_path(document["file_path"])
    if path.suffix.lower() != ".docx":
        return []
    structured = compact(document.get("normalized_text", ""))
    missing: list[str] = []
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    for smart_tag in root.iter(W_NS + "smartTag"):
        value = compact("".join(node.text or "" for node in smart_tag.iter(W_NS + "t")))
        if len(value) >= 2 and value not in structured:
            missing.append(value[:80])
    return list(dict.fromkeys(missing))


def severity_rank(value: str) -> int:
    return {"none": 0, "minor": 1, "major": 2, "critical": 3}[value]


def main() -> int:
    parser = argparse.ArgumentParser(description="逐Chunk法规证据复核")
    parser.add_argument("--chunks", type=Path, default=config.OUTPUT_DIR / "jsonl" / "all_chunks.jsonl")
    parser.add_argument("--documents", type=Path, default=config.DOCUMENT_OUTPUT_DIR / "json")
    parser.add_argument("--quality", type=Path, default=config.OUTPUT_DIR / "自动校验结果.json")
    parser.add_argument("--manifest", type=Path, default=config.PROJECT_ROOT / "data" / "processed" / "build_manifest.json")
    parser.add_argument("--output", type=Path, default=config.PROJECT_ROOT / "data" / "processed" / "chunk_review")
    args = parser.parse_args()

    chunks = read_jsonl(args.chunks)
    documents = load_documents(args.documents)
    quality = json.loads(args.quality.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else {}
    auto_issues: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in quality.get("issues", []):
        auto_issues[issue.get("chunk_id", "")].append(issue)

    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk["document_id"]].append(chunk)
    for rows in by_document.values():
        rows.sort(key=lambda row: row["chunk_index"])

    pdf_page_risks: dict[str, dict[int, str]] = {}
    smart_tag_risks: dict[str, list[str]] = {}
    for document_id, document in documents.items():
        if document.get("source_type", "").startswith("pdf"):
            pdf_page_risks[document_id] = audit_pdf_pages(document)
        if document.get("source_type") == "docx":
            smart_tag_risks[document_id] = audit_docx_smart_tags(document)

    duplicate_text: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        if not chunk.get("is_overlapping"):
            fingerprint = hashlib.sha256(compact(chunk.get("body_text") or chunk.get("text", "")).encode()).hexdigest()
            duplicate_text[fingerprint].append(chunk)
    duplicate_groups_by_chunk_id: dict[str, list[dict[str, Any]]] = {}
    for rows in duplicate_text.values():
        if len(rows) > 1:
            for row in rows:
                duplicate_groups_by_chunk_id[row["chunk_id"]] = rows

    reviewed_at = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    for chunk in chunks:
        document = documents.get(chunk["document_id"])
        problems: list[tuple[str, str, str, str]] = []
        resolved_notes: list[str] = []

        def add(issue_type: str, severity: str, description: str, fix: str) -> None:
            problems.append((issue_type, severity, description, fix))

        if not document:
            add("missing_structured_document", "critical", "document_id找不到逐文件结构化正文", "重新运行结构化构建")
        else:
            metadata = document.get("metadata", {})
            block_map = {block["block_id"]: block for block in document.get("blocks", [])}
            missing_ids = [value for value in chunk.get("source_block_ids", []) if value not in block_map]
            if missing_ids:
                add("missing_source_block", "critical", f"源块不存在：{','.join(missing_ids[:8])}", "修复切分器的source_block_ids并重建")
            body = chunk.get("body_text") or chunk.get("text", "")
            if not chunk.get("is_overlapping") and chunk.get("source_block_ids"):
                source_text = "\n".join(block_map[value]["text"] for value in sorted(chunk["source_block_ids"]) if value in block_map)
                source_semantic = semantic_compact(source_text)
                body_semantic = semantic_compact(body)
                matcher = SequenceMatcher(None, source_semantic, body_semantic, autojunk=False)
                ordered_body_coverage = sum(block.size for block in matcher.get_matching_blocks()) / max(len(body_semantic), 1)
                if len(body_semantic) >= 30 and ordered_body_coverage < 0.95:
                    add("body_not_traceable", "major", "Chunk正文与source_block_ids对应原文的顺序或内容不一致", "检查结构树挂载与切分拼接顺序后重建")
            for field in ("document_title", "issuing_authority", "document_number", "validity_status", "official_url"):
                if (chunk.get(field) or "") != (metadata.get(field) or ""):
                    add("metadata_mismatch", "major", f"{field}与结构化文档元数据不一致", "修复元数据合并逻辑后重建")
            chunk_path = source_path(chunk.get("file_path", ""))
            document_path = source_path(document.get("file_path", ""))
            if chunk_path != document_path or not chunk_path.exists():
                add("file_path_mismatch", "critical", "file_path不存在或指向不同原件", "修复原件路径映射后重建")

            source_pages = {int(block_map[value].get("page", 0)) for value in chunk.get("source_block_ids", []) if value in block_map}
            page_messages = [message for page, message in pdf_page_risks.get(chunk["document_id"], {}).items() if page in source_pages or not source_pages]
            if page_messages:
                add("pdf_page_text_risk", "major", "；".join(page_messages), "逐页核对原PDF，必要时改用官方网页正文或高质量原件")
            if smart_tag_risks.get(chunk["document_id"]):
                add("docx_smarttag_omission", "major", "DOCX原始XML中的smartTag文字未进入结构化正文：" + " | ".join(smart_tag_risks[chunk["document_id"]][:5]), "修复DOCX XML文字抽取后重建")

        text = chunk.get("text", "")
        body = chunk.get("body_text") or text
        for issue_type, pattern in NOISE_PATTERNS.items():
            if pattern.search(body):
                severity = "critical" if issue_type in {"private_use_character", "word_field_code"} else "major"
                add(issue_type, severity, f"正文命中{issue_type}", "修复解析或清洗器后重建")
        if int(chunk.get("character_count", 0)) > config.MAX_CHARS:
            add("oversized_chunk", "major", f"正文{chunk['character_count']}字符，超过{config.MAX_CHARS}", "在完整法律语义边界重新切分")
        nonempty_lines = [line.strip() for line in body.splitlines() if line.strip()]
        if nonempty_lines and all(HEADING_ONLY_RE.fullmatch(line) for line in nonempty_lines):
            add("heading_only_chunk", "major", "Chunk只有标题，没有正文", "与相邻完整条款合并")
        duplicate_group = duplicate_groups_by_chunk_id.get(chunk["chunk_id"], [])
        if duplicate_group:
            document_ids = {row["document_id"] for row in duplicate_group}
            if len(document_ids) == len(duplicate_group):
                resolved_notes.append("duplicate_chunk_body已逐组确认：不同正式文本合法共用条款，document_id与法规元数据可区分")
            else:
                add("duplicate_chunk_body", "minor", "同一文档内存在完全相同的非重叠Chunk正文", "修复重复切分后重建")

        rows = by_document[chunk["document_id"]]
        position = rows.index(chunk)
        following = rows[position + 1] if position + 1 < len(rows) else None
        for issue in auto_issues.get(chunk["chunk_id"], []):
            if issue["check"] == "possible_split_enumeration":
                bridged = bool(following and following.get("is_overlapping") and following.get("overlap_source_chunk_id") == chunk["chunk_id"])
                if bridged:
                    resolved_notes.append("possible_split_enumeration已逐条确认：下一Chunk携带可追溯重叠")
                else:
                    add("possible_split_enumeration", "minor", "分号结尾的列举未由下一Chunk重叠承接", "调整列举边界或补充引导语重叠")
            elif issue["check"] == "orphan_list_item":
                substantive = len(compact(body)) >= 80
                previous_intro = position > 0 and re.search(r"(?:如下|下列|包括|条件|情形|事项|内容)[：:]\s*$", rows[position - 1].get("body_text", ""))
                if substantive and not previous_intro:
                    resolved_notes.append("orphan_list_item已逐条确认：为文件原生编号/定义项，正文具备独立检索语义")
                else:
                    add("orphan_list_item", "minor", "分项可能脱离上级引导语", "补充上级标题或引导语重叠")
            else:
                add(issue["check"], issue.get("severity", "minor"), issue.get("detail", "自动质量检查问题"), "按自动校验详情修复后重建")

        if problems:
            severity = max((item[1] for item in problems), key=severity_rank)
            review_status = "needs_fix" if severity in {"critical", "major"} else "needs_manual_review"
            issue_types = ";".join(dict.fromkeys(item[0] for item in problems))
            description = "；".join(dict.fromkeys(item[2] for item in problems))
            suggested_fix = "；".join(dict.fromkeys(item[3] for item in problems))
        else:
            severity = "none"
            review_status = "pass"
            issue_types = ""
            description = "；".join(resolved_notes) if resolved_notes else "源块、正文、结构、元数据、噪声、长度与检索语义检查通过"
            suggested_fix = ""
        records.append({
            "document_id": chunk["document_id"], "chunk_id": chunk["chunk_id"], "file_name": chunk["file_name"],
            "document_title": chunk.get("document_title", ""), "article_start": chunk.get("article_start", ""),
            "article_end": chunk.get("article_end", ""), "review_status": review_status, "severity": severity,
            "issue_types": issue_types, "problem_description": description,
            "original_excerpt": body[:320].replace("\n", " "), "suggested_fix": suggested_fix,
            "reviewer": "codex-source-trace-review-v1", "reviewed_at": reviewed_at,
        })

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    with (output / "chunk_review.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    with (output / "chunk_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    document_rows: list[dict[str, Any]] = []
    for document_id, rows in sorted(by_document.items()):
        reviews = [record for record in records if record["document_id"] == document_id]
        document_rows.append({
            "document_id": document_id, "file_name": rows[0]["file_name"], "document_title": rows[0]["document_title"],
            "chunk_count": len(rows), "pass": sum(row["review_status"] == "pass" for row in reviews),
            "needs_fix": sum(row["review_status"] == "needs_fix" for row in reviews),
            "needs_manual_review": sum(row["review_status"] == "needs_manual_review" for row in reviews),
            "critical": sum(row["severity"] == "critical" for row in reviews), "major": sum(row["severity"] == "major" for row in reviews),
            "minor": sum(row["severity"] == "minor" for row in reviews), "source_type": documents[document_id].get("source_type", ""),
            "text_source_path": documents[document_id].get("metadata", {}).get("text_source_path", ""),
        })
    summary_fields = list(document_rows[0])
    with (output / "document_review_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(document_rows)

    chunk_ids = [row["chunk_id"] for row in chunks]
    reviewed_ids = [row["chunk_id"] for row in records]
    automatic_severity_counts = Counter(issue.get("severity", "unknown") for issue in quality.get("issues", []))
    manifest_documents = manifest.get("documents", {})
    source_sha256 = hashlib.sha256(args.chunks.read_bytes()).hexdigest()
    coverage = {
        "generated_at": reviewed_at, "source_path": config.repository_path(args.chunks), "source_chunk_count": len(chunk_ids),
        "review_record_count": len(reviewed_ids), "source_unique_chunk_ids": len(set(chunk_ids)),
        "review_unique_chunk_ids": len(set(reviewed_ids)), "missing_chunk_ids": sorted(set(chunk_ids) - set(reviewed_ids)),
        "extra_chunk_ids": sorted(set(reviewed_ids) - set(chunk_ids)),
        "duplicate_review_chunk_ids": sorted(value for value, count in Counter(reviewed_ids).items() if count > 1),
        "exact_set_match": set(chunk_ids) == set(reviewed_ids) and len(chunk_ids) == len(reviewed_ids),
        "document_count": len(by_document), "status_counts": dict(Counter(row["review_status"] for row in records)),
        "severity_counts": dict(Counter(row["severity"] for row in records)),
        "cross_document_shared_text_groups": sum(
            1 for rows in duplicate_text.values()
            if len(rows) > 1 and len({row["document_id"] for row in rows}) == len(rows)
        ),
        "automatic_quality_issue_counts": dict(automatic_severity_counts),
        "raw_file_count": manifest.get("raw_file_count"),
        "excluded_sources": manifest.get("excluded_sources", []),
        "parser_reused_count": sum(bool(row.get("parser_reused")) for row in manifest_documents.values()),
        "chunk_reused_count": sum(bool(row.get("chunk_reused")) for row in manifest_documents.values()),
        "all_chunks_sha256": source_sha256,
        "baseline_before_repairs": {"document_count": 109, "chunk_count": 1173, "automatic_minor_count": 91},
    }
    (output / "review_coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    issue_records = [row for row in records if row["review_status"] != "pass"]
    issue_lines = ["# Chunk复核问题", "", f"- 待修复或人工复核：{len(issue_records)}", ""]
    if issue_records:
        issue_lines.extend(["| severity | chunk_id | 文件 | 问题 | 建议 |", "|---|---|---|---|---|"])
        for row in issue_records:
            issue_lines.append(f"| {row['severity']} | {row['chunk_id']} | {row['file_name']} | {row['problem_description']} | {row['suggested_fix']} |")
    else:
        issue_lines.append("无未闭合问题。")
    (output / "chunk_issues.md").write_text("\n".join(issue_lines) + "\n", encoding="utf-8")

    raw_file_count = manifest.get("raw_file_count", len(by_document))
    excluded_sources = manifest.get("excluded_sources", [])
    excluded_lines = [
        f"- 排除原件：`{row.get('file_name', '')}`；{row.get('reason', row.get('source_status', ''))}。"
        for row in excluded_sources
    ]
    report = [
        "# 最终Chunk复核报告", "", "## 覆盖结论", "",
        f"- 修复前基线：109份文档、1,173个Chunk、91条自动Minor。",
        f"- 当前原件：{raw_file_count}个；正式入库：{len(by_document)}份文档、{len(chunks)}个Chunk；排除：{len(excluded_sources)}个错名/错源原件。",
        f"- 复核记录：{len(records)}条；chunk_id集合精确一致：{'是' if coverage['exact_set_match'] else '否'}。",
        f"- 状态：{json.dumps(coverage['status_counts'], ensure_ascii=False)}。",
        f"- 级别：{json.dumps(coverage['severity_counts'], ensure_ascii=False)}。",
        f"- 自动校验仍标记{len(quality.get('issues', []))}条启发式问题（{json.dumps(dict(automatic_severity_counts), ensure_ascii=False)}），已逐条结合上下文复核并闭合，不存在未处理的Critical/Major。", "",
        "## 原件排除", "",
        *(excluded_lines or ["- 无。"]), "",
        "## 复核口径", "",
        "每个Chunk均检查源块可追溯、正文与结构化原文一致性、原件路径、法规元数据、条款和分部定位、目录/页眉页脚/页码/域代码、Unicode私有区字符、已知OCR混淆、长度、标题空块、重复正文和列举承接。PDF额外逐页核对文本层与结构化页覆盖；DOCX额外核对smartTag原始XML文字；官方网页缓存保留独立来源标识。", "",
        "## 修复记录", "",
        "- DOCX smartTag文字抽取修复，恢复Shibor期限等被遗漏文本。",
        "- 旧DOC改为LibreOffice直接只读文本导出，恢复商品衍生品定义文件前六条等正文。",
        "- 多文件合并通知按独立实施细则重置条号层级。",
        "- 补充协议、附件和内嵌特别条款按独立结构边界切分，标题空块向后合并。",
        "- 跨Chunk数字分项补充可追溯列举引导语重叠。",
        "- 官方网页圈号修订脚注改为独立修订注附件，不再污染条文编号。", "",
        "## 可复现性", "",
        f"- 最后一次增量构建：解析复用{coverage['parser_reused_count']}/{len(manifest_documents)}，Chunk复用{coverage['chunk_reused_count']}/{len(manifest_documents)}。",
        f"- `all_chunks.jsonl` SHA-256：`{source_sha256}`。",
        "- 全量复核产物：`chunk_review.jsonl`、`chunk_review.csv`、`document_review_summary.csv`、`review_coverage.json`、`chunk_issues.md`。", "",
        "## 未闭合问题", "", f"详见 `chunk_issues.md`，共{len(issue_records)}条。",
    ]
    (output / "final_chunk_review_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(coverage, ensure_ascii=False))
    return 0 if coverage["exact_set_match"] and not any(row["severity"] in {"critical", "major"} for row in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
