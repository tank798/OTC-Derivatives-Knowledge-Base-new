from __future__ import annotations

import re

import config
from chunkers.semantic import clear_topic_change, depends_on_previous, valuable_short_unit
from chunkers.semantic_llm import review_boundaries
from chunkers.structure import build_tree, containing_article, descendant_block_ids, hierarchy_for, monotonic_articles, render_node
from models import ChunkDraft, Node, ParsedDocument, Unit
from utils.text import body_char_count, clean_text, compact

SENTENCE_RE = re.compile(r"(?<=[。！？；])")
SECONDARY_RE = re.compile(r"(?<=[，：,;:])")


def make_unit(node: Node, text: str | None = None, oversized_reason: str = "") -> Unit:
    body = clean_text(text if text is not None else render_node(node))
    articles = monotonic_articles(node)
    article_context = containing_article(node)
    hierarchy = hierarchy_for(node)
    return Unit(
        body_text=body,
        kind=node.kind,
        hierarchy=hierarchy,
        article_start=articles[0] if articles else article_context,
        article_end=articles[-1] if articles else article_context,
        attachment_name=hierarchy.get("attachment_name", ""),
        block_ids=descendant_block_ids(node),
        is_oversized=bool(oversized_reason),
        oversized_reason=oversized_reason,
    )


def split_complete_sentences(node: Node, text: str) -> list[Unit]:
    sentences = [clean_text(value) for value in SENTENCE_RE.split(text) if clean_text(value)]
    if len(sentences) <= 1:
        sentences = [clean_text(value) for value in SECONDARY_RE.split(text) if clean_text(value)]
    if len(sentences) <= 1:
        return [make_unit(node, text, "单个完整语义单元无可靠切分边界")]
    result: list[Unit] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = "".join(current + [sentence])
        if current and body_char_count(candidate) > config.MAX_CHARS:
            current_text = "".join(current)
            reason = "单个完整句子或字段行超过上限" if body_char_count(current_text) > config.MAX_CHARS else ""
            result.append(make_unit(node, current_text, reason))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        reason = "单个完整句子超过上限" if body_char_count("".join(current)) > config.MAX_CHARS else ""
        result.append(make_unit(node, "".join(current), reason))
    return result


def split_markdown_table(node: Node, text: str) -> list[Unit]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or not lines[0].lstrip().startswith("|"):
        return split_complete_sentences(node, text)
    prefix = lines[:2]
    rows = lines[2:]
    result: list[Unit] = []
    current: list[str] = []
    for row in rows:
        candidate = "\n".join(prefix + current + [row])
        if current and body_char_count(candidate) > config.MAX_CHARS:
            result.append(make_unit(node, "\n".join(prefix + current)))
            current = [row]
        else:
            current.append(row)
    if current:
        value = "\n".join(prefix + current)
        reason = "单个表格行超过上限，为保留行结构未拆分" if body_char_count(value) > config.MAX_CHARS else ""
        result.append(make_unit(node, value, reason))
    return result


def split_node(node: Node) -> list[Unit]:
    rendered = render_node(node)
    if not rendered:
        return []
    if body_char_count(rendered) <= config.MAX_CHARS:
        return [make_unit(node)]
    if node.kind == "table":
        return split_markdown_table(node, rendered)
    child_units: list[Unit] = []
    if node.own_text:
        own = clean_text("\n".join(part for part in (node.title, node.own_text) if part))
        if body_char_count(own) <= config.MAX_CHARS:
            child_units.append(make_unit(node, own))
        else:
            child_units.extend(split_complete_sentences(node, own))
    for child in node.children:
        child_units.extend(split_node(child))
    if child_units:
        if node.block_ids:
            child_units[0].block_ids = list(dict.fromkeys(node.block_ids + child_units[0].block_ids))
        return child_units
    return split_complete_sentences(node, rendered)


def compatible_hierarchy(left: Unit, right: Unit) -> bool:
    for key in ("part_title", "chapter_title", "section_title", "attachment_name"):
        if left.hierarchy.get(key) and right.hierarchy.get(key) and left.hierarchy[key] != right.hierarchy[key]:
            return False
    return True


def merged_hierarchy(units: list[Unit]) -> dict[str, str]:
    keys = ("part_title", "chapter_title", "section_title", "article_title", "paragraph_title", "attachment_name")
    result: dict[str, str] = {}
    for key in keys:
        values = list(dict.fromkeys(unit.hierarchy.get(key, "") for unit in units if unit.hierarchy.get(key, "")))
        result[key] = values[0] if len(values) == 1 else ""
    return result


def draft(units: list[Unit]) -> ChunkDraft:
    return ChunkDraft(
        units,
        merged_hierarchy(units),
        is_oversized=any(item.is_oversized for item in units),
        oversized_reason="；".join(item.oversized_reason for item in units if item.oversized_reason),
    )


def combine_units(units: list[Unit], forced_breaks: set[int] | None = None) -> list[ChunkDraft]:
    forced_breaks = forced_breaks or set()
    chunks: list[ChunkDraft] = []
    current: list[Unit] = []
    for unit_index, unit in enumerate(units):
        if not current:
            current = [unit]
            continue
        current_text = "\n".join(item.body_text for item in current)
        candidate_text = current_text + "\n" + unit.body_text
        semantic_break = config.ENABLE_SEMANTIC_CHUNKING and clear_topic_change(current[-1].body_text, unit.body_text)
        hierarchy_break = not compatible_hierarchy(current[-1], unit)
        exceeds = body_char_count(candidate_text) > config.MAX_CHARS
        if unit_index in forced_breaks or exceeds or hierarchy_break or (semantic_break and body_char_count(current_text) >= config.TARGET_MIN_CHARS):
            chunks.append(draft(current))
            current = [unit]
        else:
            current.append(unit)
    if current:
        chunks.append(draft(current))
    # 合并无独立检索价值的过短尾块。
    index = 1
    while index < len(chunks):
        chunk = chunks[index]
        text = "\n".join(unit.body_text for unit in chunk.units)
        previous = chunks[index - 1]
        merged = "\n".join(unit.body_text for unit in previous.units + chunk.units)
        if body_char_count(text) < config.MIN_CHARS and not valuable_short_unit(text) and body_char_count(merged) <= config.MAX_CHARS and compatible_hierarchy(previous.units[-1], chunk.units[0]):
            previous.units.extend(chunk.units)
            previous.hierarchy = merged_hierarchy(previous.units)
            chunks.pop(index)
        else:
            index += 1
    return chunks


def apply_structural_overlap(chunks: list[ChunkDraft], llm_overlaps: set[int] | None = None) -> None:
    llm_overlaps = llm_overlaps or set()
    for index in range(1, len(chunks)):
        current = chunks[index]
        previous = chunks[index - 1]
        current_text = "\n".join(unit.body_text for unit in current.units)
        first_sequence = current.units[0].sequence_index if current.units else -1
        if not (depends_on_previous(current_text) or first_sequence in llm_overlaps) or not previous.units:
            continue
        candidates = [unit for unit in previous.units[-config.MAX_OVERLAP_ARTICLES:] if unit.kind in {"article", "paragraph", "item", "subitem", "text"}]
        if not candidates:
            candidates = previous.units[-1:]
        # 从最近的完整结构单元开始，在20%建议值和总上限内重叠。
        selected: list[Unit] = []
        for unit in reversed(candidates):
            overlap_text = "\n".join(item.body_text for item in [unit] + selected)
            combined = overlap_text + "\n" + current_text
            if body_char_count(combined) <= config.MAX_CHARS and body_char_count(overlap_text) <= max(int(body_char_count(current_text) * 0.2), 120):
                selected.insert(0, unit)
        if selected:
            current.units = selected + current.units
            current.is_overlapping = True
            current.overlap_source_index = index - 1


def context_prefix(document: ParsedDocument, hierarchy: dict[str, str], body: str) -> str:
    values = [document.metadata.get("document_title", "")]
    values.extend(hierarchy.get(key, "") for key in ("part_title", "chapter_title", "section_title", "article_title", "paragraph_title", "attachment_name"))
    result: list[str] = []
    body_lead = body[:240]
    compact_lead = compact(body_lead)
    for value in values:
        if value and value not in result and compact(value) not in compact_lead:
            result.append(value)
    return "\n".join(result)


def chunk_document(document: ParsedDocument, semantic_cache_path=None) -> tuple[list[ChunkDraft], list[dict[str, str]], list[str]]:
    root = build_tree(document)
    units: list[Unit] = []
    for child in root.children:
        units.extend(split_node(child))
    for index, unit in enumerate(units):
        unit.sequence_index = index
    llm_breaks: set[int] = set()
    llm_overlaps: set[int] = set()
    llm_warnings: list[str] = []
    if semantic_cache_path is not None:
        llm_breaks, llm_overlaps, llm_warnings = review_boundaries(document.metadata.get("document_title", ""), units, semantic_cache_path)
    chunks = combine_units(units, llm_breaks)
    apply_structural_overlap(chunks, llm_overlaps)
    rendered: list[dict[str, str]] = []
    for chunk in chunks:
        body = "\n".join(unit.body_text for unit in chunk.units)
        prefix = context_prefix(document, chunk.hierarchy, body)
        text = body if not prefix or body.startswith(prefix) else prefix + "\n" + body
        rendered.append({"body": body, "text": text})
    return chunks, rendered, llm_warnings
