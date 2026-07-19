#!/usr/bin/env python3
"""Build the standalone法规 viewer from canonical documents and retrieval chunks."""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = ROOT / "data/processed/chunks/jsonl/all_chunks.jsonl"
DEFAULT_DOCUMENTS_DIR = ROOT / "data/processed/documents/json"
DEFAULT_CLASSIFICATIONS_PATH = ROOT / "data/metadata/viewer_classifications.json"
DEFAULT_TEMPLATE_PATH = ROOT / "knowledge_base/templates/regulation_viewer.html"
DEFAULT_OUTPUT_PATH = ROOT / "docs/场外衍生品法规知识库.html"

HISTORICAL_AUTHORITY_MAP = {
    "中国银行业监督管理委员会": "国家金融监督管理总局",
    "中国银行业监督管理委员会办公厅": "国家金融监督管理总局",
    "中国保险监督管理委员会": "国家金融监督管理总局",
    "中国保险监督管理委员会办公厅": "国家金融监督管理总局",
    "中国银行保险监督管理委员会": "国家金融监督管理总局",
    "中国银行保险监督管理委员会办公厅": "国家金融监督管理总局",
    "中国银监会": "国家金融监督管理总局",
    "中国银监会办公厅": "国家金融监督管理总局",
    "中国保监会": "国家金融监督管理总局",
    "中国保监会办公厅": "国家金融监督管理总局",
    "中国银保监会": "国家金融监督管理总局",
    "中国银保监会办公厅": "国家金融监督管理总局",
}
NAVIGATION_AUTHORITY_MAP = {**HISTORICAL_AUTHORITY_MAP, "中国人民银行办公厅": "中国人民银行"}
NAVIGATION_AUTHORITY_PRIORITY = [
    "中国证券监督管理委员会",
    "中国证券投资基金业协会",
    "中国证券业协会",
    "上海证券交易所",
    "深圳证券交易所",
    "中国期货业协会",
    "国家金融监督管理总局",
]


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def first_issuing_authority(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "其他监管机构"
    depth = 0
    for index, char in enumerate(text):
        if char in "（(【[":
            depth += 1
        elif char in "）)】]" and depth:
            depth -= 1
        elif depth == 0 and char in "、，,；;/":
            return text[:index].strip() or "其他监管机构"
    return text


def navigation_authority(value: str) -> str:
    first = first_issuing_authority(value)
    clean = re.sub(r"[（(]经.+[）)]$", "", first).strip()
    clean = clean.removesuffix("（历史机构）").removesuffix("(历史机构)").strip()
    return NAVIGATION_AUTHORITY_MAP.get(clean, clean or "其他监管机构")


def validity_category(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("现行使用"):
        return "现行使用（官网仍列示）"
    if "已公布" in text and "尚未施行" in text:
        return "已公布、尚未施行"
    if text.startswith("现行有效"):
        return "现行有效"
    return text or "状态未载"


def classification_lookup(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["document_id"]: row for row in payload.get("documents", [])}


def structured_lookup(directory: Path) -> dict[str, dict]:
    rows = {}
    for path in directory.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        rows[row["document_id"]] = row
    return rows


def public_data(chunks_path: Path, documents_dir: Path, classifications_path: Path) -> dict:
    chunks = read_jsonl(chunks_path)
    structured = structured_lookup(documents_dir)
    classifications = classification_lookup(classifications_path)
    documents: OrderedDict[str, dict] = OrderedDict()
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("all_chunks.jsonl contains duplicate chunk_id values")

    for chunk in chunks:
        document_id = chunk["document_id"]
        source = structured.get(document_id)
        if not source:
            raise ValueError(f"缺少结构化正文：{document_id}")
        metadata = source.get("metadata", {})
        document = documents.setdefault(
            document_id,
            {
                "document_id": document_id,
                "document_title": metadata.get("document_title") or chunk.get("document_title", ""),
                "file_name": source.get("file_name") or chunk.get("file_name", ""),
                "issuing_authority": metadata.get("issuing_authority") or chunk.get("issuing_authority", ""),
                "navigation_authority": navigation_authority(
                    metadata.get("issuing_authority") or chunk.get("issuing_authority", "")
                ),
                "document_number": metadata.get("document_number") or chunk.get("document_number", ""),
                "validity_status": metadata.get("validity_status") or chunk.get("validity_status", ""),
                "validity_category": validity_category(
                    metadata.get("validity_status") or chunk.get("validity_status", "")
                ),
                "source_type": (
                    Path(source.get("file_name") or chunk.get("file_name", "")).suffix.lstrip(".")
                    or (chunk.get("source_type", "") or "").split("+", 1)[0]
                ).upper(),
                "official_url": metadata.get("official_url") or chunk.get("official_url", ""),
                "publication_date": metadata.get("publication_date") or chunk.get("publication_date", ""),
                "effective_date": metadata.get("effective_date") or chunk.get("effective_date", ""),
                "clean_text": source.get("clean_text") or source.get("normalized_text", ""),
                "clean_text_hash": source.get("clean_text_hash", ""),
                "structured_blocks": source.get("structured_blocks", []),
                "parsing_warnings": source.get("warnings", []),
                "chunks": [],
            },
        )
        document["chunks"].append(
            {
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "character_count": chunk.get("character_count", 0),
                "body_text": chunk.get("body_text", ""),
                "article_start": chunk.get("article_start", ""),
                "article_end": chunk.get("article_end", ""),
                "chapter_title": chunk.get("chapter_title", ""),
                "section_title": chunk.get("section_title", ""),
                "part_title": chunk.get("part_title", ""),
                "attachment_name": chunk.get("attachment_name", ""),
                "section_path": chunk.get("section_path", []),
            }
        )

    for document in documents.values():
        if not document["clean_text"] or not document["structured_blocks"]:
            raise ValueError(f"阅读正文数据不完整：{document['document_id']}")
        document["chunks"].sort(key=lambda item: item["chunk_index"])
        document["chunk_count"] = len(document["chunks"])
        annotation = dict(classifications.get(document["document_id"], {}))
        annotation.pop("document_id", None)
        annotation.pop("document_title", None)
        document.update(annotation)

    document_list = list(documents.values())
    priority_position = {
        authority: index for index, authority in enumerate(NAVIGATION_AUTHORITY_PRIORITY)
    }
    document_list.sort(
        key=lambda document: (
            0 if document["navigation_authority"] in priority_position else 1,
            priority_position.get(document["navigation_authority"], len(priority_position)),
            document["document_title"] if document["navigation_authority"] in priority_position else "",
        )
    )
    authorities = {document["navigation_authority"] for document in document_list}
    return {
        "summary": {
            "documents": len(documents),
            "authorities": len(authorities),
            "chunks": len(chunks),
            "reader_source": "clean_text+structured_blocks",
            "classification_dimensions": 4,
        },
        "documents": document_list,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成场外衍生品法规知识库单文件HTML")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--documents-dir", type=Path, default=DEFAULT_DOCUMENTS_DIR)
    parser.add_argument("--classifications", type=Path, default=DEFAULT_CLASSIFICATIONS_PATH)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    data = public_data(
        args.chunks.resolve(),
        args.documents_dir.resolve(),
        args.classifications.resolve(),
    )
    if data["summary"]["documents"] != 114:
        raise ValueError(f"法规数量必须为114，当前为{data['summary']['documents']}")
    template = args.template.resolve().read_text(encoding="utf-8")
    if template.count("__VIEWER_DATA__") != 1:
        raise ValueError("HTML模板必须且只能包含一个__VIEWER_DATA__占位符")
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = template.replace("__VIEWER_DATA__", serialized)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "documents": data["summary"]["documents"],
        "authorities": data["summary"]["authorities"],
        "chunks": data["summary"]["chunks"],
        "reader_source": data["summary"]["reader_source"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
