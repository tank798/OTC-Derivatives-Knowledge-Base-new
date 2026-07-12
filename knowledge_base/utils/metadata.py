from __future__ import annotations

import re
from pathlib import Path

from models import SourceBlock
from utils.text import clean_text

DOC_NO_PATTERNS = (
    r"(?:(?:中华人民共和国)?主席令第\s*[\d一二三四五六七八九十百]+号)",
    r"(?:(?:中国证券监督管理委员会|中国证监会|中国人民银行|国家金融监督管理总局|中国银保监会|中国银监会)令(?:\s*\u3014\d{4}\u3015)?第?\s*\d+号)",
    r"(?:[一-鿿]{1,12}[〔【\[]?\d{4}[〕】\]]?\d+号)",
    r"(?:[一-鿿]{1,12}公告[〔【\[]?\d{4}[〕】\]]?第?\d+号)",
)
DATE_RE = re.compile(r"((?:19|20)\d{2})年(\d{1,2})月(\d{1,2})日")


def normalize_date(match: re.Match[str]) -> str:
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def plausible_title(line: str) -> bool:
    line = clean_text(line)
    if not 4 <= len(line) <= 120:
        return False
    if re.match(r"^第[一二三四五六七八九十百千万零〇两\d]+[编篇部分章节]", line):
        return False
    if re.match(r"^(?:第[一二三四五六七八九十百千万零〇两\d]+条|[（(][一二三四五六七八九十\d]+[）)]|\d+[.、])", line):
        return False
    if line.endswith(("；", ";", "，", ",")):
        return False
    if line.endswith("。") and len(line) > 35:
        return False
    return any(token in line for token in ("法", "条例", "办法", "规定", "规则", "指引", "指导意见", "通知", "准则", "指南", "协议", "定义文件", "实施细则", "业务规范", "须知", "报告", "模板"))


def title_from_filename(path: Path | None) -> str:
    if path is None:
        return ""
    title = clean_text(path.stem.replace("_", " "))
    source_prefixed = re.match(r"^\d{1,2}\s+[A-Z]{2,8}\s+[^ ]+\s+(.+)$", title)
    if source_prefixed:
        title = source_prefixed.group(1)
    return title.strip(" -—_、")


def infer_metadata(blocks: list[SourceBlock], path: Path | None = None) -> dict[str, str]:
    lines: list[str] = []
    for block in blocks[:80]:
        value = clean_text(block.text)
        if not value:
            continue
        if block.source_kind == "table":
            for raw_line in value.splitlines()[:30]:
                if re.fullmatch(r"\|?(?:\s*:?-+:?\s*\|)+", raw_line.strip()):
                    continue
                cells = [clean_text(cell.replace("<br>", " ")) for cell in raw_line.strip().strip("|").split("|")]
                lines.extend(cell for cell in cells if cell)
        else:
            lines.extend(clean_text(line) for line in value.splitlines() if clean_text(line))
    joined = "\n".join(lines)
    preamble_texts: list[str] = []
    for block in blocks[:30]:
        value = clean_text(block.text)
        if re.match(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条", value):
            break
        preamble_texts.append(value)
    # 书名号内容通常是制定依据或引用法规，不能拿来当本文标题。
    # 只接受文档开头的独立标题行；无法确认时使用已人工整理的文件名。
    title = next((line for line in lines[:12] if plausible_title(line) and "《" not in line and "》" not in line), "")
    filename_title = title_from_filename(path)
    if filename_title and (not title or compact_title(title) != compact_title(filename_title)):
        title = filename_title
        title_source = "filename"
    else:
        title_source = "body" if title else ""
    document_number = ""
    for pattern in DOC_NO_PATTERNS:
        match = re.search(pattern, joined)
        if match:
            document_number = re.sub(r"\s+", "", match.group(0))
            break
    dates = [normalize_date(match) for match in DATE_RE.finditer(joined[:6000])]
    publication_date = dates[0] if dates else ""
    effective_date = ""
    effective_match = re.search(r"(?:自|于)?\s*((?:19|20)\d{2}年\d{1,2}月\d{1,2}日)\s*(?:起)?(?:施行|实施|生效)", joined[:10000])
    if effective_match:
        date_match = DATE_RE.search(effective_match.group(1))
        effective_date = normalize_date(date_match) if date_match else ""
    validity = ""
    if re.search(r"废止|失效|不再执行", joined[:8000]):
        validity = "repealed_or_historical"
    elif re.search(r"征求意见稿|修订稿|草案", title + joined[:1000]):
        validity = "draft"
    issuer = ""
    issuer_candidates = [
        line for line in lines[:30]
        if len(line) <= 60
        and not re.search(r"[。；,;()]", line)
        and re.fullmatch(r"[一-鿿、·\s]{2,60}(?:委员会|人民银行|监督管理总局|协会|交易所|国务院|常务委员会)", line)
    ]
    if issuer_candidates:
        issuer = issuer_candidates[-1]
    version_match = re.search(r"((?:19|20)\d{2}年(?:\d{1,2}月)?(?:修订|修正|版)|试行|暂行)", title)
    return {
        "document_title": title,
        "issuing_authority": issuer,
        "document_number": document_number,
        "publication_date": publication_date,
        "effective_date": effective_date,
        "validity_status": validity,
        "version": version_match.group(1) if version_match else "",
        "document_title_source": title_source,
    }


def compact_title(value: str) -> str:
    value = re.sub(r"[\s《》()（）\[\]【】_-]", "", clean_text(value))
    return re.sub(r"(?:附件|修订稿|草案)$", "", value)
