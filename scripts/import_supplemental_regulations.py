from __future__ import annotations

import argparse
from datetime import date
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKDOWN = ROOT / "更新的法规" / "1" / "场外衍生品法规知识库_0722_vf.md"
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "监管文件"
DEFAULT_CATALOG = ROOT / "data" / "metadata" / "regulations.jsonl"
DEFAULT_AUDIT = ROOT / "更新的法规" / "新增法规导入审计_20260724.json"

SUPPORTED_SUFFIXES = {".doc", ".docx", ".pdf"}
PRESERVED_BUILD_FIELDS = {
    "document_id",
    "chunk_count",
    "character_count",
    "clean_text_hash",
    "structured_schema_version",
    "cleaning_rule_version",
    "parser_version",
    "chunker_version",
    "processed_status",
}
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")
VERSION_RE = re.compile(r"((?:19|20)\d{2}年(?:\d{1,2}月)?(?:修订|修正|版)|试行|暂行)")

MISSING_ROWS = {
    4: {
        "title": "证券市场程序化交易管理规定（试行）",
        "publication_date": "2024-05-11",
        "issuing_authority": "中国证券监督管理委员会",
        "validity_status": "现行有效",
        "official_url": "https://www.csrc.gov.cn/csrc/c101954/c7480579/content.shtml",
        "section": "一、场外业务配套及交易行为合规",
        "metadata_note": "原Markdown序号4为空；依据中国证监会第8号公告官网补录。",
    },
    6: {
        "title": "关于上市公司内幕信息知情人登记管理制度的规定",
        "publication_date": "2021-02-03",
        "issuing_authority": "中国证券监督管理委员会",
        "validity_status": "现行有效",
        "official_url": "https://www.csrc.gov.cn/csrc/c101875/c465cd93ff1254baab931de0cd73a9049/content.shtml",
        "section": "一、场外业务配套及交易行为合规",
        "metadata_note": "原Markdown序号6为空；依据中国证监会第5号公告官网补录。",
    },
}

EXCLUDED_ATTACHMENTS = {
    "可投资国家或者地区.docx": {
        "parent_title": "保险资金境外投资管理暂行办法实施细则",
        "reason": "内容已作为该实施细则附件1完整内嵌，排除独立入库以避免重复召回。",
    },
    "期货期权交易所.docx": {
        "parent_title": "保险资金境外投资管理暂行办法实施细则",
        "reason": "内容已作为该实施细则附件2完整内嵌，排除独立入库以避免重复召回。",
    },
}

OFFICIAL_URL_OVERRIDES = {
    62: {
        "official_url": "https://www.nfra.gov.cn/chinese/subject/subject/nianbao2011/2011zwzz.pdf",
        "metadata_note": "补充清单原链接为百度百科；改用国家金融监督管理总局官网《中国银行业监督管理委员会2011年报》中对银监发〔2011〕70号的官方列示。",
    },
    82: {
        "official_url": "https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/201610/t20161013_2434596.htm",
        "metadata_note": "补充清单原链接为第三方网站；改用财政部官网正文。",
    },
    87: {
        "official_url": "https://mzt.ln.gov.cn/mzt/hdzl/cssyzl/2024032810280039799/index.shtml",
        "metadata_note": "补充清单原链接为第三方网站；改用政府民政部门官网转载正文。",
    },
    90: {
        "official_url": "https://flk.npc.gov.cn/detail?fileId=&id=2c909fdd678bf17901678bf608a7022b&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%85%AC%E7%9B%8A%E4%BA%8B%E4%B8%9A%E6%8D%90%E8%B5%A0%E6%B3%95&type=",
        "metadata_note": "补充清单原链接为第三方网站；改用国家法律法规数据库。",
    },
    99: {
        "official_url": "https://www.safe.gov.cn/safe/2006/0417/22172.html",
        "metadata_note": "补充清单原链接为第三方网站；改用国家外汇管理局官网正文及附件页面。",
    },
}


def clean(value: str) -> str:
    return ZERO_WIDTH_RE.sub("", value).strip()


def normalized_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", clean(value))
    value = value.replace("修订", "修正")
    value = re.sub(r"（(?:19|20)\d{2}年(?:\d{1,2}月)?修正）", "", value)
    value = re.sub(r"\((?:19|20)\d{2}年(?:\d{1,2}月)?修正\)", "", value)
    value = re.sub(r"[\s《》()（）\[\]【】,，.。:：;；·—_－-]", "", value)
    return value


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalized_title(left), normalized_title(right)).ratio()


def extract_url(cell: str) -> str:
    match = re.search(r"\((https?://[^)]+)\)", cell)
    if match:
        return match.group(1).strip()
    match = re.search(r"https?://\S+", cell)
    return match.group(0).rstrip("])") if match else ""


def parse_markdown(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    section = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^##\s+(.+)$", raw_line)
        if heading and not heading.group(1).startswith(("核验口径",)):
            section = heading.group(1).strip()
        if not re.match(r"^\|\s*\d+\s*\|", raw_line):
            continue
        cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        rows.append({
            "source_list_number": int(cells[0]),
            "title": clean(cells[1]),
            "publication_date": cells[2],
            "issuing_authority": cells[3],
            "validity_status": cells[4],
            "official_url": extract_url("|".join(cells[5:])),
            "section": section,
            "metadata_note": "来自用户提供的补充法规清单。",
        })
    rows.extend({"source_list_number": number, **record} for number, record in MISSING_ROWS.items())
    rows.sort(key=lambda item: int(item["source_list_number"]))
    for row in rows:
        override = OFFICIAL_URL_OVERRIDES.get(int(row["source_list_number"]))
        if override:
            row.update(override)
    numbers = [int(item["source_list_number"]) for item in rows]
    if numbers != list(range(1, 103)):
        raise RuntimeError(f"补充清单序号不完整：{numbers}")
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def choose_file(row: dict[str, object], files: list[Path], used: set[str]) -> tuple[Path, float]:
    title = str(row["title"])
    candidates = [
        (title_similarity(title, path.stem), path)
        for path in files
        if path.name not in used and path.name not in EXCLUDED_ATTACHMENTS
    ]
    candidates.sort(key=lambda item: (-item[0], item[1].name))
    if not candidates or candidates[0][0] < 0.72:
        preview = [(round(score, 3), path.name) for score, path in candidates[:3]]
        raise RuntimeError(f"未能唯一匹配本地原件：{title}；候选={preview}")
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.03:
        preview = [(round(score, 3), path.name) for score, path in candidates[:3]]
        raise RuntimeError(f"本地原件匹配歧义：{title}；候选={preview}")
    return candidates[0][1], candidates[0][0]


def record_for(row: dict[str, object], path: Path, catalog_index: int) -> dict[str, object]:
    file_hash = sha256(path)
    title = str(row["title"])
    version = VERSION_RE.search(title)
    return {
        "document_id": f"doc_source_{file_hash[:20]}",
        "document_title": title,
        "file_name": path.name,
        "source_type": path.suffix.lower().lstrip("."),
        "official_url": str(row["official_url"]),
        "issuing_authority": str(row["issuing_authority"]),
        "document_number": "",
        "document_number_status": "待从原件或官网正文补充",
        "publication_date": str(row["publication_date"]),
        "effective_date": "",
        "validity_status": str(row["validity_status"]),
        "version": version.group(1) if version else "",
        "catalog_group": f"补充法规/{row['section']}",
        "catalog_index": catalog_index,
        "chunk_count": 0,
        "character_count": 0,
        "file_sha256": file_hash,
        "file_size": path.stat().st_size,
        "source_status": "local_original_verified",
        "local_file_path": f"data/raw/监管文件/{path.name}",
        "official_link_type": "pdf" if urlparse(str(row["official_url"])).path.lower().endswith(".pdf") else "detail",
        "source_list_number": int(row["source_list_number"]),
        "source_list_section": str(row["section"]),
        "metadata_note": str(row["metadata_note"]),
    }


def excluded_record(path: Path, details: dict[str, str], catalog_index: int) -> dict[str, object]:
    file_hash = sha256(path)
    return {
        "document_id": f"doc_source_{file_hash[:20]}",
        "document_title": path.stem,
        "file_name": path.name,
        "source_type": path.suffix.lower().lstrip("."),
        "official_url": "",
        "issuing_authority": "",
        "document_number": "",
        "publication_date": "",
        "effective_date": "",
        "validity_status": "随主文件现行有效",
        "catalog_group": "补充法规/内嵌附件",
        "catalog_index": catalog_index,
        "chunk_count": 0,
        "character_count": 0,
        "file_sha256": file_hash,
        "file_size": path.stat().st_size,
        "source_status": "excluded_embedded_attachment",
        "exclusion_reason": details["reason"],
        "parent_document_title": details["parent_title"],
        "local_file_path": f"data/raw/监管文件/{path.name}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="导入2026-07-22补充法规清单并核对本地原件")
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    rows = parse_markdown(args.markdown)
    files = sorted(
        (path for path in args.raw_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda path: path.name,
    )
    existing = load_catalog(args.catalog)
    existing_by_file_name = {
        str(record.get("file_name", "")): record
        for record in existing
    }
    existing_supplement_names = {
        str(record.get("file_name", ""))
        for record in existing
        if record.get("source_list_number") or str(record.get("source_status", "")).startswith("excluded_")
    }
    base_records = [
        record for record in existing
        if str(record.get("file_name", "")) not in existing_supplement_names
    ]
    base_file_names = {str(record.get("file_name", "")) for record in base_records}
    supplemental_files = [path for path in files if path.name not in base_file_names]
    expected_names = {path.name for path in supplemental_files}
    if len(supplemental_files) != 104:
        raise RuntimeError(f"预期104个新增原件（102法规+2内嵌附件），实际{len(supplemental_files)}")

    used: set[str] = set()
    max_index = max((int(record.get("catalog_index", 0) or 0) for record in base_records), default=0)
    imported: list[dict[str, object]] = []
    match_audit: list[dict[str, object]] = []
    for offset, row in enumerate(rows, start=1):
        path, score = choose_file(row, supplemental_files, used)
        used.add(path.name)
        record = record_for(row, path, max_index + offset)
        previous = existing_by_file_name.get(path.name, {})
        for field in PRESERVED_BUILD_FIELDS:
            if field in previous:
                record[field] = previous[field]
        imported.append(record)
        match_audit.append({
            "source_list_number": row["source_list_number"],
            "document_title": row["title"],
            "file_name": path.name,
            "match_score": round(score, 4),
            "official_url": row["official_url"],
        })

    excluded: list[dict[str, object]] = []
    for offset, (file_name, details) in enumerate(EXCLUDED_ATTACHMENTS.items(), start=1):
        path = args.raw_dir / file_name
        if not path.exists():
            raise RuntimeError(f"缺少待排除的附件原件：{file_name}")
        used.add(file_name)
        excluded.append(excluded_record(path, details, max_index + len(rows) + offset))

    unmatched = sorted(expected_names - used)
    if unmatched:
        raise RuntimeError(f"存在未匹配新增原件：{unmatched}")

    all_records = base_records + imported + excluded
    if len({str(record.get("file_name", "")) for record in all_records}) != len(all_records):
        raise RuntimeError("写入前发现重复file_name")

    args.catalog.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in all_records) + "\n",
        encoding="utf-8",
    )
    audit = {
        "audit_date": date.today().isoformat(),
        "markdown": str(args.markdown.relative_to(ROOT)),
        "raw_dir": str(args.raw_dir.relative_to(ROOT)),
        "previous_catalog_records": len(existing),
        "supplemental_regulations": len(imported),
        "excluded_embedded_attachments": len(excluded),
        "final_catalog_records": len(all_records),
        "expected_active_documents": len(all_records) - len(excluded),
        "missing_markdown_rows_recovered": sorted(MISSING_ROWS),
        "matches": match_audit,
        "excluded": excluded,
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "imported": len(imported),
        "excluded": len(excluded),
        "catalog_records": len(all_records),
        "expected_active_documents": audit["expected_active_documents"],
        "minimum_match_score": min(item["match_score"] for item in match_audit),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
