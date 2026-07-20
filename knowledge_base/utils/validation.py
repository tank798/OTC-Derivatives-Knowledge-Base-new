from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
import re

from utils.text import compact


CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
TOC_HEADING_RE = re.compile(r"(?im)^\s*(?:目录|目次|contents)\s*$")
TOC_ENTRY_RE = re.compile(r"(?m)^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节条款]|[一二三四五六七八九十百]+[、.]|\d+[、.]).{0,100}(?:\.{2,}|[…·]{2,})\s*\d{1,4}\s*$")
HEADING_ONLY_RE = re.compile(r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节](?:\s+.{0,60})?|附件(?:\s*\d+)?(?:[:：].{0,60})?)$")
ITEM_START_RE = re.compile(r"^[（(][一二三四五六七八九十百\d]+[）)]|^\d+[.、．]")
WORD_FIELD_RE = re.compile(r"\b(?:HYPERLINK|PAGEREF|NUMPAGES|FORMTEXT|TOC\s+\\o)\b|MERGEFORMAT", re.I)
ENUMERATION_INTRO_RE = re.compile(r"(?:如下|下列|包括|条件|材料|方法|情形|事项|内容)[：:]\s*$")
STRUCTURAL_HEADING_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百千万零〇\d]+[编篇部分章节条]|"
    r"[一二三四五六七八九十百]+、|附件|附录)"
)


def chinese_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    total = section = number = 0
    for char in value:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
        elif char in CN_UNITS:
            unit = CN_UNITS[char]
            if unit == 10000:
                total += (section + number) * unit
                section = number = 0
            else:
                section += (number or 1) * unit
                number = 0
        else:
            return None
    return total + section + number


def article_number(value: str) -> int | None:
    match = re.fullmatch(r"第([一二三四五六七八九十百千万零〇两\d]+)条", value or "")
    return chinese_number(match.group(1)) if match else None


def validate_outputs(rows: list[dict[str, Any]], summaries: list[dict[str, Any]], max_chars: int) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    position_schema_enabled = any("clean_text_hash" in row or "start_char" in row for row in rows)

    def add(severity: str, check: str, detail: str, row: dict[str, Any] | None = None) -> None:
        issues.append({
            "severity": severity,
            "check": check,
            "detail": detail,
            "chunk_id": row.get("chunk_id", "") if row else "",
            "document_id": row.get("document_id", "") if row else "",
            "file_name": row.get("file_name", "") if row else "",
        })

    ids = [row["chunk_id"] for row in rows]
    duplicate_ids = [value for value, count in Counter(ids).items() if count > 1]
    for value in duplicate_ids[:20]:
        add("critical", "chunk_id_unique", f"重复ID：{value}")

    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized_bodies: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_document[row["document_id"]].append(row)
        body = row.get("body_text") or row.get("text", "")
        body_compact = compact(body)
        if not body_compact:
            add("critical", "empty_chunk", "Chunk正文为空", row)
            continue
        normalized_bodies[row["document_id"]][body_compact].append(row)
        if row["character_count"] > max_chars and not row["is_oversized"]:
            add("critical", "character_limit", f"{row['character_count']}字符且未标记超限", row)
        elif row["character_count"] > max_chars:
            add("minor", "marked_oversized", f"{row['character_count']}字符：{row.get('oversized_reason', '')}", row)
        if row["document_title"] and compact(row["document_title"]) not in compact(row["text"][:600]):
            add("major", "title_context", "检索文本开头缺少法规标题上下文", row)
        if position_schema_enabled:
            start_char = row.get("start_char")
            end_char = row.get("end_char")
            if not isinstance(start_char, int) or not isinstance(end_char, int) or start_char < 0 or end_char < start_char:
                add("major", "clean_text_position", f"正文位置无效：{start_char}-{end_char}", row)
            if not row.get("clean_text_hash") or not row.get("chunk_hash"):
                add("major", "incremental_hashes", "缺少clean_text_hash或chunk_hash", row)
            if row.get("is_overlapping") and not isinstance(row.get("overlap_left"), int):
                add("major", "overlap_coordinates", "overlap Chunk缺少overlap_left", row)
        if any(0xE000 <= ord(char) <= 0xF8FF for char in row["text"]):
            add("critical", "private_use_formula_character", "仍包含Unicode私有区字符", row)
        if "[未映射公式符号U+" in row["text"]:
            add("major", "unmapped_formula_character", "存在未映射公式字符，需要人工核对", row)
        if WORD_FIELD_RE.search(row["text"]):
            add("critical", "word_field_code", "包含Word域代码", row)
        toc_entries = len(TOC_ENTRY_RE.findall(body))
        if TOC_HEADING_RE.search(body) or toc_entries >= 2:
            add("critical", "table_of_contents_residue", f"疑似目录残留（目录条目{toc_entries}）", row)
        nonempty_lines = [line.strip() for line in body.splitlines() if line.strip()]
        if nonempty_lines and all(HEADING_ONLY_RE.fullmatch(line) for line in nonempty_lines):
            add("major", "heading_only_chunk", "Chunk只有章节/附件标题，没有可检索正文", row)
        if row["character_count"] < 80 and not row.get("article_start") and not row.get("attachment_name"):
            add("minor", "very_short_chunk", f"正文仅{row['character_count']}字符且没有条款定位", row)
        if ITEM_START_RE.search(body.lstrip()) and not row.get("article_start") and not row.get("is_overlapping"):
            add("minor", "orphan_list_item", "以款项编号开头且没有条号；检索文本仍保留法规标题和章节上下文", row)
        page_lines = [line for line in nonempty_lines if re.fullmatch(r"(?:[-—–]\s*)?\d{1,4}(?:\s*[-—–])?", line)]
        if page_lines:
            add("major", "page_number_residue", "存在孤立页码：" + "、".join(page_lines[:5]), row)

    for document_id, body_map in normalized_bodies.items():
        for body, duplicates in body_map.items():
            unique_non_overlap = [row for row in duplicates if not row.get("is_overlapping")]
            if len(body) >= 50 and len(unique_non_overlap) > 1:
                add("major", "duplicate_chunk_body", f"同一文件存在{len(unique_non_overlap)}个相同正文Chunk", unique_non_overlap[0])

    row_by_id = {row["chunk_id"]: row for row in rows}
    for document_id, document_rows in by_document.items():
        document_rows.sort(key=lambda row: row["chunk_index"])
        paths = {row["file_path"] for row in document_rows}
        if len(paths) != 1:
            add("critical", "file_isolation", "同一document_id对应多个文件路径", document_rows[0])
        indices = [row["chunk_index"] for row in document_rows]
        if indices != list(range(1, len(document_rows) + 1)):
            add("critical", "chunk_order", f"Chunk序号不连续：{indices[:20]}", document_rows[0])
        previous_article: int | None = None
        previous_sequence_scope: tuple[str, str] = ("", "")
        article_sequences: list[list[tuple[int, int, dict[str, Any]]]] = []
        for position, row in enumerate(document_rows):
            if row["is_overlapping"]:
                source = row_by_id.get(row["overlap_source_chunk_id"])
                if not source or source["document_id"] != document_id or source["chunk_index"] >= row["chunk_index"]:
                    add("major", "overlap_trace", "重叠来源不存在或顺序错误", row)
            body = row.get("body_text") or row.get("text", "")
            if ENUMERATION_INTRO_RE.search(body) and not row.get("is_overlapping"):
                following = document_rows[position + 1] if position + 1 < len(document_rows) else None
                following_body = (following or {}).get("body_text", "")
                following_lead = next((line.strip() for line in following_body.splitlines() if line.strip()), "")
                starts_new_structure = bool(following and (
                    following.get("chapter_title") or following.get("section_title")
                    or following.get("part_title") or STRUCTURAL_HEADING_RE.match(following_lead)
                ))
                bridged = starts_new_structure or bool(following and following.get("is_overlapping") and following.get("overlap_source_chunk_id") == row.get("chunk_id"))
                if not bridged:
                    add("major", "incomplete_enumeration", "正文以冒号结束，且下一Chunk未携带该引导语", row)
            if re.search(r"[；;]\s*$", body) and row.get("article_start") and row.get("article_end") == row.get("article_start"):
                following = document_rows[position + 1] if position + 1 < len(document_rows) else None
                following_body = (following or {}).get("body_text", "")
                following_lead = next((line.strip() for line in following_body.splitlines() if line.strip()), "")
                starts_new_structure = bool(following and (
                    following.get("chapter_title") or following.get("section_title")
                    or following.get("part_title") or STRUCTURAL_HEADING_RE.match(following_lead)
                ))
                bridged = starts_new_structure or bool(following and following.get("is_overlapping") and following.get("overlap_source_chunk_id") == row.get("chunk_id"))
                if not bridged:
                    add("minor", "possible_split_enumeration", "同一条款Chunk以分号结束，且下一Chunk未携带列举上下文", row)
            start = article_number(row["article_start"])
            end = article_number(row["article_end"])
            sequence_scope = (
                row.get("attachment_name", ""), row.get("part_title", ""),
                row.get("chapter_title", ""), row.get("section_title", ""),
            )
            if sequence_scope != previous_sequence_scope:
                previous_article = None
                previous_sequence_scope = sequence_scope
            if start is not None and end is not None and start > end:
                add("major", "article_range", "条款起止范围倒置", row)
            if start is not None:
                range_end = end if end is not None else start
                if not article_sequences or (article_sequences[-1] and start < article_sequences[-1][-1][0]):
                    article_sequences.append([])
                article_sequences[-1].append((start, range_end, row))
            if start is not None and not row["is_overlapping"]:
                if previous_article is not None and start < previous_article:
                    add("major", "article_order", "条款顺序倒退", row)
                previous_article = end if end is not None else start

        # Long regulations normally begin at Article 1.  This catches scanned or
        # partially parsed files that otherwise look structurally valid.
        for article_ranges in article_sequences:
            if len(article_ranges) < 10:
                continue
            first_number, first_end, first_row = article_ranges[0]
            if first_number > 2:
                add("major", "article_start_gap", f"正文首个识别条款为第{first_number}条，疑似缺失前部正文", first_row)
            previous_end = first_end
            for number, range_end, row in article_ranges[1:]:
                if number > previous_end + 1:
                    add("major", "article_sequence_gap", f"条款从第{previous_end}条跳至第{number}条，疑似解析缺失", row)
                previous_end = max(previous_end, range_end)

    for summary in summaries:
        if summary.get("coverage_status") != "pass" and summary.get("status") == "success":
            add("major", "source_block_coverage", f"{summary.get('file_name')}存在未覆盖源文本块")
        if summary.get("status") == "success" and not summary.get("chunk_count"):
            add("critical", "empty_document_output", f"{summary.get('file_name')}解析成功但没有Chunk")

    severity_counts = Counter(issue["severity"] for issue in issues)
    checks = {}
    for name in sorted({issue["check"] for issue in issues} | {
        "chunk_id_unique", "character_limit", "empty_chunk", "file_isolation", "chunk_order",
        "article_order", "title_context", "overlap_trace", "source_block_coverage",
        "private_use_formula_character", "word_field_code", "table_of_contents_residue",
        "heading_only_chunk", "duplicate_chunk_body",
        "article_start_gap", "article_sequence_gap", "clean_text_position",
        "incremental_hashes", "overlap_coordinates",
    }):
        checks[name] = not any(issue["check"] == name and issue["severity"] in {"critical", "major"} for issue in issues)
    passed = severity_counts["critical"] == 0 and severity_counts["major"] == 0
    return {
        "passed": passed,
        "checks": checks,
        "issue_count": len(issues),
        "severity_counts": dict(severity_counts),
        "issues": issues,
    }
