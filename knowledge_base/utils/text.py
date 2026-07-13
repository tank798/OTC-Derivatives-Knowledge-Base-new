from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

BAD_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
PAGE_NUMBER_RE = re.compile(
    r"^(?:(?:[-—–]\s*)?(?:\d\s*){1,4}(?:\s*[-—–])?|(?:\d\s*){1,4}/\s*(?:\d\s*){1,4}|"
    r"[IVXLCDM]{1,8}|第\s*\d+\s*页(?:\s*共\s*\d+\s*页)?)$",
    re.I,
)
TOC_FIELD_RE = re.compile(r"^(?:TOC\s+\\|\"?_Toc\d+\"?)", re.I)
STRUCTURE_HEADING_RE = re.compile(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*[编篇部分章节](?:\s+.{0,80})?$")
ARTICLE_HEADING_RE = re.compile(r"^第\s*[一二三四五六七八九十百千万零〇两\d ]+\s*条")
WRAPPED_DECIMAL_RE = re.compile(
    r"(?<!\d)(\d{1,3})[.．]\s*\n\s*(\d{1,3})"
    r"(?=[一-鿿A-Za-z【、%]|[.．]\d|\s+[一-鿿A-Za-z【])"
)

# PDF中的Symbol字体经常被提取到U+F000私有区。这里按Adobe Symbol
# 编码还原常见运算符和可伸缩括号组件，避免把乱码静默写入知识库。
SYMBOL_PUA_MAP = {
    0xF028: "(", 0xF029: ")", 0xF02B: "+", 0xF02D: "−", 0xF03C: "<", 0xF03D: "=",
    0xF05B: "[", 0xF05D: "]", 0xF07B: "{", 0xF07D: "}", 0xF073: "σ", 0xF0B4: "×",
    0xF0D5: "∏", 0xF0D6: "√", 0xF0D7: "·", 0xF0E5: "∑", 0xF0E6: "(",
    0xF0E7: "", 0xF0E8: "", 0xF0E9: "[", 0xF0EA: "", 0xF0EB: "", 0xF0EC: "{",
    0xF0ED: "", 0xF0EE: "", 0xF0EF: "", 0xF0F2: "∫", 0xF0F3: "∫", 0xF0F4: "",
    0xF0F5: "", 0xF0F6: ")", 0xF0F7: "", 0xF0F8: "", 0xF0F9: "]", 0xF0FA: "",
    0xF0FB: "", 0xF0FC: "}", 0xF0FD: "", 0xF0FE: "",
}


def normalize_symbol_pua(value: str) -> str:
    result: list[str] = []
    for char in value:
        codepoint = ord(char)
        if codepoint in SYMBOL_PUA_MAP:
            result.append(SYMBOL_PUA_MAP[codepoint])
        elif 0xE000 <= codepoint <= 0xF8FF:
            result.append(f"[未映射公式符号U+{codepoint:04X}]")
        else:
            result.append(char)
    return "".join(result)


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = normalize_symbol_pua(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = BAD_CONTROL_RE.sub("", value)
    value = re.sub(r"FORM(?:TEXT|CHECKBOX|DROPDOWN)", "", value, flags=re.I)
    # PDF and legacy Word layout extraction can wrap a decimal/term number at
    # the dot (``1.\n1 术语``, ``5.\n625%`` or ``7.\n2.1``).  The guarded
    # lookahead deliberately does not join ordinary ``1.\n2. 第二项`` lists.
    value = WRAPPED_DECIMAL_RE.sub(r"\1.\2", value)
    value = re.sub(r"[ \t\u3000]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", clean_text(value))


def body_char_count(value: str) -> int:
    return len(compact(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for piece in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def stable_id(*parts: str, length: int = 20) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def safe_stem(path: Path, limit: int = 80) -> str:
    stem = re.sub(r"[\\/:*?\"<>|\s]+", "_", path.stem).strip("_.")
    return (stem[:limit] or "document") + "_" + stable_id(str(path.resolve()), length=8)


def is_page_number(line: str) -> bool:
    return bool(PAGE_NUMBER_RE.fullmatch(clean_text(line)))


def is_toc_field(line: str) -> bool:
    return bool(TOC_FIELD_RE.match(clean_text(line)))


def strip_repeated_front_structure(blocks):
    """Remove a front TOC made of headings repeated before the real first article."""
    limit = min(len(blocks), 80)
    values = [compact(block.text) for block in blocks[:limit]]
    for start in range(min(20, limit)):
        raw = clean_text(blocks[start].text)
        if not STRUCTURE_HEADING_RE.match(raw):
            continue
        duplicate = next((index for index in range(start + 2, limit) if values[index] == values[start]), None)
        if duplicate is None:
            continue
        # A real TOC contains structural headings but not article bodies.  Repeated
        # chapter names also occur naturally in the body, so never delete a range
        # once an article marker has appeared inside it.
        if any(ARTICLE_HEADING_RE.match(clean_text(blocks[index].text)) for index in range(start, duplicate)):
            continue
        front_headings = sum(bool(STRUCTURE_HEADING_RE.match(clean_text(blocks[index].text))) for index in range(start, duplicate))
        following = [clean_text(block.text) for block in blocks[duplicate + 1:min(duplicate + 8, len(blocks))]]
        if front_headings >= 2 and any(ARTICLE_HEADING_RE.match(value) for value in following):
            return blocks[:start] + blocks[duplicate:], duplicate - start
    return blocks, 0


def markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [[clean_text(cell).replace("|", "\\|").replace("\n", "<br>") for cell in row] + [""] * (width - len(row)) for row in rows]
    if not any(compact(cell) for row in normalized for cell in row):
        return ""
    header = normalized[0]
    result = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    result.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
    return "\n".join(result)
