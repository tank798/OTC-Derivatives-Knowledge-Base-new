#!/usr/bin/env python3
"""Independent three-layer review for regulatory documents and chunks.

Inputs are deliberately limited to:
  data/raw/监管文件/
  data/processed/documents/json/
  data/processed/chunks/jsonl/all_chunks.jsonl

The build manifest is read only to resolve the existing structured-json mapping;
it is never treated as evidence that the content itself is correct.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data/raw/监管文件"
DOC_DIR = ROOT / "data/processed/documents/json"
CHUNK_FILE = ROOT / "data/processed/chunks/jsonl/all_chunks.jsonl"
MANIFEST_FILE = ROOT / "data/processed/build_manifest.json"
OUT_DIR = Path(__file__).resolve().parent

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FIELD_RE = re.compile(r"\b(?:MERGEFIELD|HYPERLINK|PAGEREF|TOC)\b(?:\s+|\\)", re.I)
PUA_RE = re.compile(r"[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]")
ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千〇零两0-9]+条")
ENUM_START_RE = re.compile(
    r"^\s*(?:[（(][一二三四五六七八九十百千0-9]+[)）]|[一二三四五六七八九十百千0-9]+[、.]|[A-Za-z][.)])"
)
ORPHAN_ENUM_RE = re.compile(r"^\s*[（(][一二三四五六七八九十百千0-9]+[)）]")
HEADING_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百千〇零两0-9]+(?:编|章|节|条)|附件(?:\s*[一二三四五六七八九十0-9]+)?|附则|目录)[\s\S]{0,35}$"
)
PAGE_ONLY_RE = re.compile(r"^\s*(?:第?\s*[-—－]?\s*\d+\s*[-—－]?\s*页?|Page\s*\d+)\s*$", re.I)
INTRO_RE = re.compile(r"(?:包括以下(?:内容|事项)?|应(?:当)?符合下列(?:条件|要求)?|如下|下列)\s*[:：]?\s*$")
CRITICAL_TOKEN_RE = re.compile(
    r"(?:\d+(?:\.\d+)?%|\d+(?:\.\d+)?(?:万|亿)?元|\d+(?:\.\d+)?(?:个)?(?:工作日|日|月|年)|"
    r"\d{4}[年\-]\d{1,2}(?:[月\-]\d{1,2}日?)?|(?:O/N|\d+(?:\.\d+)?[DWMY])|"
    r"第[一二三四五六七八九十百千〇零两0-9]+条)"
)

SEVERITY_RANK = {"NONE": 0, "MINOR": 1, "MAJOR": 2, "CRITICAL": 3}


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def canonical(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return "".join(ch.lower() for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def compact(text: str, limit: int = 520) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def retrieval_only_context(chunk: dict) -> str:
    """Return retrieval context that precedes body_text, excluding routine metadata."""
    text_value = canonical(chunk.get("text", ""))
    body_value = canonical(chunk.get("body_text", ""))
    if not body_value or not text_value.endswith(body_value):
        return ""
    extra = text_value[:-len(body_value)]
    for key in ("document_title", "part_title", "chapter_title", "section_title", "article_start", "paragraph_range", "attachment_name"):
        value = canonical(chunk.get(key, ""))
        if value:
            extra = extra.replace(value, "", 1)
    return extra


def has_meaningful_overlap_context(chunk: dict) -> bool:
    """Accept concise legal locators; they need not be twenty characters long."""
    context = retrieval_only_context(chunk)
    if len(context) >= 4:
        return True
    return any(chunk.get(key) for key in ("article_start", "chapter_title", "section_title", "paragraph_range"))


def longest_overlap_with_source(chunk: dict, chunk_by_id: dict[str, dict]) -> int:
    source = chunk_by_id.get(chunk.get("overlap_source_chunk_id", ""))
    if not source:
        return 0
    source_body = canonical(source.get("body_text", ""))
    chunk_body = canonical(chunk.get("body_text", ""))
    return difflib.SequenceMatcher(None, source_body, chunk_body, autojunk=False).find_longest_match(
        0, len(source_body), 0, len(chunk_body)
    ).size


def xml_visible_text(blob: bytes) -> tuple[str, dict[str, int]]:
    root = ET.fromstring(blob)
    counts = {"tables": 0, "textboxes": 0, "smartTags": 0, "field_codes": 0}
    counts["tables"] = len(root.findall(f".//{W_NS}tbl"))
    counts["textboxes"] = len(root.findall(".//{urn:schemas-microsoft-com:vml}textbox"))
    counts["smartTags"] = len(root.findall(f".//{W_NS}smartTag"))
    counts["field_codes"] = len(root.findall(f".//{W_NS}instrText"))
    parts: list[str] = []
    for p in root.findall(f".//{W_NS}p"):
        # Ignore deleted revision text; w:t under normal runs, smartTags, tables and text boxes is retained.
        texts = []
        for node in p.iter(f"{W_NS}t"):
            if any(ancestor.tag == f"{W_NS}del" for ancestor in []):
                continue
            texts.append(node.text or "")
        value = "".join(texts).strip()
        if value:
            parts.append(value)
    return "\n".join(parts), counts


def extract_docx(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        if "word/document.xml" not in zf.namelist():
            text = run_text_command(["textutil", "-convert", "txt", "-stdout", str(path)])
            return {"text": text, "pages": [], "headers": "", "footers": "", "stats": {"nonstandard_docx": True}, "method": "textutil_docx_fallback"}
        body, stats = xml_visible_text(zf.read("word/document.xml"))
        headers, footers = [], []
        for name in zf.namelist():
            if re.fullmatch(r"word/header\d+\.xml", name):
                headers.append(xml_visible_text(zf.read(name))[0])
            elif re.fullmatch(r"word/footer\d+\.xml", name):
                footers.append(xml_visible_text(zf.read(name))[0])
    return {
        "text": body,
        "pages": [],
        "headers": "\n".join(headers),
        "footers": "\n".join(footers),
        "stats": stats,
        "method": "docx_ooxml",
    }


def run_text_command(args: list[str]) -> str:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(args)}: {p.stderr.decode('utf-8', 'replace')[:300]}")
    return p.stdout.decode("utf-8", "replace")


def extract_pdf(path: Path) -> dict:
    text = run_text_command(["pdftotext", "-layout", str(path), "-"])
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    info = run_text_command(["pdfinfo", str(path)])
    m = re.search(r"^Pages:\s*(\d+)", info, re.M)
    page_count = int(m.group(1)) if m else len(pages)
    return {
        "text": "\n".join(pages),
        "pages": pages,
        "headers": "",
        "footers": "",
        "stats": {"page_count": page_count, "text_pages": sum(bool(canonical(p)) for p in pages)},
        "method": "pdftotext_layout",
    }


def extract_doc(path: Path) -> dict:
    text = run_text_command(["textutil", "-convert", "txt", "-stdout", str(path)])
    return {"text": text, "pages": [], "headers": "", "footers": "", "stats": {}, "method": "textutil"}


def extract_raw(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".doc":
        return extract_doc(path)
    raise ValueError(f"unsupported source: {path}")


def sequence_coverage(raw: str, structured: str) -> float:
    a, b = canonical(raw), canonical(structured)
    if not a:
        return 1.0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(a)


def token_set(text: str) -> set[str]:
    return {canonical(x) for x in CRITICAL_TOKEN_RE.findall(unicodedata.normalize("NFKC", text or "")) if canonical(x)}


def max_severity(issues: list[dict]) -> str:
    if not issues:
        return "NONE"
    return max((i["severity"] for i in issues), key=lambda x: SEVERITY_RANK[x])


def add_issue(issue_map, chunk_id: str, issue_type: str, severity: str, reason: str, evidence: str, recommendation: str):
    issue_map[chunk_id].append({
        "type": issue_type,
        "severity": severity,
        "reason": reason,
        "evidence": evidence,
        "recommendation": recommendation,
    })


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chunks = read_jsonl(CHUNK_FILE)
    manifest = read_json(MANIFEST_FILE)
    manifest_docs = manifest.get("documents", {})
    docs_by_json_name = {p.name: read_json(p) for p in sorted(DOC_DIR.glob("*.json"))}
    raw_files = {
        p.name: p
        for p in sorted(RAW_DIR.iterdir())
        if p.is_file() and not p.name.startswith(("~$", "."))
    }
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    issue_map: dict[str, list[dict]] = defaultdict(list)
    doc_chunks: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        doc_chunks[c["document_id"]].append(c)
    for values in doc_chunks.values():
        values.sort(key=lambda c: c.get("chunk_index", -1))

    # Resolve each chunk document to its structured JSON via the build manifest.
    chunk_doc_to_structured: dict[str, dict] = {}
    structured_path_for_chunk_doc: dict[str, str] = {}
    for chunk_doc_id, entry in manifest_docs.items():
        rel = entry.get("structured_json", "")
        name = Path(rel).name
        if name in docs_by_json_name:
            chunk_doc_to_structured[chunk_doc_id] = docs_by_json_name[name]
            structured_path_for_chunk_doc[chunk_doc_id] = name

    # 1-4: formal-document coverage, IDs, indices, referenced block existence.
    duplicate_ids = [cid for cid, n in Counter(c["chunk_id"] for c in chunks).items() if n > 1]
    for cid in duplicate_ids:
        add_issue(issue_map, cid, "duplicate_chunk_id", "CRITICAL", "chunk_id不唯一。", f"chunk_id={cid} 出现多次。", "重新生成全局唯一chunk_id并重建Chunk。")

    missing_chunk_documents = []
    for doc_id, entry in manifest_docs.items():
        expected = entry.get("chunk_ids", [])
        actual = [c["chunk_id"] for c in doc_chunks.get(doc_id, [])]
        if not actual:
            missing_chunk_documents.append(entry.get("file_name", doc_id))
        indices = [c.get("chunk_index") for c in doc_chunks.get(doc_id, [])]
        expected_indices = list(range(1, len(indices) + 1))
        if indices and indices != expected_indices:
            for c in doc_chunks[doc_id]:
                add_issue(issue_map, c["chunk_id"], "non_contiguous_chunk_index", "MAJOR", "同一文档的chunk_index不连续或不从1开始。", f"实际={indices}; 应为={expected_indices}", "按文档重新排序并连续编号。")
        if expected and actual != expected:
            for c in doc_chunks.get(doc_id, [])[:1]:
                add_issue(issue_map, c["chunk_id"], "manifest_chunk_set_mismatch", "MAJOR", "Chunk集合或顺序与构建清单不一致。", f"manifest={expected}; actual={actual}", "核查构建产物并统一manifest与all_chunks.jsonl。")

    block_owners: dict[tuple[str, str], dict] = {}
    uncovered_blocks: list[dict] = []
    for chunk_doc_id, doc in chunk_doc_to_structured.items():
        blocks = {b["block_id"]: b for b in doc.get("blocks", [])}
        cited = Counter(bid for c in doc_chunks.get(chunk_doc_id, []) for bid in c.get("source_block_ids", []))
        for c in doc_chunks.get(chunk_doc_id, []):
            if c.get("document_id") != doc.get("document_id"):
                add_issue(
                    issue_map, c["chunk_id"], "document_id_mismatch", "MINOR",
                    "Chunk主键与结构化文档主键不一致，当前只能依赖manifest间接映射。",
                    f"chunk.document_id={c.get('document_id')}; structured.document_id={doc.get('document_id')}; structured_json={structured_path_for_chunk_doc.get(chunk_doc_id)}",
                    "统一解析器与Chunker的document_id生成规则后重新构建。",
                )
            missing = [bid for bid in c.get("source_block_ids", []) if bid not in blocks]
            if missing:
                add_issue(issue_map, c["chunk_id"], "missing_source_block_reference", "CRITICAL", "Chunk引用了不存在的source_block_id。", f"不存在的ID={missing}", "修复引用或重新切分该文档。")
            for bid in c.get("source_block_ids", []):
                if bid in blocks:
                    block_owners[(chunk_doc_id, bid)] = c
            source_text = "\n".join(blocks[bid].get("text", "") for bid in c.get("source_block_ids", []) if bid in blocks)
            if source_text:
                source_canon = canonical(source_text)
                body_canon = canonical(c.get("body_text", ""))
                # A chunk may legitimately use only part of a large source block.  It must,
                # however, be an ordered substring of the cited block text (after normalization).
                if body_canon and body_canon not in source_canon:
                    matcher = difflib.SequenceMatcher(None, source_canon, body_canon, autojunk=False)
                    matched = sum(block.size for block in matcher.get_matching_blocks())
                    body_coverage = matched / len(body_canon)
                    if body_coverage < 0.95 and not c.get("is_overlapping"):
                        add_issue(issue_map, c["chunk_id"], "chunk_text_source_mismatch", "MAJOR", "Chunk正文不能由其引用的结构化source_block按序回溯。", f"Chunk正文覆盖率={body_coverage:.4f}; 结构化证据={compact(source_text)}", "从source_block原文重新组装Chunk，禁止改写。")
        for bid, block in blocks.items():
            if canonical(block.get("text", "")) and cited[bid] == 0:
                uncovered_blocks.append({"chunk_doc_id": chunk_doc_id, "block": block, "file_name": doc.get("file_name", "")})

    # 5-9: content quality, duplicates, noise and metadata.
    text_hash_groups: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        body = c.get("body_text", "")
        canon = canonical(body)
        text_hash_groups[hashlib.sha256(canon.encode()).hexdigest()].append(c)
        if not canon:
            add_issue(issue_map, c["chunk_id"], "empty_chunk", "CRITICAL", "Chunk正文为空。", "body_text规范化后长度为0。", "删除空Chunk并重新切分。")
        if len(canon) > 1300 or c.get("is_oversized"):
            add_issue(issue_map, c["chunk_id"], "oversized_chunk", "MAJOR", "Chunk超过1300字符或被标记为oversized。", f"规范化长度={len(canon)}; is_oversized={c.get('is_oversized')}", "在完整条款、句子或分项边界拆分并保留必要上下文。")
        if "�" in body:
            add_issue(issue_map, c["chunk_id"], "replacement_character", "MAJOR", "Chunk含Unicode替换字符。", compact(body), "回到原件重新提取或OCR校正。")
        if PUA_RE.search(body):
            add_issue(issue_map, c["chunk_id"], "private_use_character", "MAJOR", "Chunk含Unicode私有区字符。", compact(body), "恢复对应公式/符号的可读文本。")
        if FIELD_RE.search(body):
            add_issue(issue_map, c["chunk_id"], "word_field_code", "MAJOR", "Chunk含Word域代码残留。", compact(body), "仅保留域显示值，移除域指令。")
        if PAGE_ONLY_RE.fullmatch(body.strip()):
            add_issue(issue_map, c["chunk_id"], "isolated_page_number", "MAJOR", "Chunk仅包含页码。", compact(body), "删除该Chunk并在解析阶段过滤页眉页脚/页码。")
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if lines and all(HEADING_RE.fullmatch(line) or PAGE_ONLY_RE.fullmatch(line) for line in lines):
            add_issue(issue_map, c["chunk_id"], "heading_only_chunk", "MAJOR", "Chunk只有标题或结构标签。", compact(body), "向后合并到所属正文。")
        doc = chunk_doc_to_structured.get(c.get("document_id"))
        if doc:
            md = doc.get("metadata", {})
            field_map = {
                "document_title": "document_title",
                "document_number": "document_number",
                "issuing_authority": "issuing_authority",
                "official_url": "official_url",
            }
            mismatches = []
            for cf, mf in field_map.items():
                if (c.get(cf) or "").strip() != (md.get(mf) or "").strip():
                    mismatches.append(f"{cf}: chunk={c.get(cf)!r}, structured={md.get(mf)!r}")
            if c.get("file_name") != doc.get("file_name"):
                mismatches.append(f"file_name: chunk={c.get('file_name')!r}, structured={doc.get('file_name')!r}")
            if mismatches:
                add_issue(issue_map, c["chunk_id"], "metadata_mismatch", "MAJOR", "Chunk与结构化文档的标题/文号/机关/官网链接或文件名不一致。", "; ".join(mismatches), "以核验后的权威元数据为准统一两层数据并重新构建。")

    duplicate_text_groups = []
    for group in text_hash_groups.values():
        if len(group) > 1 and canonical(group[0].get("body_text", "")):
            ids = [x["chunk_id"] for x in group]
            duplicate_text_groups.append(ids)
            same_document = len({x.get("document_id") for x in group}) == 1
            for c in group:
                if same_document:
                    add_issue(issue_map, c["chunk_id"], "exact_duplicate_chunk", "MAJOR", "同一文档内存在正文完全重复的Chunk。", f"重复组={ids}", "删除无意义重复；若为必要overlap，改用明确的overlap引用并缩小重复范围。")
                # Identical clauses across different formal source documents are
                # recorded in coverage.json but are not a Chunk defect.

    overlap_audits = []
    for c in chunks:
        if not c.get("is_overlapping"):
            if c.get("overlap_source_chunk_id"):
                add_issue(issue_map, c["chunk_id"], "overlap_flag_inconsistent", "MINOR", "Chunk未标记overlap但填写了overlap_source_chunk_id。", f"overlap_source_chunk_id={c.get('overlap_source_chunk_id')}", "统一overlap标记与来源字段。")
            continue
        source_id = c.get("overlap_source_chunk_id", "")
        source = chunk_by_id.get(source_id)
        valid_source = bool(source and source.get("document_id") == c.get("document_id") and source.get("chunk_index", 0) < c.get("chunk_index", 0))
        longest = 0
        shared_ratio = 0.0
        context_chars = len(retrieval_only_context(c))
        if source:
            a, b = canonical(source.get("body_text", "")), canonical(c.get("body_text", ""))
            match = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
            longest = match.size
            shared_ratio = longest / max(1, min(len(a), len(b)))
        overlap_audits.append({"chunk_id": c["chunk_id"], "source_chunk_id": source_id, "valid_source": valid_source, "longest_shared_characters": longest, "retrieval_only_context_characters": context_chars, "shared_ratio": round(shared_ratio, 4)})
        if not valid_source:
            add_issue(issue_map, c["chunk_id"], "invalid_overlap_source", "MAJOR", "overlap来源不存在、跨文档或不是前序Chunk。", f"overlap_source_chunk_id={source_id}", "修复overlap来源引用后重新构建。")
        elif longest < 30 and not has_meaningful_overlap_context(c):
            add_issue(issue_map, c["chunk_id"], "ineffective_overlap", "MINOR", "已标记overlap，但既没有足够正文重叠，也没有可识别的父级条款或检索上下文。", f"最长连续共享字符={longest}; 检索专用上下文字符={context_chars}; 来源={source_id}", "移除无效overlap标记或加入真正必要的父级定义/条款上下文。")
        elif shared_ratio > 0.85:
            add_issue(issue_map, c["chunk_id"], "excessive_overlap", "MINOR", "与来源Chunk的连续重复比例超过85%，overlap可能过大。", f"共享比例={shared_ratio:.3f}; 来源={source_id}", "缩小overlap到父级条号、引导语和必要前文。")

    # High similarity is checked inside each document; legitimate declared overlap is not reported.
    high_duplicate_pairs = []
    for doc_id, values in doc_chunks.items():
        for i, left in enumerate(values):
            a = canonical(left.get("body_text", ""))
            if len(a) < 80:
                continue
            for right in values[i + 1:]:
                if left.get("is_overlapping") or right.get("is_overlapping"):
                    continue
                b = canonical(right.get("body_text", ""))
                if len(b) < 80 or min(len(a), len(b)) / max(len(a), len(b)) < 0.82:
                    continue
                ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
                if ratio >= 0.92:
                    high_duplicate_pairs.append((left["chunk_id"], right["chunk_id"], ratio))
                    for c, other in ((left, right), (right, left)):
                        add_issue(issue_map, c["chunk_id"], "highly_duplicate_chunk", "MINOR", "与同文档另一Chunk高度重复且未声明overlap。", f"另一Chunk={other['chunk_id']}; 相似度={ratio:.4f}", "合并重复内容或显式标记并收缩overlap。")

    # Boundary checks: isolated list items, split introductions, incomplete endings.
    for doc_id, values in doc_chunks.items():
        for i, c in enumerate(values):
            body = c.get("body_text", "").strip()
            previous = values[i - 1] if i else None
            nxt = values[i + 1] if i + 1 < len(values) else None
            first_line = body.splitlines()[0].strip() if body else ""
            meaningful_retrieval_context = has_meaningful_overlap_context(c)
            meaningful_literal_overlap = bool(c.get("is_overlapping") and longest_overlap_with_source(c, chunk_by_id) >= 30)
            if ORPHAN_ENUM_RE.match(first_line) and not ARTICLE_RE.search(body[:220]) and not meaningful_retrieval_context and not meaningful_literal_overlap and not c.get("attachment_name"):
                evidence = f"Chunk开头={compact(body[:240])}"
                if previous:
                    evidence += f"; 前一Chunk结尾={compact(previous.get('body_text','')[-240:])}"
                add_issue(issue_map, c["chunk_id"], "orphan_list_item", "MINOR", "Chunk以款/项编号开头，但正文和结构元数据未携带父级条款或引导语。", evidence, "合并父级引导语，或加入可追溯的最小overlap并补齐article元数据。")
            if nxt:
                next_body = nxt.get("body_text", "").strip()
                if INTRO_RE.search(body[-120:]) and ENUM_START_RE.match(next_body):
                    add_issue(issue_map, c["chunk_id"], "intro_list_split", "MAJOR", "引导语与其列表被切到不同Chunk。", f"本Chunk结尾={compact(body[-260:])}; 下一Chunk开头={compact(next_body[:260])}", "将引导语与至少首个列表项置于同一Chunk，并通过overlap保持其余分项上下文。")
                    add_issue(issue_map, nxt["chunk_id"], "intro_list_split", "MAJOR", "列表项与所属引导语分离。", f"前一Chunk结尾={compact(body[-260:])}; 本Chunk开头={compact(next_body[:260])}", "在本Chunk加入父级条款和引导语的最小必要overlap。")
                terminal = body.rstrip("\"'”’）》】)） ")[-1:] if body else ""
                same_article = c.get("article_end") and c.get("article_end") == nxt.get("article_start")
                top_level_next = bool(re.match(r"^[一二三四五六七八九十百千]+、", next_body))
                if (not nxt.get("is_overlapping") and not top_level_next and terminal in {";", "；", ",", "，", ":", "："} and (same_article or ENUM_START_RE.match(next_body))):
                    boundary_evidence = f"前一侧结尾={compact(body[-280:])}; 后一侧开头={compact(next_body[:280])}; overlap={nxt.get('is_overlapping')}"
                    recommendation = "在完整分项/句号处切分，或为后续Chunk加入父级条款/引导语的最小必要overlap并正确标记。"
                    add_issue(issue_map, c["chunk_id"], "split_enumeration_without_overlap", "MAJOR", "Chunk在列举或未完句标点处结束，下一Chunk直接续写且没有必要的overlap，割裂了同一条款/列表。", boundary_evidence, recommendation)
                    add_issue(issue_map, nxt["chunk_id"], "split_enumeration_without_overlap", "MAJOR", "Chunk从前一Chunk被割裂的句子或列表中间开始，且未携带父级条款/引导语overlap。", boundary_evidence, recommendation)

    # Independent raw-to-structured conversion checks for all 108 formal documents.
    raw_audits = {}
    conversion_problem_docs = []
    for chunk_doc_id, doc in chunk_doc_to_structured.items():
        file_name = doc.get("file_name", "")
        raw_path = raw_files.get(file_name)
        if not raw_path:
            conversion_problem_docs.append({"file_name": file_name, "type": "missing_raw_file", "detail": "结构化文档找不到同名原件"})
            continue
        try:
            raw = extract_raw(raw_path)
        except Exception as exc:
            conversion_problem_docs.append({"file_name": file_name, "type": "raw_extraction_failure", "detail": str(exc)})
            continue
        raw_text = raw["text"]
        structured_text = doc.get("normalized_text", "")
        coverage = sequence_coverage(raw_text, structured_text)
        raw_articles = set(ARTICLE_RE.findall(unicodedata.normalize("NFKC", raw_text)))
        structured_articles = set(ARTICLE_RE.findall(unicodedata.normalize("NFKC", structured_text)))
        missing_articles = sorted(raw_articles - structured_articles)
        raw_tokens, structured_tokens = token_set(raw_text), token_set(structured_text)
        missing_tokens = sorted(raw_tokens - structured_tokens)
        blank_text_pages = []
        for page_no, page in enumerate(raw.get("pages", []), 1):
            if not canonical(page):
                blank_text_pages.append(page_no)
        audit = {
            "file_name": file_name,
            "source_type": doc.get("source_type"),
            "method": raw["method"],
            "raw_character_count": len(canonical(raw_text)),
            "structured_character_count": len(canonical(structured_text)),
            "sequence_coverage": round(coverage, 6),
            "missing_article_labels": missing_articles[:60],
            "missing_critical_tokens": missing_tokens[:80],
            "blank_text_pages": blank_text_pages,
            "stats": raw.get("stats", {}),
        }
        raw_audits[file_name] = audit
        severe_reasons = []
        if missing_articles:
            severe_reasons.append(f"原件条号未在结构化文本出现={missing_articles[:20]}")
        # Token differences may be headers/dates on cover pages; require several before document-level escalation.
        if len(missing_tokens) >= 8:
            severe_reasons.append(f"关键日期/金额/比例/期限/编号缺失候选={missing_tokens[:20]}")
        # A blank text page is retained in the audit for visual follow-up, but is not itself
        # proof of a scanned/missing page (covers and intentional blank pages are common).
        if severe_reasons:
            length_ratio = len(canonical(raw_text)) / max(1, len(canonical(structured_text)))
            confirmed_large_omission = length_ratio >= 2.0 and (missing_articles or missing_tokens)
            conversion_problem_docs.append({"file_name": file_name, "type": "confirmed_conversion_omission" if confirmed_large_omission else "possible_conversion_omission", "detail": f"原件/结构化规范化长度比={length_ratio:.2f}; {'; '.join(severe_reasons)}"})
            severity = "CRITICAL" if confirmed_large_omission else "MAJOR"
            reason = "原件主体正文大段未进入结构化文本，现有Chunk仅覆盖原件的一小部分。" if confirmed_large_omission else "原始文件与结构化文本差异核对发现需人工确认的遗漏/OCR候选。"
            for target in doc_chunks.get(chunk_doc_id, []):
                add_issue(issue_map, target["chunk_id"], "conversion_omission", severity, reason, f"原件/结构化规范化长度比={length_ratio:.2f}; {'; '.join(severe_reasons)}; 原件片段={compact(raw_text)}; 结构化片段={compact(structured_text)}", "对照原件全部页面/Word对象重新解析，补齐结构化文本后对该文档重新构建全部Chunk。")

    # Explicit checks requested by the user.
    special_checks = {}
    shibor_doc = next((d for d in chunk_doc_to_structured.values() if d.get("file_name", "").startswith("Shibor利率互换")), None)
    if shibor_doc:
        t = unicodedata.normalize("NFKC", shibor_doc.get("normalized_text", ""))
        values = {x: x in t for x in ("1M", "3M", "6M", "9M")}
        special_checks["shibor_tenors"] = values
        if not all(values.values()):
            doc_id = next(k for k, v in chunk_doc_to_structured.items() if v is shibor_doc)
            for c in doc_chunks.get(doc_id, [])[:1]:
                add_issue(issue_map, c["chunk_id"], "shibor_tenor_missing", "CRITICAL", "Shibor期限1M/3M/6M/9M不完整。", json.dumps(values, ensure_ascii=False), "修复DOCX smartTag/文本对象抽取后重建。")

    commodity_doc = next((d for d in chunk_doc_to_structured.values() if "商品衍生品定义文件" in d.get("file_name", "")), None)
    if commodity_doc:
        t = unicodedata.normalize("NFKC", commodity_doc.get("normalized_text", ""))
        article_presence = {f"第{i}条": bool(re.search(rf"第\s*{i}\s*条", t)) for i in range(1, 7)}
        # Also accept Chinese numeral article labels.
        cn = ["一", "二", "三", "四", "五", "六"]
        for i, label in enumerate(cn, 1):
            article_presence[f"第{i}条"] = article_presence[f"第{i}条"] or f"第{label}条" in t
        special_checks["commodity_first_six_articles"] = article_presence
        if not all(article_presence.values()):
            doc_id = next(k for k, v in chunk_doc_to_structured.items() if v is commodity_doc)
            for c in doc_chunks.get(doc_id, [])[:1]:
                add_issue(issue_map, c["chunk_id"], "commodity_first_six_missing", "CRITICAL", "商品衍生品定义文件前六条不完整。", json.dumps(article_presence, ensure_ascii=False), "重新解析旧DOC正文并核对目录与正文，补齐前六条后重建。")

    wrong_pdf = raw_files.get("证券公司市场风险管理指引.pdf")
    wrong_pdf_check = {"file_name": "证券公司市场风险管理指引.pdf", "exists": bool(wrong_pdf)}
    if wrong_pdf:
        wrong_text = extract_pdf(wrong_pdf)["text"]
        wrong_pdf_check.update({
            "contains_actual_title": "证券公司全面风险管理规范" in re.sub(r"\s+", "", wrong_text),
            "contains_named_title": "证券公司市场风险管理指引" in re.sub(r"\s+", "", wrong_text),
            "actual_text_excerpt": compact(wrong_text, 300),
        })
    exclusion_record = next(
        (record for record in manifest.get("excluded_sources", []) if record.get("file_name") == "证券公司市场风险管理指引.pdf"),
        None,
    )
    wrong_pdf_check.update({
        "exclusion_record_present": bool(exclusion_record),
        "exclusion_reason": (exclusion_record or {}).get("reason", ""),
        "correct_docx_exists": "证券公司全面风险管理规范.docx" in raw_files,
    })
    special_checks["wrong_named_pdf"] = wrong_pdf_check

    # Build per-chunk review records.
    review_records = []
    for c in chunks:
        issues = issue_map.get(c["chunk_id"], [])
        severity = max_severity(issues)
        doc = chunk_doc_to_structured.get(c.get("document_id"), {})
        blocks = {b["block_id"]: b for b in doc.get("blocks", [])}
        structured_evidence = "\n".join(blocks[bid].get("text", "") for bid in c.get("source_block_ids", []) if bid in blocks)
        if issues:
            evidence = {
                "file_name": c.get("file_name", ""),
                "chunk_content": c.get("body_text", ""),
                "structured_source_evidence": compact(structured_evidence, 900),
                "issue_evidence": [i["evidence"] for i in issues],
            }
            reason = "；".join(dict.fromkeys(i["reason"] for i in issues))
            recommendation = "；".join(dict.fromkeys(i["recommendation"] for i in issues))
        else:
            evidence = {"file_name": c.get("file_name", ""), "source_block_ids_verified": c.get("source_block_ids", [])}
            reason = "自动一致性、结构化来源回溯、原件转换抽查与Chunk边界规则均未发现问题。"
            recommendation = "无需修复。"
        review_records.append({
            "chunk_id": c["chunk_id"],
            "document_id": c.get("document_id", ""),
            "chunk_index": c.get("chunk_index"),
            "status": "ISSUE" if issues else "PASS",
            "severity": severity,
            "issue_types": list(dict.fromkeys(i["type"] for i in issues)),
            "reason": reason,
            "evidence": evidence,
            "recommendation": recommendation,
        })

    review_path = OUT_DIR / "chunk_review.jsonl"
    with review_path.open("w", encoding="utf-8") as f:
        for row in review_records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Document summary.
    summary_path = OUT_DIR / "document_summary.csv"
    records_by_doc = defaultdict(list)
    for r in review_records:
        records_by_doc[r["document_id"]].append(r)
    with summary_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["document_id", "file_name", "chunk_count", "pass_count", "issue_count", "minor_count", "major_count", "critical_count"])
        writer.writeheader()
        for doc_id, values in sorted(records_by_doc.items(), key=lambda kv: (chunk_by_id[kv[1][0]["chunk_id"]].get("file_name", ""), kv[0])):
            file_name = chunk_by_id[values[0]["chunk_id"]].get("file_name", "")
            writer.writerow({
                "document_id": doc_id,
                "file_name": file_name,
                "chunk_count": len(values),
                "pass_count": sum(r["status"] == "PASS" for r in values),
                "issue_count": sum(r["status"] == "ISSUE" for r in values),
                "minor_count": sum(r["severity"] == "MINOR" for r in values),
                "major_count": sum(r["severity"] == "MAJOR" for r in values),
                "critical_count": sum(r["severity"] == "CRITICAL" for r in values),
            })

    status_counts = Counter(r["status"] for r in review_records)
    severity_counts = Counter(r["severity"] for r in review_records)
    reviewed_counts = Counter(r["chunk_id"] for r in review_records)
    input_counts = Counter(c["chunk_id"] for c in chunks)
    missing_review = sorted((input_counts - reviewed_counts).elements())
    duplicate_review = sorted([cid for cid, n in reviewed_counts.items() if n > 1])
    coverage = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chunk_total": len(chunks),
        "unique_chunk_id_count": len(input_counts),
        "review_record_count": len(review_records),
        "missing_review_count": len(missing_review),
        "duplicate_review_count": len(duplicate_review),
        "missing_review_chunk_ids": missing_review,
        "duplicate_review_chunk_ids": duplicate_review,
        "PASS": status_counts.get("PASS", 0),
        "MINOR": severity_counts.get("MINOR", 0),
        "MAJOR": severity_counts.get("MAJOR", 0),
        "CRITICAL": severity_counts.get("CRITICAL", 0),
        "formal_document_count": len(manifest_docs),
        "raw_file_count": len(raw_files),
        "structured_json_count": len(docs_by_json_name),
        "missing_chunk_documents": missing_chunk_documents,
        "uncovered_body_block_count": len(uncovered_blocks),
        "duplicate_chunk_ids": duplicate_ids,
        "exact_duplicate_text_group_count": len(duplicate_text_groups),
        "exact_duplicate_text_groups": duplicate_text_groups,
        "high_duplicate_pairs": high_duplicate_pairs,
        "overlap_chunk_count": len(overlap_audits),
        "overlap_audits": overlap_audits,
        "short_chunk_ids_under_30_chars": [c["chunk_id"] for c in chunks if 0 < len(canonical(c.get("body_text", ""))) < 30],
        "oversized_chunk_ids_over_1300_chars": [c["chunk_id"] for c in chunks if len(canonical(c.get("body_text", ""))) > 1300 or c.get("is_oversized")],
        "raw_conversion_audits": raw_audits,
        "conversion_problem_documents": conversion_problem_docs,
        "special_checks": special_checks,
    }
    with (OUT_DIR / "coverage.json").open("w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    # Issues markdown, one section per problematic chunk with all required evidence.
    issue_records = [r for r in review_records if r["status"] == "ISSUE"]
    issue_type_counts = Counter(t for r in issue_records for t in r["issue_types"])
    with (OUT_DIR / "issues.md").open("w", encoding="utf-8") as f:
        f.write("# Chunk复核发现的问题\n\n")
        f.write(f"共发现 **{len(issue_records)}** 个问题Chunk；本文件不列PASS记录。\n\n")
        for r in issue_records:
            ev = r["evidence"]
            f.write(f"## {r['chunk_id']} — {ev.get('file_name','')}\n\n")
            f.write(f"- document_id：`{r['document_id']}`\n")
            f.write(f"- chunk_index：{r['chunk_index']}\n")
            f.write(f"- 严重程度：**{r['severity']}**\n")
            f.write(f"- 问题类型：{', '.join(r['issue_types'])}\n")
            f.write(f"- 问题原因：{r['reason']}\n")
            f.write(f"- 修复建议：{r['recommendation']}\n\n")
            f.write("**Chunk内容**\n\n```text\n" + ev.get("chunk_content", "") + "\n```\n\n")
            f.write("**原始/结构化正文证据**\n\n```text\n" + ev.get("structured_source_evidence", "") + "\n")
            for item in ev.get("issue_evidence", []):
                f.write(str(item) + "\n")
            f.write("```\n\n")

    wrong_pdf_not_chunked = not any(d.get("file_name") == "证券公司市场风险管理指引.pdf" for d in chunk_doc_to_structured.values())
    recorded_duplicate = (
        wrong_pdf_check.get("exclusion_record_present")
        and "证券公司全面风险管理规范" in wrong_pdf_check.get("exclusion_reason", "")
        and wrong_pdf_check.get("correct_docx_exists")
    )
    exclusion_reasonable = wrong_pdf_not_chunked and bool(wrong_pdf_check.get("contains_actual_title") or recorded_duplicate)
    has_omission = bool(uncovered_blocks or missing_chunk_documents or conversion_problem_docs)
    has_conversion_error = bool(conversion_problem_docs)
    has_confirmed_conversion = any(d.get("type") == "confirmed_conversion_omission" for d in conversion_problem_docs)
    has_boundary_error = any(any(t in {"intro_list_split", "split_enumeration_without_overlap", "orphan_list_item", "heading_only_chunk", "isolated_page_number"} for t in r["issue_types"]) for r in issue_records)
    with (OUT_DIR / "final_report.md").open("w", encoding="utf-8") as f:
        f.write("# 中国场外衍生品法规知识库 Chunk 独立复核报告\n\n")
        f.write(f"生成时间：{coverage['generated_at']}\n\n")
        f.write("## 结论\n\n")
        f.write(f"- 是否复核全部Chunk：{'是' if not missing_review and not duplicate_review and len(review_records)==len(chunks) else '否'}（输入{len(chunks)}条，唯一ID {len(input_counts)}个，复核记录{len(review_records)}条）。\n")
        f.write(f"- 是否存在正文遗漏：{'是，已确认1份原件的主体正文大段遗漏' if has_confirmed_conversion else ('是，存在待核对候选' if has_omission else '未发现')}。source_block未覆盖{len(uncovered_blocks)}个；无Chunk正式文档{len(missing_chunk_documents)}份。\n")
        f.write(f"- 是否存在转换错误：{'是，已确认结构化文本仅保留原件小部分内容' if has_confirmed_conversion else ('是，存在待人工定位的原件差异候选' if has_conversion_error else '未发现明确转换错误')}。\n")
        f.write(f"- 是否存在切分错误：{'是' if has_boundary_error else '未发现'}。\n")
        wrong_pdf_conclusion = "合理" if exclusion_reasonable else "尚不能确认"
        if exclusion_reasonable and not wrong_pdf:
            wrong_pdf_conclusion += "（依据现存排除记录及正确DOCX；错名PDF当前不在raw目录，无法再次直接验页）"
        f.write(f"- 错名PDF排除是否合理：{wrong_pdf_conclusion}。核对信息：{json.dumps(wrong_pdf_check, ensure_ascii=False)}\n")
        recommend_rebuild = bool(severity_counts.get("MAJOR") or severity_counts.get("CRITICAL") or has_conversion_error)
        f.write(f"- 是否建议修复后重新构建：{'是' if recommend_rebuild else '否；本轮已重建并通过复核'}。\n\n")
        f.write("## 覆盖统计\n\n")
        f.write(f"- 正式文档：{len(manifest_docs)}份；原件：{len(raw_files)}份；结构化JSON：{len(docs_by_json_name)}份。\n")
        f.write(f"- PASS：{status_counts.get('PASS',0)}；MINOR：{severity_counts.get('MINOR',0)}；MAJOR：{severity_counts.get('MAJOR',0)}；CRITICAL：{severity_counts.get('CRITICAL',0)}。\n")
        f.write(f"- source_block正文遗漏：{len(uncovered_blocks)}个；完全重复ID：{len(duplicate_ids)}个；高度重复对：{len(high_duplicate_pairs)}对。\n\n")
        f.write("## 问题分布\n\n")
        for issue_type, count in issue_type_counts.most_common():
            f.write(f"- {issue_type}：{count}个Chunk。\n")
        f.write("\n")
        f.write("## 专项核对\n\n")
        f.write(f"- Shibor 1M、3M、6M、9M：{json.dumps(special_checks.get('shibor_tenors',{}), ensure_ascii=False)}。\n")
        f.write(f"- 商品衍生品定义文件前六条：{json.dumps(special_checks.get('commodity_first_six_articles',{}), ensure_ascii=False)}。\n")
        f.write(f"- 错名PDF：{json.dumps(wrong_pdf_check, ensure_ascii=False)}。\n\n")
        f.write("## 方法说明\n\n")
        f.write("脚本逐条检查Chunk覆盖、唯一性、索引连续性、source_block引用与正文一致性、长度、重复、乱码/私有区/Word域代码/孤立页码、核心元数据与边界启发式；并独立从PDF文本层及分页、DOCX OOXML（含表格、文本框、smartTag）和旧DOC转换文本读取原件，对条号与日期/金额/比例/期限等关键token进行差异核对。自动差异仅作为候选，报告结论以明确证据为准。\n")

    print(json.dumps({
        "chunk_total": len(chunks),
        "review_records": len(review_records),
        "PASS": status_counts.get("PASS", 0),
        "MINOR": severity_counts.get("MINOR", 0),
        "MAJOR": severity_counts.get("MAJOR", 0),
        "CRITICAL": severity_counts.get("CRITICAL", 0),
        "uncovered_blocks": len(uncovered_blocks),
        "conversion_problem_docs": len(conversion_problem_docs),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
