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
ENUMERATION_INTRO_RE = re.compile(r"(?:如下|下列|包括|条件|材料|方法|情形|事项|款项|内容)[^。！？；;]{0,40}[：:]\s*$")
ENUMERATION_TAIL_RE = re.compile(r"(?:^|[。！？\n])([^。！？\n]{1,200}(?:如下|下列|包括|条件|材料|方法|情形|事项|款项|内容)[^。！？；;]{0,40}[：:]\s*)$")
ENUMERATION_CONTEXT_RE = re.compile(r"(?:^|[。！？\n])([^。！？\n]{0,180}?(?:如下|下列|包括|条件|材料|方法|情形|事项|款项|内容)[^。！？；;]{0,40}[：:])")
LIST_CONTINUATION_RE = re.compile(r"^(?:[（(][一二三四五六七八九十百\d]+[）)]|\d+[.、．])")
MID_SENTENCE_CONTINUATION_RE = re.compile(r"^(?:包括|以及|且|并且|并|或|其中|即|亦即|但|但是|除非|否则)")
PAREN_MARKER_RE = re.compile(r"[（(]([一二三四五六七八九十百\d]+)[）)]")
TERM_HEADING_RE = re.compile(r"(?m)^(\d+[.．]\s*(?:\n\s*)?\d+\s+[^\n]{2,220})")


def marker_ordinal(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if value.startswith("十") and value[1:] in digits:
        return 10 + digits[value[1:]]
    if value.endswith("十") and value[:-1] in digits:
        return digits[value[:-1]] * 10
    if "十" in value:
        left, right = value.split("十", 1)
        if left in digits and right in digits:
            return digits[left] * 10 + digits[right]
    return None


def continues_numbered_list(previous_text: str, current_text: str) -> bool:
    current_match = PAREN_MARKER_RE.match(current_text.lstrip())
    if not current_match:
        return False
    current_number = marker_ordinal(current_match.group(1))
    if current_number is None:
        return False
    previous_matches = list(PAREN_MARKER_RE.finditer(previous_text[-1200:]))
    if not previous_matches:
        return current_number == 1 and bool(ENUMERATION_CONTEXT_RE.search(previous_text))
    previous_number = marker_ordinal(previous_matches[-1].group(1))
    return previous_number is not None and current_number == previous_number + 1


def parent_context_from_previous(previous_text: str, current_text: str = "") -> str:
    """Return compact parent context for a list/mid-sentence continuation."""
    leading_marker = PAREN_MARKER_RE.match(current_text.lstrip())
    if leading_marker and not leading_marker.group(1).isdigit():
        top_level_matches = list(re.finditer(
            r"(?m)^([一二三四五六七八九十百]+、)\s*(?:\n\s*)?([^\n]{1,100})?",
            previous_text,
        ))
        if top_level_matches:
            marker, title = top_level_matches[-1].group(1), clean_text(top_level_matches[-1].group(2) or "")
            return clean_text(marker + (" " + title if title else ""))
    if leading_marker and leading_marker.group(1).isdigit():
        term_matches = list(TERM_HEADING_RE.finditer(previous_text))
        if term_matches:
            value = clean_text(term_matches[-1].group(1))
            boundary = re.search(r"[。；;]", value)
            return clean_text(value[:boundary.end()] if boundary else value[:220])
    intro_matches = list(ENUMERATION_CONTEXT_RE.finditer(previous_text))
    if intro_matches:
        return clean_text(intro_matches[-1].group(1))
    term_matches = list(TERM_HEADING_RE.finditer(previous_text))
    if term_matches:
        value = clean_text(term_matches[-1].group(1))
        # The definition label and first sentence are enough to identify the parent;
        # do not duplicate a full long definition in every continuation chunk.
        boundary = re.search(r"[。；;]", value)
        return clean_text(value[:boundary.end()] if boundary else value[:220])
    lines = [clean_text(line) for line in previous_text.splitlines() if clean_text(line)]
    for line_index in range(len(lines) - 1, -1, -1):
        line = lines[line_index]
        if re.match(r"^(?:第.+条|第.+章|第.+节|[一二三四五六七八九十百]+、|\d+[.．]\s*\d+)", line):
            if re.fullmatch(r"[一二三四五六七八九十百]+、", line) and line_index + 1 < len(lines):
                return clean_text(line + " " + lines[line_index + 1])[:220]
            return line[:220]
    return clean_text(previous_text[-180:])


def make_unit(node: Node, text: str | None = None, oversized_reason: str = "", *, include_descendant_articles: bool = True) -> Unit:
    body = clean_text(text if text is not None else render_node(node))
    articles = monotonic_articles(node) if include_descendant_articles else []
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
        if current and ENUMERATION_INTRO_RE.search(sentence):
            current_text = "".join(current)
            result.append(make_unit(node, current_text, "单个完整句子或字段行超过上限" if body_char_count(current_text) > config.MAX_CHARS else ""))
            current = [sentence]
            continue
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
            child_units.append(make_unit(node, own, include_descendant_articles=False))
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
        left_value = left.hierarchy.get(key, "")
        right_value = right.hierarchy.get(key, "")
        if key in {"part_title", "attachment_name"} and left_value != right_value:
            return False
        if left_value and right_value and left_value != right_value:
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
        carry_text = current[-1].body_text + "\n" + unit.body_text if current else ""
        if exceeds and len(current) > 1 and ENUMERATION_INTRO_RE.search(current[-1].body_text) and body_char_count(carry_text) <= config.MAX_CHARS:
            chunks.append(draft(current[:-1]))
            current = [current[-1], unit]
        elif unit_index in forced_breaks or exceeds or hierarchy_break or (semantic_break and body_char_count(current_text) >= config.TARGET_MIN_CHARS):
            chunks.append(draft(current))
            current = [unit]
        else:
            current.append(unit)
    if current:
        chunks.append(draft(current))
    # 显式分部/附件边界必须与前文断开，但标题本身不能成为无正文Chunk。
    # 若标题与其后第一个正文块可完整容纳，则向后合并。
    index = 0
    while index + 1 < len(chunks):
        heading = chunks[index]
        following = chunks[index + 1]
        heading_text = "\n".join(unit.body_text for unit in heading.units)
        merged = "\n".join(unit.body_text for unit in heading.units + following.units)
        structural_only = bool(heading.units) and all(unit.kind in {"part", "chapter", "section", "attachment"} for unit in heading.units)
        if structural_only and body_char_count(heading_text) < config.MIN_CHARS and body_char_count(merged) <= config.MAX_CHARS and compatible_hierarchy(heading.units[-1], following.units[0]):
            following.units = heading.units + following.units
            following.hierarchy = merged_hierarchy(following.units)
            chunks.pop(index)
        else:
            index += 1
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
        previous_text = "\n".join(unit.body_text for unit in previous.units)
        first_sequence = current.units[0].sequence_index if current.units else -1
        same_article = bool(
            previous.units and current.units
            and previous.units[-1].article_start
            and previous.units[-1].article_start == current.units[0].article_start
        )
        numbered_continuation = continues_numbered_list(previous_text, current_text)
        sentence_continuation = bool(
            re.search(r"[,，:]\s*$", previous_text)
            and MID_SENTENCE_CONTINUATION_RE.match(current_text.lstrip())
        )
        enumeration_continuation = bool(
            ENUMERATION_INTRO_RE.search(previous_text)
            or numbered_continuation
            or sentence_continuation
            or (same_article and LIST_CONTINUATION_RE.search(current_text.lstrip()) and re.search(r"[；;]\s*$", previous_text))
        )
        dependency = depends_on_previous(current_text)
        if not (dependency or enumeration_continuation or first_sequence in llm_overlaps) or not previous.units:
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
        elif enumeration_continuation or dependency:
            match = ENUMERATION_TAIL_RE.search(previous_text)
            if match:
                tail = clean_text(match.group(1))
            else:
                matches = list(ENUMERATION_CONTEXT_RE.finditer(previous_text))
                tail = clean_text(matches[-1].group(1)) if matches else parent_context_from_previous(previous_text, current_text)
            if tail and body_char_count(tail + "\n" + current_text) <= config.MAX_CHARS:
                source = previous.units[-1]
                current.units.insert(0, Unit(
                    body_text=tail,
                    kind="text",
                    hierarchy=dict(source.hierarchy),
                    article_start=source.article_start,
                    article_end=source.article_end,
                    attachment_name=source.attachment_name,
                    block_ids=[],
                    sequence_index=source.sequence_index,
                ))
                current.is_overlapping = True
                current.overlap_source_index = index - 1
            elif tail:
                # 当前正文已接近上限时，将最短引导语作为检索上下文而非
                # 正文字符计数的一部分，仍保留可追溯的重叠来源。
                current.context_only_prefix = tail
                current.is_overlapping = True
                current.overlap_source_index = index - 1

        # Whole-unit overlap can still repeat only a terse list item. Add the
        # parent definition/article or enumeration introduction as retrieval-only
        # context so the new Chunk never begins with an unexplained “(二)/(2)”.
        if current.is_overlapping and (LIST_CONTINUATION_RE.search(current_text.lstrip()) or sentence_continuation):
            parent_context = parent_context_from_previous(previous_text, current_text)
            if parent_context and compact(parent_context) not in compact(current_text[:320]):
                prefixes = [value for value in (current.context_only_prefix, parent_context) if value]
                current.context_only_prefix = "\n".join(dict.fromkeys(prefixes))


def coalesce_structural_units(document: ParsedDocument, units: list[Unit]) -> list[Unit]:
    # Legacy Word files sometimes split the cover title across two paragraphs,
    # e.g. ``…商品衍生品定义文件`` + ``(2015年版)``.  When those
    # consecutive units reconstruct the authoritative document title and are
    # immediately followed by a declaration, keep their source trace on the
    # declaration instead of emitting a title-only chunk.
    for width in range(min(3, len(units) - 1), 1, -1):
        following = units[width] if width < len(units) else None
        reconstructed = "".join(unit.body_text for unit in units[:width])
        if (
            following and following.kind == "part" and following.hierarchy.get("part_title") in {"声明", "前言"}
            and compact(reconstructed) == compact(document.metadata.get("document_title", ""))
        ):
            leading_ids = [block_id for unit in units[:width] for block_id in unit.block_ids]
            following.block_ids = list(dict.fromkeys(leading_ids + following.block_ids))
            units = units[width:]
            break
    if len(units) > 1 and compact(units[0].body_text) == compact(document.metadata.get("document_title", "")):
        units[1].block_ids = list(dict.fromkeys(units[0].block_ids + units[1].block_ids))
        units = units[1:]
    result: list[Unit] = []
    index = 0
    while index < len(units):
        current = units[index]
        following = units[index + 1] if index + 1 < len(units) else None
        if (
            following and current.kind == "part" and following.kind == "part"
            and body_char_count(current.body_text) < 20
            and compact(current.body_text) in compact(following.body_text)
        ):
            following.block_ids = list(dict.fromkeys(current.block_ids + following.block_ids))
            index += 1
            continue
        result.append(current)
        index += 1
    return result


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
    units = coalesce_structural_units(document, units)
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
        retrieval_body = "\n".join(value for value in (chunk.context_only_prefix, body) if value)
        text = retrieval_body if not prefix or retrieval_body.startswith(prefix) else prefix + "\n" + retrieval_body
        rendered.append({"body": body, "text": text})
    return chunks, rendered, llm_warnings
