from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import pdfplumber

from models import ParsedDocument, SourceBlock
from utils.metadata import infer_metadata
from utils.text import clean_text, compact, is_page_number, markdown_table

TOC_ENTRY_RE = re.compile(
    r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节条款]|"
    r"[一二三四五六七八九十百]+[、.]|\d+[、.]|附件|附录).*?(?:\.{2,}|[…·]{2,}|\s)(?:\d\s*){1,4}$"
)
TOC_GENERIC_ENTRY_RE = re.compile(r"^.+(?:\.{2,}|[…·]{2,})\s*(?:(?:\d\s*){1,4}|[IVXLCDM]+)$", re.I)


def repeated_margin_lines(pages: list[list[str]]) -> set[str]:
    candidates: Counter[str] = Counter()
    for lines in pages:
        visible = [clean_text(line) for line in lines if clean_text(line)]
        for line in visible[:2] + visible[-2:]:
            key = compact(line)
            if 2 <= len(key) <= 80 and not is_page_number(line):
                candidates[key] += 1
    threshold = 2 if len(pages) <= 5 else max(3, (len(pages) + 2) // 3)
    return {line for line, count in candidates.items() if count >= threshold}


def remove_toc_entries(lines: list[str]) -> tuple[list[str], int]:
    cleaned = [clean_text(line) for line in lines if clean_text(line)]
    toc_like = sum(bool(TOC_ENTRY_RE.match(line)) for line in cleaned)
    toc_headings = {"目录", "目次", "目录CONTENTS", "CONTENTS"}
    has_toc_heading = any(compact(line) in toc_headings for line in cleaned)
    toc_page = toc_like >= 3 or has_toc_heading
    if not toc_page:
        return cleaned, 0
    result = [
        line for line in cleaned
        if compact(line) not in toc_headings
        and not TOC_ENTRY_RE.match(line)
        and not (toc_page and TOC_GENERIC_ENTRY_RE.match(line))
    ]
    return result, len(cleaned) - len(result)


def join_pdf_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    current = ""
    structural = re.compile(r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节条款]|[（(][一二三四五六七八九十\d]+[）)]|\d+(?:\.\d+){0,4}\s+[一-鿿]|\d+[．.、])")
    for raw in lines:
        line = clean_text(raw)
        if not line or is_page_number(line):
            continue
        if structural.match(line) or line.startswith(("附件", "附录")):
            if current:
                result.append(current)
            current = line
            continue
        if not current:
            current = line
        else:
            separator = " " if re.search(r"[A-Za-z0-9]$", current) and re.match(r"^[A-Za-z0-9]", line) else ""
            current += separator + line
    if current:
        result.append(current)
    return result


def parse_pdf(path: Path) -> ParsedDocument:
    warnings: list[str] = []
    pages_lines: list[list[str]] = []
    page_tables: list[list[list[list[str | None]]]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            pages_lines.append(text.splitlines())
            try:
                page_tables.append(page.extract_tables() or [])
            except Exception:
                page_tables.append([])
    private_use_count = sum(0xE000 <= ord(char) <= 0xF8FF for lines in pages_lines for line in lines for char in line)
    if private_use_count:
        warnings.append(f"按Adobe Symbol编码规范化{private_use_count}个PDF公式字符")
    if not any(compact("\n".join(lines)) for lines in pages_lines):
        return ParsedDocument(path, "pdf", [], {}, ["疑似扫描型PDF，未获得可靠文本，需要OCR或人工复核"], "needs_ocr")
    repeated = repeated_margin_lines(pages_lines)
    if repeated:
        warnings.append(f"已去除{len(repeated)}类跨页重复页眉或页脚")
    blocks: list[SourceBlock] = []
    sequence = 0
    for page_no, lines in enumerate(pages_lines, start=1):
        margin_filtered = [line for line in lines if compact(line) not in repeated and not is_page_number(line)]
        filtered, removed_toc = remove_toc_entries(margin_filtered)
        if removed_toc:
            warnings.append(f"第{page_no}页过滤{removed_toc}行目录条目")
        for paragraph in join_pdf_lines(filtered):
            sequence += 1
            blocks.append(SourceBlock(paragraph, page=page_no, block_id=f"b{sequence:05d}"))
        # 表格文字通常已在页面文本中；只在页面文本未覆盖主要单元格时追加结构化表格。
        page_compact = compact("\n".join(filtered))
        for table_index, table in enumerate(page_tables[page_no - 1], start=1):
            rows = [[clean_text(cell or "") for cell in row] for row in table]
            cells = [compact(cell) for row in rows for cell in row if compact(cell)]
            coverage = sum(cell in page_compact for cell in cells) / max(len(cells), 1)
            if cells and coverage < 0.65:
                sequence += 1
                blocks.append(SourceBlock("表格\n" + markdown_table(rows), style="Table", source_kind="table", page=page_no, block_id=f"b{sequence:05d}"))
                warnings.append(f"第{page_no}页第{table_index}个表格以Markdown补入")
    metadata = infer_metadata(blocks, path)
    return ParsedDocument(path, "pdf", blocks, metadata, warnings)
