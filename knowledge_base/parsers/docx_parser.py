from __future__ import annotations

from pathlib import Path
import re

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

from models import ParsedDocument, SourceBlock
from utils.metadata import infer_metadata
from utils.text import clean_text, is_page_number, is_toc_field, markdown_table, strip_repeated_front_structure


def paragraph_xml_text(paragraph: Paragraph) -> str:
    """Read visible text from all WordprocessingML containers in a paragraph.

    ``Paragraph.text`` only walks direct runs and silently drops text nested in
    ``w:smartTag``, content controls and some field containers.  Regulatory
    documents use those containers for dates, tenors and numbered items, so the
    omission can change legal or financial meaning.
    """
    pieces: list[str] = []
    for element in paragraph._p.iter():
        if element.tag == qn("w:t"):
            if element.text:
                pieces.append(element.text)
        elif element.tag == qn("w:tab"):
            pieces.append("\t")
        elif element.tag in {qn("w:br"), qn("w:cr")}:
            pieces.append("\n")
    return clean_text("".join(pieces))


def table_cell_text(cell) -> str:
    values: list[str] = []
    for child in cell.iter_inner_content():
        if isinstance(child, Paragraph):
            value = paragraph_xml_text(child)
            if value:
                values.append(value)
        elif isinstance(child, Table):
            for row in child.rows:
                values.append(" | ".join(table_cell_text(nested) for nested in row.cells))
    return "\n".join(values)


def strip_word_toc(blocks: list[SourceBlock]) -> tuple[list[SourceBlock], int]:
    marker = next((index for index, block in enumerate(blocks[:20]) if re.sub(r"\s+", "", clean_text(block.text)) in {"目录", "目次"}), None)
    if marker is None:
        return blocks, 0
    # Word生成的目录通常有明确的TOC 1/TOC 2样式。优先按样式删除连续
    # 目录条目，不要依赖正文必须以“第一条”开头；业务指南、操作手册等
    # 经常采用“章 + 一、二、三”的结构，首个“第X条”可能直到附件合同
    # 才出现。旧逻辑会因此把整篇主指南误当目录删除。
    styled_end = marker + 1
    while styled_end < len(blocks) and re.match(r"^toc(?:\s*\d+)?$", clean_text(blocks[styled_end].style), re.I):
        styled_end += 1
    if styled_end > marker + 1:
        return blocks[:marker] + blocks[styled_end:], styled_end - marker
    for index in range(marker + 2, len(blocks)):
        value = re.sub(r"\s+", "", clean_text(blocks[index].text))
        earlier = {re.sub(r"\s+", "", clean_text(block.text)) for block in blocks[marker + 1:index]}
        following = [clean_text(block.text) for block in blocks[index + 1:index + 6]]
        if value in earlier and any(re.match(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条", item) for item in following):
            return blocks[:marker] + blocks[index:], index - marker
    # 部分Word目录没有重复章节标题，只有目录域生成的条目。此时从第一条
    # 正文向前保留连续的编/章/节标题，目录本身及页码条目全部丢弃。
    article_index = next(
        (index for index in range(marker + 1, len(blocks)) if re.match(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条", clean_text(blocks[index].text))),
        None,
    )
    if article_index is not None:
        start = article_index
        for index in range(article_index - 1, marker, -1):
            value = clean_text(blocks[index].text)
            if re.match(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节](?:\s+.{0,80})?$", value) and not re.search(r"\.{2,}|[…·]{2,}|\s\d{1,4}$", value):
                start = index
                continue
            break
        return blocks[:marker] + blocks[start:], start - marker
    return blocks, 0


def parse_docx(path: Path) -> ParsedDocument:
    document = Document(path)
    blocks: list[SourceBlock] = []
    sequence = 0

    def append_item(item) -> None:
        nonlocal sequence
        sequence += 1
        if isinstance(item, Paragraph):
            text = paragraph_xml_text(item)
            if not text:
                return
            style = item.style.name if item.style else ""
            blocks.append(SourceBlock(text=text, style=style, source_kind="paragraph", block_id=f"b{sequence:05d}"))
        elif isinstance(item, Table):
            # WPS/网页导出的法规有时把整篇正文包在一列嵌套表格里。
            # 逐单元格递归可保留条款段落；真正的多列表格仍转Markdown。
            if len(item.columns) == 1:
                seen_cells: set[int] = set()
                for row in item.rows:
                    cell = row.cells[0]
                    cell_key = id(cell._tc)
                    if cell_key in seen_cells:
                        continue
                    seen_cells.add(cell_key)
                    for child in cell.iter_inner_content():
                        append_item(child)
                return
            rows = [[table_cell_text(cell) for cell in row.cells] for row in item.rows]
            text = markdown_table(rows)
            if text:
                blocks.append(SourceBlock(text=text, style="Table", source_kind="table", block_id=f"b{sequence:05d}"))

    for item in document.iter_inner_content():
        append_item(item)
    warnings: list[str] = []
    blocks, removed_toc = strip_word_toc(blocks)
    if removed_toc:
        warnings.append(f"已过滤{removed_toc}个Word目录段落")
    before_noise = len(blocks)
    blocks = [block for block in blocks if not is_page_number(block.text) and not is_toc_field(block.text)]
    if len(blocks) != before_noise:
        warnings.append(f"已过滤{before_noise - len(blocks)}个Word页码或目录域段落")
    blocks, removed_front_structure = strip_repeated_front_structure(blocks)
    if removed_front_structure:
        warnings.append(f"已过滤{removed_front_structure}个Word前置目录标题")
    header_footer_text = []
    for section in document.sections:
        for container in (section.header, section.footer):
            header_footer_text.extend(clean_text(p.text) for p in container.paragraphs if clean_text(p.text))
    if header_footer_text:
        warnings.append("已识别Word页眉页脚，未混入正文：" + " | ".join(dict.fromkeys(header_footer_text))[:300])
    metadata = infer_metadata(blocks, path)
    return ParsedDocument(path, "docx", blocks, metadata, warnings)
