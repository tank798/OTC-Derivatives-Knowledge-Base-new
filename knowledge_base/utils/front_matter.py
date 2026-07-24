from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import config
from models import ParsedDocument, SourceBlock
from utils.metadata import compact_title
from utils.text import body_char_count, clean_text, compact


STRUCTURE_START_RE = re.compile(
    r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节条款]|"
    r"[一二三四五六七八九十百]+[、.]|"
    r"[（(][一二三四五六七八九十百\d]+[）)]|"
    r"\d+(?:\.\d+){1,4}(?:\s|$)|附件|附录)"
)
DOCUMENT_NUMBER_LINE_RE = re.compile(
    r"^(?:(?:中华人民共和国)?主席令第?\s*[\d一二三四五六七八九十百]+号|"
    r"(?:中国证券监督管理委员会|中国证监会|中国人民银行|国家金融监督管理总局|"
    r"中国银保监会|中国银监会|中国保监会)(?:公告|令)?\s*[〔【\[]?\d{4}[〕】\]]?\s*第?\s*\d+号|"
    r"[一-鿿]{1,18}(?:发|上|会|办|规|公告)\s*[〔【\[]\d{4}[〕】\]]\s*第?\s*\d+号|"
    r"[一-鿿]{1,18}[〔【\[]\d{4}[〕】\]]\s*第?\s*\d+号)$"
)
PAREN_PROMULGATION_RE = re.compile(
    r"^[（(].{0,220}(?:公布|发布|施行|实施|修订|修正|通过).{0,120}[）)]$"
)
REVISION_NOTE_RE = re.compile(
    r"^(?=.{4,220}$)(?:根据.{0,160})?(?:19|20)\d{2}年.{0,160}(?:修订|修正|发布|公布)"
)
DATE_LINE_RE = re.compile(r"^(?:19|20)\d{2}年\d{1,2}月\d{1,2}日$")
CHINESE_DATE_LINE_RE = re.compile(r"^[〇零一二三四五六七八九十]{4}年[〇零一二三四五六七八九十]{1,3}月[〇零一二三四五六七八九十]{1,3}日$")
MONTH_LINE_RE = re.compile(r"^(?:19|20)\d{2}年\d{1,2}月$")
ATTACHMENT_LABEL_RE = re.compile(r"^附件(?:\s*[一二三四五六七八九十百\d]+)?$")
VERSION_SUFFIX_RE = re.compile(r"(?:19|20)\d{2}年(?:版|修订|修正版)$")
PUBLICATION_WRAPPER_RE = re.compile(
    r"(?:"
    r"(?:现予公布|现公布|予以公布|现予发布|现发布).{0,180}《[^》]{2,120}》|"
    r"《[^》]{2,120}》.{0,240}(?:现予公布|现公布|予以公布|现予发布|现发布)"
    r")"
)
PUBLICATION_SUMMARY_RE = re.compile(
    r"(?=.{30,1000}$)(?:根据《[^》]{2,120}》.{0,220})?"
    r"(?:我会|本会|现).{0,120}(?:修订|修正|发布|公布).{0,320}"
    r"(?:施行|实施|生效)(?:.{0,180}(?:同时废止|予以废止|废止))?"
)
DOCUMENT_NUMBER_PREFIX_RE = re.compile(
    r"^(?:中国人民银行|中国证券监督管理委员会|中国证监会|国家金融监督管理总局|"
    r"中国银保监会|中国银监会|中国保监会)(?:公告|令)$"
)
DOCUMENT_NUMBER_SUFFIX_RE = re.compile(r"^[〔【\[]\s*\d{4}\s*[〕】\]]\s*第?\s*\d+\s*号$")
SIGNATURE_LINE_RE = re.compile(r"^(?:中华人民共和国主席|主席|总理|主任|会长|局长)\s*[一-鿿·]{1,12}$")
STANDALONE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
ATTACHMENT_DIRECTORY_START_RE = re.compile(r"^附件\s*[:：]\s*1[.、．]\s*.+")
ATTACHMENT_DIRECTORY_ITEM_RE = re.compile(r"^\d+[.、．]\s*.+")


def _blocks_sha256(blocks: list[SourceBlock]) -> str:
    payload = [
        {
            "block_id": block.block_id,
            "text": clean_text(block.text),
            "style": block.style,
            "source_kind": block.source_kind,
            "page": block.page,
        }
        for block in blocks
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _first_structure_index(blocks: list[SourceBlock]) -> int:
    for index, block in enumerate(blocks[:120]):
        for line in clean_text(block.text).splitlines():
            if STRUCTURE_START_RE.match(line):
                # “附件”常作为下载文件的封面标签，后接本文标题。首三
                # 个 block 内先把它留给标题匹配规则判断，避免把清洗
                # 窗口错误截断在第 0 个 block。未匹配本文标题的附件
                # 标题不会被删除，仍会保留在正文中。
                if index < 3 and (
                    ATTACHMENT_LABEL_RE.fullmatch(line)
                    or re.match(r"^附件\s*[:：]\s*\S", line)
                ):
                    continue
                return index
    return min(len(blocks), 60)


def _authority_values(metadata: dict[str, Any]) -> set[str]:
    value = clean_text(str(metadata.get("issuing_authority", "")))
    values = {compact(part) for part in re.split(r"[、，,；;/]", value) if compact(part)}
    return values


def _cover_title_key(value: str) -> str:
    """Normalize harmless separators only for high-confidence cover matching."""

    return re.sub(r"[、，,。:：；;·]", "", compact_title(value))


def _title_variants(metadata: dict[str, Any]) -> set[str]:
    """Return conservative compact variants used only for cover-title detection."""

    title = _cover_title_key(str(metadata.get("document_title", "")))
    if not title:
        return set()
    variants = {title, VERSION_SUFFIX_RE.sub("", title)}
    for authority in _authority_values(metadata):
        for value in list(variants):
            if value.startswith(authority) and len(value) > len(authority) + 4:
                variants.add(value[len(authority):])
    return {value for value in variants if len(value) >= 6}


def _cover_title_positions(
    blocks: list[SourceBlock],
    prefix_end: int,
    metadata: dict[str, Any],
) -> set[int]:
    """Find a cover title even when Word/PDF split it across several paragraphs."""

    variants = _title_variants(metadata)
    if not variants:
        return set()
    limit = min(prefix_end, 12)
    positions: set[int] = set()
    for start in range(limit):
        if blocks[start].source_kind == "table":
            continue
        joined = ""
        for width in range(1, 5):
            end = start + width
            if end > limit or blocks[end - 1].source_kind == "table":
                break
            joined += _cover_title_key(clean_text(blocks[end - 1].text))
            without_attachment_prefix = re.sub(r"^附件[:：]?", "", joined)
            if joined not in variants and without_attachment_prefix not in variants:
                continue
            following = [
                compact(clean_text(block.text))
                for block in blocks[end:min(prefix_end, end + 5)]
            ]
            is_split = width > 1
            is_guide_cover = any(
                text.startswith(("说明及声明", "说明和声明"))
                for text in following
            )
            has_cover_tail = any(
                text in _authority_values(metadata) or MONTH_LINE_RE.fullmatch(text)
                for text in following
            )
            has_attachment_lead = (
                (
                    start > 0
                    and ATTACHMENT_LABEL_RE.fullmatch(clean_text(blocks[start - 1].text))
                )
                or bool(re.match(r"^附件\s*[:：]", clean_text(blocks[start].text)))
            )
            if is_split or is_guide_cover or has_cover_tail or has_attachment_lead:
                title_start = (
                    start + 1
                    if ATTACHMENT_LABEL_RE.fullmatch(clean_text(blocks[start].text))
                    else start
                )
                positions.update(range(title_start, end))
                break
    return positions


def _cover_attachment_directory_positions(blocks: list[SourceBlock]) -> set[int]:
    """Find a cover-page attachment list, not substantive appendices."""

    if not blocks:
        return set()
    first_page = blocks[0].page
    limit = min(len(blocks), 20)
    start = next(
        (
            index for index, block in enumerate(blocks[:limit])
            if block.page == first_page
            and ATTACHMENT_DIRECTORY_START_RE.match(clean_text(block.text))
        ),
        None,
    )
    if start is None:
        return set()
    positions = {start}
    expected = 2
    for index in range(start + 1, limit):
        block = blocks[index]
        if block.page != first_page:
            break
        match = re.match(r"^(\d+)[.、．]\s*.+", clean_text(block.text))
        if not match or int(match.group(1)) != expected:
            break
        positions.add(index)
        expected += 1
    return positions if len(positions) >= 2 else set()


def _trailing_source_reference_positions(blocks: list[SourceBlock]) -> set[int]:
    """Find a short source-link appendix placed after the final legal structure."""

    structure_positions = []
    for index, block in enumerate(blocks):
        if block.source_kind == "table":
            continue
        if any(STRUCTURE_START_RE.match(line) for line in clean_text(block.text).splitlines()):
            structure_positions.append(index)
    if not structure_positions:
        return set()
    tail_start = structure_positions[-1] + 1
    tail = blocks[tail_start:]
    if not tail or len(tail) > 12:
        return set()
    texts = [clean_text(block.text) for block in tail]
    if not any(STANDALONE_URL_RE.fullmatch(text) for text in texts):
        return set()
    if any(block.source_kind == "table" or body_char_count(text) > 160 for block, text in zip(tail, texts)):
        return set()
    if any(STRUCTURE_START_RE.match(text) for text in texts):
        return set()
    return set(range(tail_start, len(blocks)))


def _record(block: SourceBlock, rule_id: str, action: str = "moved_to_front_matter") -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "page": block.page,
        "source_kind": block.source_kind,
        "rule_id": rule_id,
        "action": action,
        "text": clean_text(block.text),
        "character_count": body_char_count(block.text),
    }


def clean_front_matter(document: ParsedDocument) -> ParsedDocument:
    """Move high-confidence publication metadata out of Chunk-eligible blocks.

    The rules are deliberately position-aware.  They only inspect the bounded
    prefix before the first legal/list structure and never remove matching text
    from articles, tables or appendices.
    """

    blocks = list(document.blocks)
    previous = dict(document.cleaning or {})
    content_overrides: list[str] = list(previous.get("content_overrides", []))
    content_override_rule_hits: list[str] = list(previous.get("content_override_rule_hits", []))
    original_hash = previous.get("original_text_sha256") or _blocks_sha256(blocks)
    chars_before = int(previous.get("chars_before") or sum(body_char_count(block.text) for block in blocks))
    removed: list[dict[str, Any]] = list(previous.get("removed_front_matter", []))
    log: list[dict[str, Any]] = list(previous.get("cleaning_log", []))
    already_removed_ids = {item.get("block_id") for item in removed}

    prefix_end = _first_structure_index(blocks)
    title_variants = _title_variants(document.metadata)
    if blocks:
        first_without_attachment = re.sub(
            r"^附件\s*[:：]?",
            "",
            _cover_title_key(clean_text(blocks[0].text)),
        )
        if first_without_attachment in title_variants:
            prefix_end = next(
                (
                    index for index, block in enumerate(blocks[1:120], start=1)
                    if any(STRUCTURE_START_RE.match(line) for line in clean_text(block.text).splitlines())
                ),
                min(len(blocks), 12),
            )
    title = _cover_title_key(str(document.metadata.get("document_title", "")))
    title_positions = [
        index
        for index, block in enumerate(blocks[:prefix_end])
        if title and _cover_title_key(clean_text(block.text)) == title
    ]
    cover_title_positions = _cover_title_positions(
        blocks,
        prefix_end,
        document.metadata,
    )
    duplicate_title_positions = set(title_positions[:-1]) if len(title_positions) > 1 else set()
    wrapper_positions = {
        index
        for index, block in enumerate(blocks[:prefix_end])
        if (
            block.source_kind != "table"
            and PUBLICATION_WRAPPER_RE.search(clean_text(block.text))
            and "现就有关事项通知如下" not in clean_text(block.text)
        )
    }
    wrapper_titles = {
        _cover_title_key(title)
        for index in wrapper_positions
        for title in re.findall(r"《([^》]{2,120})》", clean_text(blocks[index].text))
    }
    wrapper_title_positions = {
        index
        for index, block in enumerate(blocks[:prefix_end])
        if _cover_title_key(clean_text(block.text)) in wrapper_titles
    }
    cover_title_positions.update(wrapper_title_positions)
    cover_attachment_directory_positions = _cover_attachment_directory_positions(blocks)
    split_document_number_positions: set[int] = set()
    for index, block in enumerate(blocks[:max(prefix_end - 1, 0)]):
        prefix = clean_text(block.text)
        suffix = clean_text(blocks[index + 1].text)
        if DOCUMENT_NUMBER_PREFIX_RE.fullmatch(prefix) and DOCUMENT_NUMBER_SUFFIX_RE.fullmatch(suffix):
            split_document_number_positions.update({index, index + 1})
            if not document.metadata.get("document_number"):
                document.metadata["document_number"] = re.sub(r"\s+", "", prefix + suffix)
    has_publication_wrapper = bool(wrapper_positions)
    all_formal_title_positions = sorted(set(title_positions) | wrapper_title_positions)
    last_title = all_formal_title_positions[-1] if all_formal_title_positions else -1
    authorities = _authority_values(document.metadata)
    trailing_reference_positions = _trailing_source_reference_positions(blocks)

    kept: list[SourceBlock] = []
    for index, block in enumerate(blocks):
        text = clean_text(block.text)
        compact_text = compact(text)
        rule_id = ""
        if index in trailing_reference_positions:
            rule_id = "trailing_source_reference"
        elif index in cover_attachment_directory_positions:
            rule_id = "cover_attachment_directory"
        elif index < prefix_end and block.source_kind != "table":
            if index in split_document_number_positions:
                rule_id = "split_front_document_number"
            elif index in cover_title_positions:
                rule_id = "cover_document_title"
            elif (
                any(index < title_index <= index + 2 for title_index in cover_title_positions)
                and ATTACHMENT_LABEL_RE.fullmatch(text)
            ):
                rule_id = "cover_attachment_label"
            elif (
                any(title_index < index <= title_index + 4 for title_index in cover_title_positions)
                and compact_text in authorities
            ):
                rule_id = "cover_authority"
            elif (
                any(title_index < index <= title_index + 4 for title_index in cover_title_positions)
                and MONTH_LINE_RE.fullmatch(text)
            ):
                rule_id = "cover_month"
            elif index in duplicate_title_positions:
                rule_id = "duplicate_front_title"
            elif DOCUMENT_NUMBER_LINE_RE.fullmatch(text):
                rule_id = "standalone_front_document_number"
                if not document.metadata.get("document_number"):
                    document.metadata["document_number"] = re.sub(r"\s+", "", text)
            elif PAREN_PROMULGATION_RE.fullmatch(text):
                rule_id = "front_promulgation_parenthetical"
            elif (
                index in wrapper_positions
                or (
                    PUBLICATION_SUMMARY_RE.search(text)
                    and "现就有关事项通知如下" not in text
                )
            ):
                rule_id = "publication_wrapper"
            elif REVISION_NOTE_RE.match(text) and not STRUCTURE_START_RE.match(text):
                rule_id = "front_revision_history"
            elif has_publication_wrapper and index < last_title and DATE_LINE_RE.fullmatch(text):
                rule_id = "publication_signature_date"
            elif has_publication_wrapper and index < last_title and CHINESE_DATE_LINE_RE.fullmatch(text):
                rule_id = "publication_signature_date"
            elif has_publication_wrapper and index < last_title and compact_text in authorities:
                rule_id = "publication_signature_authority"
            elif has_publication_wrapper and index < last_title and SIGNATURE_LINE_RE.fullmatch(text):
                rule_id = "publication_signature_officer"

        if rule_id:
            if rule_id in {"publication_wrapper", "front_revision_history"}:
                document.metadata.setdefault("version_note", text)
            if block.block_id not in already_removed_ids:
                item = _record(block, rule_id)
                removed.append(item)
                log.append(item)
                already_removed_ids.add(block.block_id)
            continue
        block.region = "body"
        kept.append(block)

    document.blocks = kept
    clean_hash = _blocks_sha256(kept)
    chars_after = sum(body_char_count(block.text) for block in kept)
    document.cleaning = {
        "cleaning_rule_version": config.CLEANING_RULE_VERSION,
        "status": "changed" if removed or content_overrides else "unchanged",
        "original_text_sha256": original_hash,
        "clean_text_sha256": clean_hash,
        "chars_before": chars_before,
        "chars_after": chars_after,
        "removed_character_count": max(0, chars_before - chars_after),
        "rule_hits": sorted({item["rule_id"] for item in removed}),
        "removed_front_matter": removed,
        "cleaning_log": log,
        "content_overrides": content_overrides,
        "content_override_rule_hits": content_override_rule_hits,
        "chunk_eligible_block_ids": [block.block_id for block in kept],
    }
    if removed:
        document.warnings = [
            warning for warning in document.warnings
            if not warning.startswith("前置发布信息清洗：")
        ]
        document.warnings.append(
            f"前置发布信息清洗：移出{len(removed)}个block，规则"
            + "、".join(document.cleaning["rule_hits"])
        )
    return document
