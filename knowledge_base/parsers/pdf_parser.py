from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import pdfplumber

import config
from models import ParsedDocument, SourceBlock
from utils.metadata import infer_metadata
from utils.text import clean_text, compact, is_page_number, markdown_table, strip_repeated_front_structure
from parsers.pdf_formula_overrides import apply_verified_formula_overrides

TOC_ENTRY_RE = re.compile(
    r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节条款]|"
    r"[一二三四五六七八九十百]+[、.]|\d+[、.]|附件|附录).*?(?:\.{2,}|[…·]{2,}|\s)(?:\d\s*){1,4}$"
)
TOC_GENERIC_ENTRY_RE = re.compile(r"^.+(?:\.{2,}|[…·]{2,})\s*(?:(?:\d\s*){1,4}|[IVXLCDM]+)$", re.I)
PDF_STRUCTURE_START_RE = re.compile(
    r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节条款]|"
    r"[一二三四五六七八九十百]+[、.]|[（(][一二三四五六七八九十\d]+[）)]|"
    r"\d+(?:\.\d+){1,4}\s+[一-鿿]|\d+[．.、]|"
    r"附件|附录|声\s*明|前言|目录|目次)"
)
PDF_TERMINAL_RE = re.compile(r"[。！？!?]】?$")
GUIDE_TOP_HEADING_RE = re.compile(r"^[一二三四五六七八九十百]+[、.]\s*(.+)$")
GUIDE_SUB_HEADING_RE = re.compile(r"^[（(][一二三四五六七八九十百\d]+[）)]\s*(.+)$")
GUIDE_MINOR_HEADING_RE = re.compile(r"^\d+[.．、]\s*(.+)$")
# PDF text extraction frequently cuts an action sentence after a short first
# line, e.g. ``（一）向……个人`` or ``五、……发``.  These are not headings:
# they are the lead of a numbered item whose next visual line is continuation
# text.  Keep the cue list broad enough to prevent the parser from flushing a
# false heading, while retaining genuinely short noun-style headings.
GUIDE_NORMATIVE_RE = re.compile(
    r"(?:应当|应|不得|可以|可|负责|包括|主要职责|是指|须|建议|向|通过|口头|夸大|不符合|"
    r"从事|委托|按照|根据|禁止|限制|发生|提供|承诺|要求|完成|履行|宣传|投向|开展|参与|"
    r"支付|计算|提交|知晓|遵守|用于|采取|建立|适用|转让|认购|卖方|买方|申请|新增|展期|"
    r"清算|具有|符合|满足|接受|收取|取得|披露|报告|报送|说明|识别|使用|设立|发行|保证|"
    r"确认|执行|导致|影响|属于|定义|批准|以)"
)
GUIDE_TRUNCATED_END_RE = re.compile(r"(?:专|项|发|行|讲|直|投|资|信|报|第|不|应|为|其|及|等|的|与|或|在|对|从|将|未|有|由|和)$")


def ocr_pdf_pages(path: Path) -> list[list[str]]:
    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")
    if not pdftoppm or not tesseract:
        return []
    pages: list[list[str]] = []
    with tempfile.TemporaryDirectory(prefix="regulatory_pdf_ocr_") as temp_dir:
        prefix = str(Path(temp_dir) / "page")
        rendered = subprocess.run(
            [pdftoppm, "-r", "220", "-jpeg", "-jpegopt", "quality=88", str(path), prefix],
            capture_output=True, text=True, timeout=600,
        )
        if rendered.returncode != 0:
            return []
        images = sorted(Path(temp_dir).glob("page-*.jpg"), key=lambda item: int(re.search(r"(\d+)$", item.stem).group(1)))
        for image in images:
            completed = subprocess.run(
                [tesseract, str(image), "stdout", "-l", "chi_sim+eng", "--psm", "3"],
                capture_output=True, text=True, timeout=180,
            )
            pages.append(completed.stdout.splitlines() if completed.returncode == 0 else [])
    return pages


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


def is_pdf_guide_heading(line: str) -> bool:
    value = clean_text(line)
    if compact(value) in {"说明及声明", "说明和声明"}:
        return True
    if re.fullmatch(r"第.+章(?:\s+.{1,40})?", value):
        return True
    for pattern, limit in (
        (GUIDE_TOP_HEADING_RE, 36),
        (GUIDE_SUB_HEADING_RE, 28),
        (GUIDE_MINOR_HEADING_RE, 22),
    ):
        match = pattern.fullmatch(value)
        if not match:
            continue
        remainder = clean_text(match.group(1))
        if (
            remainder
            and len(compact(remainder)) <= limit
            and not re.search(r"[。；;！？!?]", remainder)
            and not GUIDE_NORMATIVE_RE.search(remainder)
            and not (len(compact(remainder)) >= 10 and GUIDE_TRUNCATED_END_RE.search(remainder))
        ):
            return True
    return False


def join_pdf_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    current = ""
    structural = re.compile(r"^(?:第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节条款]|[（(][一二三四五六七八九十\d]+[）)]|\d+(?:\.\d+){1,4}\s+[一-鿿]|\d+[．.、])")
    article_only = re.compile(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条$")
    article_reference_fragment = re.compile(
        r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条"
        r"(?:至|、|和|及|的规定|规定)"
    )
    cleaned_lines = [
        clean_text(raw)
        for raw in lines
        if clean_text(raw) and not is_page_number(clean_text(raw))
    ]
    for line_index, line in enumerate(cleaned_lines):
        next_line = cleaned_lines[line_index + 1] if line_index + 1 < len(cleaned_lines) else ""
        if is_pdf_guide_heading(line):
            if current:
                result.append(current)
                current = ""
            result.append(line)
            continue
        if structural.match(line) or line.startswith(("附件", "附录")):
            # A numbered rule can itself wrap before a legal-looking phrase,
            # e.g. ``（三）……第（八）项、\n第六条第一款……``.  When the
            # current numbered item ends in a list separator, treat that
            # apparent article lead as continuation text instead of starting
            # a new block.  This is deliberately narrower than joining every
            # line beginning with “第”, so genuine article boundaries remain.
            if (
                current
                and re.match(r"^(?:[（(][一二三四五六七八九十百\d]+[）)]|[一二三四五六七八九十百]+[、.])", current)
                and (
                    current.rstrip().endswith(("、", ",", "，", ":", "："))
                    or (len(compact(current)) >= 20 and line.startswith("第"))
                )
                and not re.search(r"[。！？!?；;]$", current.rstrip())
            ):
                current += line
                continue
            # PDF窄行排版会把正文中的条款引用拆成独立视觉行，例如：
            # “仅适用本办法” / “第四条” / “至第八条……”。只有当前文
            # 本和下一行同时构成明显的引用语法时，才把独立“第X条”
            # 接回原句，避免把真实条款标题错误并入上一条。
            if (
                current
                and (
                    article_only.fullmatch(line)
                    or article_reference_fragment.match(line)
                )
                and not re.search(r"[。！？!?；;]$", current.rstrip())
                and re.search(r"(?:本办法|本规定|本规则|本指引|第|至|、|和|及)$", current.rstrip())
                and (
                    article_reference_fragment.match(line)
                    or re.match(r"^(?:至第|、第|和第|及第|至|、|和|及|的规定|规定)", next_line)
                )
            ):
                current += line
                continue
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


def normalize_pdf_table_cell(value: str) -> str:
    """Collapse visual line wrapping inside one extracted PDF table cell.

    pdfplumber keeps the line breaks produced by a narrow column.  Those
    breaks are page-layout artifacts, not semantic paragraphs, and otherwise
    become ``<br>`` inside Markdown (for example ``债<br>券``).  Chinese text
    is joined directly; adjacent Latin letters or digits retain one space.
    """
    lines = [clean_text(line) for line in clean_text(value).splitlines() if clean_text(line)]
    if not lines:
        return ""
    result = lines[0]
    for line in lines[1:]:
        separator = " " if re.search(r"[A-Za-z0-9]$", result) and re.match(r"^[A-Za-z0-9]", line) else ""
        result += separator + line
    return clean_text(result)


def normalize_semantic_table(rows: list[list[str | None]]) -> list[list[str]]:
    """Return a real multi-column table without all-empty rows or columns.

    PDF layout engines often draw a three-column box around a prose note.  In
    those boxes only the middle column contains text; treating them as tables
    creates artificial columns and duplicates prose.  A semantic table must
    retain at least two columns containing actual values after empty-column
    removal.
    """
    cleaned = [[normalize_pdf_table_cell(cell or "") for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(compact(cell) for cell in row)]
    if len(cleaned) < 2:
        return []
    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    active_columns = [index for index in range(width) if any(compact(row[index]) for row in padded)]
    if len(active_columns) < 2:
        return []
    # Preserve the source grid width. Removing all-empty columns breaks merged
    # multi-level headers and makes cross-page continuations appear to have a
    # different schema. Empty columns remain explicit and are never invented
    # later by the HTML renderer.
    result = padded
    if sum(bool(compact(cell)) for row in result for cell in row) < 4:
        return []
    return result


def table_header_count(rows: list[list[str]]) -> int:
    if len(rows) < 3:
        return 1
    first, second = rows[0], rows[1]
    first_nonempty = sum(bool(compact(cell)) for cell in first)
    second_nonempty = sum(bool(compact(cell)) for cell in second)
    if first_nonempty and second_nonempty and (
        any(not compact(cell) for cell in first)
        or any(not compact(cell) for cell in second)
    ):
        return 2
    return 1


def pdf_table_data(
    rows: list[list[str]],
    page_no: int,
    table_index: int,
    bbox: tuple[float, float, float, float],
    page_height: float,
) -> dict:
    width = max((len(row) for row in rows), default=0)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header_count = min(table_header_count(normalized), len(normalized))
    headers = normalized[:header_count]
    body_rows = normalized[header_count:]
    cells = [
        {
            "row": row_index,
            "column": column_index,
            "text": cell,
            "rowspan": 1,
            "colspan": 1,
        }
        for row_index, row in enumerate(normalized)
        for column_index, cell in enumerate(row)
    ]
    warnings = ["PDF文本层未提供可靠合并单元格语义，保留原始网格且未伪造rowspan/colspan"]
    return {
        "table_id": f"table_p{page_no}_{table_index}",
        "caption": "",
        "headers": headers,
        "rows": body_rows,
        "cells": cells,
        "column_count": width,
        "source_page_start": page_no,
        "source_page_end": page_no,
        "source_fragments": [{"page": page_no, "table_index": table_index}],
        "bbox": [round(float(value), 3) for value in bbox],
        "page_height": round(float(page_height), 3),
        "parsing_warnings": warnings,
    }


def table_grid(table_data: dict) -> list[list[str]]:
    return list(table_data.get("headers", [])) + list(table_data.get("rows", []))


def refresh_table_block_text(block: SourceBlock) -> None:
    block.text = markdown_table(table_grid(block.table_data))
    block.source_page_end = int(block.table_data.get("source_page_end", block.page))
    block.parsing_warnings = list(table_data_warning for table_data_warning in block.table_data.get("parsing_warnings", []))


def stitch_cross_page_tables(blocks: list[SourceBlock]) -> tuple[list[SourceBlock], int]:
    """Join only geometrically credible page-bottom/page-top continuations."""

    result: list[SourceBlock] = []
    stitched = 0
    for block in blocks:
        if result and block.source_kind == "table" and result[-1].source_kind == "table":
            previous = result[-1]
            left = previous.table_data
            right = block.table_data
            left_bbox = left.get("bbox", [])
            right_bbox = right.get("bbox", [])
            left_height = float(left.get("page_height", 0) or 0)
            right_height = float(right.get("page_height", 0) or 0)
            adjacent = block.page == int(left.get("source_page_end", previous.page)) + 1
            same_width = int(left.get("column_count", 0)) == int(right.get("column_count", -1))
            boundary_geometry = (
                len(left_bbox) == 4 and len(right_bbox) == 4
                and left_height > 0 and right_height > 0
                and float(left_bbox[3]) >= left_height * 0.72
                and float(right_bbox[1]) <= right_height * 0.28
            )
            if adjacent and same_width and boundary_geometry:
                left_headers = list(left.get("headers", []))
                right_headers = list(right.get("headers", []))
                left_header_key = [[compact(cell) for cell in row] for row in left_headers]
                right_header_key = [[compact(cell) for cell in row] for row in right_headers]
                continuation_rows = list(right.get("rows", []))
                if right_header_key != left_header_key[:len(right_header_key)]:
                    continuation_rows = right_headers + continuation_rows
                left["rows"] = list(left.get("rows", [])) + continuation_rows
                left["source_page_end"] = right.get("source_page_end", block.page)
                left["source_fragments"] = list(left.get("source_fragments", [])) + list(right.get("source_fragments", []))
                left["parsing_warnings"] = list(dict.fromkeys(
                    list(left.get("parsing_warnings", []))
                    + list(right.get("parsing_warnings", []))
                    + [f"已按页底/页顶几何边界拼接第{previous.page}-{block.page}页表格片段"]
                ))
                refresh_table_block_text(previous)
                stitched += 1
                continue
        result.append(block)
    return result, stitched


def split_semantic_table_content(rows: list[list[str]]) -> list[tuple[str, object]]:
    """Separate prose notes from genuine multi-column rows in one PDF box.

    Some PDFs put a long explanatory note, a displayed equation and more
    prose inside one bordered area. pdfplumber reports the whole area as one
    table. Keeping the single-cell prose as table rows creates extremely wide
    Markdown and oversized chunks, so retain only the multi-column portion as
    a table and emit prose portions as ordinary text in their original order.
    """
    segments: list[tuple[str, object]] = []
    table_rows: list[list[str]] = []
    prose_lines: list[str] = []
    mode = "table"

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            segments.append(("table", table_rows))
            table_rows = []

    def flush_prose() -> None:
        nonlocal prose_lines
        if prose_lines:
            physical_lines = [line for value in prose_lines for line in value.splitlines()]
            paragraphs = join_pdf_lines(physical_lines)
            segments.append(("text", "\n".join(paragraphs)))
            prose_lines = []

    for row in rows:
        values = [cell for cell in row if compact(cell)]
        single_value = values[0] if len(values) == 1 else ""
        starts_note = bool(re.match(r"^(?:注|说明|备注)\s*[:：]", single_value))
        looks_like_prose = (
            len(values) == 1
            and len(compact(single_value)) >= 24
            and bool(re.search(r"[,;:，。；：！？]", single_value))
        )

        if mode == "prose":
            if len(values) >= 2:
                flush_prose()
                mode = "table"
                table_rows.append(row)
            else:
                prose_lines.append(single_value)
            continue

        if starts_note or looks_like_prose:
            flush_table()
            mode = "prose"
            prose_lines.append(single_value)
        else:
            table_rows.append(row)

    flush_table() if mode == "table" else flush_prose()
    return [(kind, value) for kind, value in segments if value]


def merge_cross_page_paragraphs(blocks: list[SourceBlock]) -> tuple[list[SourceBlock], int]:
    """Join artificial PDF page breaks that split one paragraph or word.

    A continuation is merged only across adjacent pages, only for paragraph
    blocks, and never when the next page begins with a legal/list structure.
    Sentence-ending punctuation is a safe paragraph boundary.  Commas,
    semicolons and colons may legitimately occur at page breaks and therefore
    do not block a merge when the next line is plain continuation text.
    """
    if not blocks:
        return blocks, 0
    result: list[SourceBlock] = []
    merged = 0
    for block in blocks:
        if result:
            previous = result[-1]
            adjacent_pages = previous.page > 0 and block.page == previous.page + 1
            plain_paragraphs = previous.source_kind == block.source_kind == "paragraph"
            continuation = not PDF_TERMINAL_RE.search(previous.text.rstrip()) and not PDF_STRUCTURE_START_RE.match(block.text.lstrip())
            if adjacent_pages and plain_paragraphs and continuation:
                separator = " " if re.search(r"[A-Za-z0-9]$", previous.text) and re.match(r"^[A-Za-z0-9]", block.text) else ""
                previous.text = clean_text(previous.text + separator + block.text)
                merged += 1
                continue
        result.append(block)
    return result, merged


def parse_pdf(path: Path) -> ParsedDocument:
    warnings: list[str] = []
    pages_lines: list[list[str]] = []
    page_tables: list[list[tuple[tuple[float, float, float, float], list[tuple[str, object]]]]] = []
    page_line_records: list[list[dict]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            pages_lines.append(text.splitlines())
            try:
                records = page.extract_text_lines(x_tolerance=2, y_tolerance=3, return_chars=False)
                page_line_records.append(records)
                semantic_tables = []
                for table in page.find_tables():
                    rows = normalize_semantic_table(table.extract())
                    if rows:
                        semantic_tables.append((table.bbox, split_semantic_table_content(rows), float(page.height)))
                page_tables.append(semantic_tables)
            except Exception:
                page_tables.append([])
                page_line_records.append([])
    extracted_chars = len(compact("\n".join(line for lines in pages_lines for line in lines)))
    sparse_threshold = max(120, len(pages_lines) * 40)
    if extracted_chars < sparse_threshold:
        official_cache = config.OFFICIAL_TEXT_CACHE_DIR / f"{path.stem}.html"
        if official_cache.exists():
            from parsers.text_parser import parse_official_html_cache
            return parse_official_html_cache(official_cache, path)
        ocr_pages = ocr_pdf_pages(path)
        ocr_chars = len(compact("\n".join(line for lines in ocr_pages for line in lines)))
        if ocr_chars > extracted_chars * 3 and ocr_chars >= sparse_threshold:
            pages_lines = ocr_pages
            page_tables = [[] for _ in pages_lines]
            page_line_records = [[] for _ in pages_lines]
            warnings.append(f"原PDF文本层过少（{extracted_chars}字符），已使用本机OCR提取{ocr_chars}字符")
        else:
            return ParsedDocument(path, "pdf", [], {}, [f"PDF共{len(pages_lines)}页但仅提取{extracted_chars}字符，OCR未获得可靠正文，需要人工复核"], "needs_ocr")
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
        tables = sorted(page_tables[page_no - 1], key=lambda item: item[0][1])
        records = page_line_records[page_no - 1]
        if tables and records:
            cursor = float("-inf")
            segments: list[tuple[float, str, object]] = []
            for table_index, (bbox, content_segments, page_height) in enumerate(tables, start=1):
                top, bottom = bbox[1], bbox[3]
                segment_lines = [
                    record["text"] for record in records
                    if cursor <= (record["top"] + record["bottom"]) / 2 < top
                ]
                segments.append((cursor, "text", segment_lines))
                for content_index, (content_kind, content) in enumerate(content_segments):
                    segments.append((top + content_index / 1000, content_kind, (table_index, content, bbox, page_height)))
                cursor = max(cursor, bottom)
            segments.append((cursor, "text", [
                record["text"] for record in records
                if (record["top"] + record["bottom"]) / 2 >= cursor
            ]))
        else:
            segments = [(0, "text", lines)]

        for _, kind, payload in segments:
            if kind == "table":
                table_index, rows, bbox, page_height = payload
                value = markdown_table(rows)
                if value:
                    sequence += 1
                    table_data = pdf_table_data(rows, page_no, table_index, bbox, page_height)
                    blocks.append(SourceBlock(
                        value,
                        style="Table",
                        source_kind="table",
                        page=page_no,
                        source_page_end=page_no,
                        block_id=f"b{sequence:05d}",
                        table_data=table_data,
                        parsing_warnings=list(table_data["parsing_warnings"]),
                    ))
                    warnings.append(f"第{page_no}页第{table_index}个多列表格按原行列转为Markdown")
                continue
            if isinstance(payload, tuple):
                table_index, value, _, _ = payload
                if value:
                    sequence += 1
                    blocks.append(SourceBlock(value, page=page_no, block_id=f"b{sequence:05d}"))
                    warnings.append(f"第{page_no}页第{table_index}个表格中的说明文本已与行列分离")
                continue
            margin_filtered = [line for line in payload if compact(line) not in repeated and not is_page_number(line)]
            filtered, removed_toc = remove_toc_entries(margin_filtered)
            if removed_toc:
                warnings.append(f"第{page_no}页过滤{removed_toc}行目录条目")
            for paragraph in join_pdf_lines(filtered):
                sequence += 1
                blocks.append(SourceBlock(paragraph, page=page_no, block_id=f"b{sequence:05d}"))

    blocks, stitched_tables = stitch_cross_page_tables(blocks)
    if stitched_tables:
        warnings.append(f"已按几何边界拼接{stitched_tables}组PDF跨页表格")
    blocks, merged_page_breaks = merge_cross_page_paragraphs(blocks)
    if merged_page_breaks:
        warnings.append(f"已合并{merged_page_breaks}处PDF跨页句子或词语断行")
    # Apply formula corrections only after cross-page paragraphs have been
    # joined.  Otherwise a formula that starts at the bottom of one page can
    # be attached to a discarded continuation block and lose its metadata.
    verified_formula_count = apply_verified_formula_overrides(path, blocks)
    if verified_formula_count:
        warnings.append(f"按原PDF二维排版核对并线性化{verified_formula_count}处公式")
    blocks, removed_front_structure = strip_repeated_front_structure(blocks)
    if removed_front_structure:
        warnings.append(f"已过滤{removed_front_structure}个PDF前置目录标题")
    metadata = infer_metadata(blocks, path)
    return ParsedDocument(path, "pdf", blocks, metadata, warnings)
