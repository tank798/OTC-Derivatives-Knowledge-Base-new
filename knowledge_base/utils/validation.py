from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
import re

from utils.text import compact


CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


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
    ids = [row["chunk_id"] for row in rows]
    duplicate_ids = [value for value, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        issues.append({"check": "chunk_id_unique", "detail": f"重复ID：{duplicate_ids[:10]}"})
    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_document[row["document_id"]].append(row)
        if row["character_count"] > max_chars and not row["is_oversized"]:
            issues.append({"check": "character_limit", "detail": row["chunk_id"]})
        if row["document_title"] and compact(row["document_title"]) not in compact(row["text"][:500]):
            issues.append({"check": "title_context", "detail": row["chunk_id"]})
        if any(0xE000 <= ord(char) <= 0xF8FF for char in row["text"]):
            issues.append({"check": "private_use_formula_character", "detail": row["chunk_id"]})
        if re.search(r"\b(?:HYPERLINK|PAGEREF|NUMPAGES|FORMTEXT)\b|MERGEFORMAT", row["text"], re.I):
            issues.append({"check": "word_field_code", "detail": row["chunk_id"]})
    row_by_id = {row["chunk_id"]: row for row in rows}
    for document_id, document_rows in by_document.items():
        paths = {row["file_path"] for row in document_rows}
        if len(paths) != 1:
            issues.append({"check": "file_isolation", "detail": document_id})
        indices = [row["chunk_index"] for row in document_rows]
        if indices != list(range(1, len(document_rows) + 1)):
            issues.append({"check": "chunk_order", "detail": document_id})
        previous_article: int | None = None
        previous_attachment = ""
        for row in document_rows:
            if row["is_overlapping"]:
                source = row_by_id.get(row["overlap_source_chunk_id"])
                if not source or source["document_id"] != document_id or source["chunk_index"] >= row["chunk_index"]:
                    issues.append({"check": "overlap_trace", "detail": row["chunk_id"]})
            start = article_number(row["article_start"])
            end = article_number(row["article_end"])
            if row.get("attachment_name") != previous_attachment:
                previous_article = None
                previous_attachment = row.get("attachment_name", "")
            if start is not None and end is not None and start > end:
                issues.append({"check": "article_range", "detail": row["chunk_id"]})
            if start is not None and not row["is_overlapping"]:
                if previous_article is not None and start < previous_article:
                    issues.append({"check": "article_order", "detail": row["chunk_id"]})
                previous_article = end if end is not None else start
    review_coverage = [row["file_name"] for row in summaries if row.get("coverage_status") != "pass" and row.get("status") == "success"]
    if review_coverage:
        issues.append({"check": "source_block_coverage", "detail": "；".join(review_coverage[:20])})
    checks = {
        "chunk_id_unique": not duplicate_ids,
        "character_limit_or_marked_oversized": not any(issue["check"] == "character_limit" for issue in issues),
        "file_isolation": not any(issue["check"] == "file_isolation" for issue in issues),
        "chunk_order": not any(issue["check"] == "chunk_order" for issue in issues),
        "article_order": not any(issue["check"] in {"article_range", "article_order"} for issue in issues),
        "title_context": not any(issue["check"] == "title_context" for issue in issues),
        "overlap_trace": not any(issue["check"] == "overlap_trace" for issue in issues),
        "source_block_coverage": not review_coverage,
        "no_private_use_formula_characters": not any(issue["check"] == "private_use_formula_character" for issue in issues),
        "no_word_field_codes": not any(issue["check"] == "word_field_code" for issue in issues),
    }
    return {"passed": all(checks.values()), "checks": checks, "issue_count": len(issues), "issues": issues}
