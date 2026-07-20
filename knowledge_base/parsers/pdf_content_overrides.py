from __future__ import annotations

from pathlib import Path
import re

from models import SourceBlock
from utils.text import clean_text, compact


# These are source-verified attachment directories/templates.  They are kept
# here, at the PDF parsing layer, instead of in the chunker so the same clean
# source is used by the structured document viewer and by retrieval.  The
# rules are deliberately bounded by an exact file name, an explicit anchor,
# and the expected number of numbered attachment entries; they never mean
# “drop everything after any occurrence of 附件”.
ATTACHMENT_RULES: dict[str, dict[str, object]] = {
    "关于证券公司证券自营业务投资范围及有关事项的规定(2020年修订).pdf": {
        "anchor": re.compile(r"^附件\s*[:：]?\s*证券公司证券自营投资品种清单"),
        "item_count": 5,
    },
    "基金管理公司特定客户资产管理子公司风险控制指标管理暂行规定.pdf": {
        "anchor": re.compile(r"^附件\s*[:：]?\s*1[.、．]\s*基金专户子公司净资本计算表"),
        "item_count": 3,
    },
    "关于加强场外衍生品业务自律管理的通知.pdf": {
        "anchor": re.compile(r"^附件\s*[:：]?\s*1[.、．]\s*场外衍生品报告内容与格式模板"),
        "item_count": 5,
        "tail_signatures": {"中国证券业协会", "2017年5月22日"},
    },
    # This source is a DOCX in the raw directory even though the same notice
    # is often circulated as a PDF.  The exact filename keeps the cleanup
    # scoped to this known template appendix.
    "关于加强场外衍生品业务自律管理的通知.docx": {
        "anchor": re.compile(r"^附件\s*[:：]?\s*1[.、．]\s*场外衍生品报告内容与格式模板"),
        "item_count": 5,
        "tail_signatures": {"中国证券业协会", "2017年5月22日"},
    },
}

CN_ITEM_RE = re.compile(r"(?<!第)([一二三四五六七八九十百]+)[、．.]\s*")
ARABIC_ITEM_RE = re.compile(r"(?<!\d)(\d+)[、．.]\s*")
NON_TERMINAL_CONTINUATION_RE = re.compile(r"[发讲直接投资机资数文规管信报]$")


def _item_count(text: str) -> int:
    value = clean_text(text)
    return len(CN_ITEM_RE.findall(value)) + len(ARABIC_ITEM_RE.findall(value))


def _is_attachment_item(text: str) -> bool:
    value = compact(text)
    return bool(
        value.startswith("附件")
        or re.match(r"^(?:[一二三四五六七八九十百]+|\d+)[、．.]", value)
    )


def _is_visual_continuation(previous: str, current: str) -> bool:
    """Recognize only a likely split line of the just-finished final item."""

    previous_value = clean_text(previous)
    current_value = clean_text(current)
    if not previous_value or not current_value or re.search(r"[。！？!?；;]$", previous_value):
        return False
    if re.match(r"^(?:第\s*[一二三四五六七八九十百\d]+\s*[条章节]|[（(][一二三四五六七八九十\d]+[）)]|附件)", current_value):
        return False
    return bool(NON_TERMINAL_CONTINUATION_RE.search(previous_value)) and bool(re.match(r"^[一-鿿A-Za-z]", current_value))


def apply_verified_pdf_content_overrides(
    path: Path,
    blocks: list[SourceBlock],
) -> tuple[list[SourceBlock], list[str]]:
    """Remove only the explicitly verified attachment directory for a PDF.

    Returns the filtered blocks and human-readable cleanup descriptions.  A
    rule stops as soon as its expected numbered entries have been consumed;
    only a narrowly recognized visual continuation or an explicitly listed
    signature/date is removed afterwards.
    """

    rule = ATTACHMENT_RULES.get(path.name)
    if not rule:
        return blocks, []
    anchor = rule["anchor"]
    expected = int(rule["item_count"])
    anchor_index = next(
        (index for index, block in enumerate(blocks) if anchor.search(clean_text(block.text))),
        None,
    )
    if anchor_index is None:
        return blocks, []

    signatures = {compact(str(value)) for value in rule.get("tail_signatures", set())}
    remove_indices: set[int] = set()
    count = 0
    last_removed = anchor_index
    previous_removed_text = ""
    for index in range(anchor_index, len(blocks)):
        text = clean_text(blocks[index].text)
        if index == anchor_index:
            remove_indices.add(index)
            count += _item_count(text)
            previous_removed_text = text
            continue

        if count < expected and _is_attachment_item(text):
            remove_indices.add(index)
            count += _item_count(text)
            previous_removed_text = text
            last_removed = index
            continue

        if count < expected and index == last_removed + 1 and _is_visual_continuation(previous_removed_text, text):
            remove_indices.add(index)
            previous_removed_text = text
            last_removed = index
            continue

        if count >= expected:
            if _is_visual_continuation(previous_removed_text, text):
                remove_indices.add(index)
                previous_removed_text = text
                last_removed = index
                continue
            if compact(text) in signatures:
                remove_indices.add(index)
                previous_removed_text = text
                last_removed = index
                continue
        break

    # Never silently remove an incomplete list: if the source shape changes,
    # leave it for human review rather than guessing where the attachment ends.
    if count < expected:
        return blocks, []
    kept = [block for index, block in enumerate(blocks) if index not in remove_indices]
    description = f"按原件核对移除明确附件目录/模板{len(remove_indices)}个block（{count}项）"
    return kept, [description]
