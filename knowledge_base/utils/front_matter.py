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
ATTACHMENT_LABEL_RE = re.compile(r"^附件\s*[一二三四五六七八九十百\d]+$")
VERSION_SUFFIX_RE = re.compile(r"(?:19|20)\d{2}年(?:版|修订|修正版)$")
PUBLICATION_WRAPPER_RE = re.compile(
    r"(?:"
    r"(?:现予公布|现公布|予以公布|现予发布|现发布).{0,180}《[^》]{2,120}》|"
    r"《[^》]{2,120}》.{0,240}(?:现予公布|现公布|予以公布|现予发布|现发布)"
    r")"
)
DOCUMENT_NUMBER_PREFIX_RE = re.compile(
    r"^(?:中国人民银行|中国证券监督管理委员会|中国证监会|国家金融监督管理总局|"
    r"中国银保监会|中国银监会|中国保监会)(?:公告|令)$"
)
DOCUMENT_NUMBER_SUFFIX_RE = re.compile(r"^[〔【\[]\s*\d{4}\s*[〕】\]]\s*第?\s*\d+\s*号$")
SIGNATURE_LINE_RE = re.compile(r"^(?:中华人民共和国主席|主席|总理|主任|会长|局长)\s*[一-鿿·]{1,12}$")
STANDALONE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


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
                if index < 3 and ATTACHMENT_LABEL_RE.fullmatch(line):
                    continue
                return index
    return min(len(blocks), 60)


def _authority_values(metadata: dict[str, Any]) -> set[str]:
    value = clean_text(str(metadata.get("issuing_authority", "")))
    values = {compact(part) for part in re.split(r"[、，,；;/]", value) if compact(part)}
    return values


def _title_variants(metadata: dict[str, Any]) -> set[str]:
    """Return conservative compact variants used only for cover-title detection."""

    title = compact_title(str(metadata.get("document_title", "")))
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
        for width in range(1, 4):
            end = start + width
            if end > limit or blocks[end - 1].source_kind == "table":
                break
            joined += compact_title(clean_text(blocks[end - 1].text))
            if joined not in variants:
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
            if is_split or is_guide_cover or has_cover_tail:
                positions.update(range(start, end))
                break
    return positions


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
    original_hash = previous.get("original_text_sha256") or _blocks_sha256(blocks)
    chars_before = int(previous.get("chars_before") or sum(body_char_count(block.text) for block in blocks))
    removed: list[dict[str, Any]] = list(previous.get("removed_front_matter", []))
    log: list[dict[str, Any]] = list(previous.get("cleaning_log", []))
    already_removed_ids = {item.get("block_id") for item in removed}

    prefix_end = _first_structure_index(blocks)
    title = compact_title(str(document.metadata.get("document_title", "")))
    title_positions = [
        index
        for index, block in enumerate(blocks[:prefix_end])
        if title and compact_title(clean_text(block.text)) == title
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
        compact_title(title)
        for index in wrapper_positions
        for title in re.findall(r"《([^》]{2,120})》", clean_text(blocks[index].text))
    }
    wrapper_title_positions = {
        index
        for index, block in enumerate(blocks[:prefix_end])
        if compact_title(clean_text(block.text)) in wrapper_titles
    }
    cover_title_positions.update(wrapper_title_positions)
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
            elif index in wrapper_positions:
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
        "status": "changed" if removed else "unchanged",
        "original_text_sha256": original_hash,
        "clean_text_sha256": clean_hash,
        "chars_before": chars_before,
        "chars_after": chars_after,
        "removed_character_count": max(0, chars_before - chars_after),
        "rule_hits": sorted({item["rule_id"] for item in removed}),
        "removed_front_matter": removed,
        "cleaning_log": log,
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
