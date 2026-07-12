from __future__ import annotations

from pathlib import Path
import re

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from models import ParsedDocument, SourceBlock
from utils.metadata import infer_metadata
from utils.text import clean_text, markdown_table


def strip_word_toc(blocks: list[SourceBlock]) -> tuple[list[SourceBlock], int]:
    marker = next((index for index, block in enumerate(blocks[:20]) if re.sub(r"\s+", "", clean_text(block.text)) in {"目录", "目次"}), None)
    if marker is None:
        return blocks, 0
    for index in range(marker + 2, len(blocks)):
        value = re.sub(r"\s+", "", clean_text(blocks[index].text))
        earlier = {re.sub(r"\s+", "", clean_text(block.text)) for block in blocks[marker + 1:index]}
        following = [clean_text(block.text) for block in blocks[index + 1:index + 6]]
        if value in earlier and any(re.match(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条", item) for item in following):
            return blocks[:marker] + blocks[index:], index - marker
    return blocks, 0


def parse_docx(path: Path) -> ParsedDocument:
    document = Document(path)
    blocks: list[SourceBlock] = []
    sequence = 0
    for item in document.iter_inner_content():
        sequence += 1
        if isinstance(item, Paragraph):
            text = clean_text(item.text)
            if not text:
                continue
            style = item.style.name if item.style else ""
            blocks.append(SourceBlock(text=text, style=style, source_kind="paragraph", block_id=f"b{sequence:05d}"))
        elif isinstance(item, Table):
            rows = [[cell.text for cell in row.cells] for row in item.rows]
            text = markdown_table(rows)
            if text:
                blocks.append(SourceBlock(text=text, style="Table", source_kind="table", block_id=f"b{sequence:05d}"))
    warnings: list[str] = []
    blocks, removed_toc = strip_word_toc(blocks)
    if removed_toc:
        warnings.append(f"已过滤{removed_toc}个Word目录段落")
    header_footer_text = []
    for section in document.sections:
        for container in (section.header, section.footer):
            header_footer_text.extend(clean_text(p.text) for p in container.paragraphs if clean_text(p.text))
    if header_footer_text:
        warnings.append("已识别Word页眉页脚，未混入正文：" + " | ".join(dict.fromkeys(header_footer_text))[:300])
    metadata = infer_metadata(blocks, path)
    return ParsedDocument(path, "docx", blocks, metadata, warnings)
