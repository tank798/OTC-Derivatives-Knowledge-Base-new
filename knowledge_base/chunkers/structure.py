from __future__ import annotations

import re

from models import Node, ParsedDocument, SourceBlock
from utils.text import clean_text

CN_NUM = r"[一二三四五六七八九十百千万零〇两\d]+"
DOTTED_TERM_RE = re.compile(r"^(\d+[.．]\d+(?:[.．]\d+)*)(?:\s+|(?=[一-鿿A-Za-z【]))(.+)$")
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("part", re.compile(rf"^(第\s*{CN_NUM}\s*[编篇部分])(?:\s+|$)(.*)$")),
    ("chapter", re.compile(rf"^(第\s*{CN_NUM}\s*章)(?:\s+|$)(.*)$")),
    ("section", re.compile(rf"^(第\s*{CN_NUM}\s*节)(?:\s+|$)(.*)$")),
    ("article", re.compile(rf"^(第\s*{CN_NUM}\s*条)(?:\s+|$)?(.*)$")),
    ("paragraph", re.compile(rf"^(第\s*{CN_NUM}\s*款)(?:\s+|$)?(.*)$")),
    ("item", re.compile(r"^([（(][一二三四五六七八九十百\d]+[）)])\s*(.*)$")),
    ("subitem", re.compile(r"^((?:\d+|[一二三四五六七八九十]+)[.．、])\s*(.*)$")),
    ("subitem", re.compile(r"^([①-⑳])\s*(.*)$")),
    ("attachment", re.compile(r"^((?:附件|附录)(?:\s*\d+)?(?:[::：]\s*)?.{0,80})$")),
]
RANK = {
    "document": 0, "part": 1, "attachment": 1,
    "chapter": 2,
    "section": 3, "guide_heading": 3,
    "article": 4, "guide_subheading": 4,
    "paragraph": 5, "guide_minor_heading": 5,
    "item": 6, "subitem": 7, "table": 8, "text": 8,
}
STANDALONE_PART_RE = re.compile(
    r"^(?:补充协议|特别条款|专用条款|[^。；;：:]{2,80}(?:实施细则|管理办法|业务指引|备案指引|补充协议|特别条款|专用条款|操作细则|交易规则))$"
)
EMBEDDED_PART_RE = re.compile(r"^(.{2,120}?(?:补充协议|特别条款|专用条款))((?:本|为|鉴于).+)$")
GUIDE_TOP_RE = re.compile(r"^([一二三四五六七八九十百]+[、.])\s*(.+)$")
GUIDE_SUB_RE = re.compile(r"^([（(][一二三四五六七八九十百]+[）)])\s*(.+)$")
GUIDE_MINOR_RE = re.compile(r"^(\d+[.．、])\s*(.+)$")
GUIDE_NORMATIVE_RE = re.compile(
    r"(?:应当|应|不得|可以|可|负责|包括|主要职责|是指|须|建议|向|通过|口头|夸大|不符合|"
    r"从事|委托|按照|根据|禁止|限制|发生|提供|承诺|要求|完成|履行|宣传|投向|开展|参与|"
    r"支付|计算|提交|知晓|遵守|用于|采取|建立|适用|转让|认购|卖方|买方|申请|新增|展期|"
    r"清算|具有|符合|满足|接受|收取|取得|披露|报告|报送|说明|识别|使用|设立|发行|保证|"
    r"确认|执行|导致|影响|属于|定义|批准|以)"
)


def normalize_marker(value: str) -> str:
    return re.sub(r"\s+", "", value)


def is_standalone_part_heading(value: str) -> bool:
    return bool(STANDALONE_PART_RE.fullmatch(clean_text(value)))


def is_official_footnote_heading(value: str) -> bool:
    return bool(re.match(r"^修订注\d+[：:]", clean_text(value)))


def is_embedded_part_heading(value: str) -> bool:
    return bool(EMBEDDED_PART_RE.fullmatch(clean_text(value)))


def classify_block(block: SourceBlock, *, allow_standalone_part: bool = True) -> tuple[str, str, str]:
    text = clean_text(block.text)
    if block.source_kind == "table":
        return "table", "", text
    if re.search(r"\.{4,}|[…·]{6,}", text):
        return "text", "", text
    if block.source_kind == "sheet":
        return "part", text, ""
    # A verified formula block may contain an article lead followed by several
    # newline-separated equations.  Match the article lead across newlines so
    # the formulas retain the article's structural context and numbering.
    article_lead = re.match(rf"^(第\s*{CN_NUM}\s*条)(?:\s+|$)?([\s\S]*)$", text)
    if article_lead:
        return "article", normalize_marker(article_lead.group(1)), clean_text(article_lead.group(2))
    # Definition documents use decimal term numbers such as ``1.1`` and
    # ``2.3.1``.  This must run before the generic ``1.`` list matcher;
    # otherwise ``1.1 权益类衍生品交易`` is parsed as marker ``1.`` plus
    # body ``1 ...`` and later rendered as the artificial line break ``1.\n1``.
    dotted_term = DOTTED_TERM_RE.fullmatch(text)
    if dotted_term:
        return "subitem", dotted_term.group(1).replace("．", "."), clean_text(dotted_term.group(2))
    # A front-matter declaration has substantive provenance/use information,
    # but it is not part of the first legal article.  Treat it as its own
    # structural part so the chunker keeps it with its following declaration
    # text and breaks before Article 1.
    if normalize_marker(text) in {"声明", "前言", "说明及声明", "说明和声明"}:
        return "part", normalize_marker(text), ""
    embedded_part = EMBEDDED_PART_RE.fullmatch(text)
    if embedded_part:
        return "part", clean_text(embedded_part.group(1)), clean_text(embedded_part.group(2))
    if allow_standalone_part and is_standalone_part_heading(text):
        return "part", text, ""
    for kind, pattern, limit in (
        ("guide_heading", GUIDE_TOP_RE, 36),
        ("guide_subheading", GUIDE_SUB_RE, 30),
        ("guide_minor_heading", GUIDE_MINOR_RE, 24),
    ):
        match = pattern.fullmatch(text)
        if not match:
            continue
        remainder = clean_text(match.group(2))
        if (
            remainder
            and len(normalize_marker(remainder)) <= limit
            and not re.search(r"[。；;！？!?]", remainder)
            and not GUIDE_NORMATIVE_RE.search(remainder)
        ):
            return kind, clean_text(match.group(1) + remainder), ""
    footnote = re.match(r"^(修订注\d+)[：:]\s*(.*)$", text)
    if footnote:
        return "attachment", footnote.group(1), clean_text(footnote.group(2))
    for kind, pattern in PATTERNS:
        match = pattern.match(text)
        if match:
            if kind == "attachment":
                return kind, match.group(1), ""
            marker = normalize_marker(match.group(1))
            remainder = clean_text(match.group(2))
            if kind in {"part", "chapter", "section"}:
                return kind, clean_text(marker + (" " + remainder if remainder else "")), ""
            return kind, marker, remainder
    style = block.style.lower()
    if "heading 1" in style or "标题 1" in style:
        return "part", text, ""
    if "heading 2" in style or "标题 2" in style:
        return "chapter", text, ""
    if "heading 3" in style or "标题 3" in style:
        return "section", text, ""
    return "text", "", text


def build_tree(document: ParsedDocument) -> Node:
    root = Node("document", title=document.metadata.get("document_title", ""))
    stack: list[Node] = [root]
    standalone_part_count = sum(is_standalone_part_heading(block.text) for block in document.blocks)
    for block in document.blocks:
        kind, title, own_text = classify_block(block, allow_standalone_part=standalone_part_count >= 2)
        # Front matter ends when the operative articles begin.  Without this
        # explicit reset, the normal hierarchy would make Article 1 a child of
        # the preceding ``声明/前言`` part and merge both into one chunk.
        if kind == "article" and any(item.kind == "part" and item.title in {"声明", "前言"} for item in stack):
            while len(stack) > 1:
                stack.pop()
        if kind == "text":
            node = Node(kind, own_text=own_text, block_ids=[block.block_id])
            stack[-1].add_child(node)
            continue
        if kind == "article":
            current_article = next((item for item in reversed(stack) if item.kind == "article"), None)
            current_ordinal = article_ordinal(current_article.title) if current_article else None
            new_ordinal = article_ordinal(title)
            if current_article and current_ordinal is not None and new_ordinal is not None and new_ordinal < current_ordinal:
                current_article.add_child(Node("text", own_text=clean_text(title + (" " + own_text if own_text else "")), block_ids=[block.block_id]))
                continue
        node = Node(kind, title=title, own_text=own_text, block_ids=[block.block_id])
        rank = RANK[kind]
        while len(stack) > 1 and RANK[stack[-1].kind] >= rank:
            stack.pop()
        stack[-1].add_child(node)
        if kind not in {"table"}:
            stack.append(node)
    return root


def hierarchy_for(node: Node) -> dict[str, str]:
    result = {"part_title": "", "chapter_title": "", "section_title": "", "article_title": "", "paragraph_title": "", "attachment_name": ""}
    current: Node | None = node
    while current:
        if current.kind == "part" and not result["part_title"]:
            result["part_title"] = current.title
        elif current.kind == "guide_heading" and not result["section_title"]:
            result["section_title"] = current.title
        elif current.kind in {"guide_subheading", "guide_minor_heading"} and not result["paragraph_title"]:
            result["paragraph_title"] = current.title
        elif current.kind == "chapter" and not result["chapter_title"]:
            result["chapter_title"] = current.title
        elif current.kind == "section" and not result["section_title"]:
            result["section_title"] = current.title
        elif current.kind == "article" and not result["article_title"]:
            result["article_title"] = current.title
        elif current.kind in {"paragraph", "item", "subitem"} and not result["paragraph_title"]:
            result["paragraph_title"] = current.title
        elif current.kind == "attachment" and not result["attachment_name"]:
            result["attachment_name"] = current.title
        current = current.parent
    return result


def render_node(node: Node) -> str:
    if node.kind in {"paragraph", "item", "subitem"} and node.title and node.own_text:
        separator = " " if node.kind == "paragraph" or re.fullmatch(r"\d+(?:\.\d+)+", node.title) else ""
        parts = [f"{node.title}{separator}{node.own_text}"]
    else:
        parts = [node.title, node.own_text]
    parts.extend(render_node(child) for child in node.children)
    return "\n".join(part for part in parts if part).strip()


def descendant_articles(node: Node) -> list[str]:
    result: list[str] = []
    if node.kind == "article" and node.title:
        result.append(node.title)
    for child in node.children:
        result.extend(descendant_articles(child))
    return result


def article_ordinal(value: str) -> int | None:
    match = re.fullmatch(r"第([一二三四五六七八九十百千零〇两\d]+)条", value)
    if not match:
        return None
    raw = match.group(1)
    if raw.isdigit():
        return int(raw)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = number = 0
    for char in raw:
        if char in digits:
            number = digits[char]
        elif char in units:
            total += (number or 1) * units[char]
            number = 0
        else:
            return None
    return total + number


def monotonic_articles(node: Node) -> list[str]:
    result: list[str] = []
    last: int | None = None
    for value in descendant_articles(node):
        ordinal = article_ordinal(value)
        if ordinal is None or last is None or ordinal >= last:
            result.append(value)
            if ordinal is not None:
                last = ordinal
    return result


def containing_article(node: Node) -> str:
    current: Node | None = node
    while current:
        if current.kind == "article":
            return current.title
        current = current.parent
    return ""


def descendant_block_ids(node: Node) -> list[str]:
    result = list(node.block_ids)
    for child in node.children:
        result.extend(descendant_block_ids(child))
    return result
