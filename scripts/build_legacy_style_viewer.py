#!/usr/bin/env python3
"""Merge current canonical bodies into the user-approved seven-dimension viewer."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_base.build_chunk_review_viewer import (  # noqa: E402
    DEFAULT_CHUNKS_PATH,
    DEFAULT_CLASSIFICATIONS_PATH,
    DEFAULT_DOCUMENTS_DIR,
    public_data,
)


DEFAULT_TEMPLATE = ROOT / "knowledge_base/templates/regulation_viewer_legacy_7d.html"
DEFAULT_BASELINE = ROOT / "data/metadata/viewer_legacy_7d_baseline.json"
DEFAULT_OUTPUT = ROOT / "更新的法规/场外衍生品法规知识库_20260723.html"
DEFAULT_CLASSIFICATIONS = ROOT / "data/metadata/viewer_legacy_7d_classifications.json"
DEFAULT_EVIDENCE = ROOT / "data/metadata/viewer_legacy_7d_evidence.jsonl"
DEFAULT_AUDIT = ROOT / "更新的法规/七维分类与正文合并审计_20260724.json"
CLASSIFICATION_VERSION = "2026-07-24-legacy-seven-dimension-full-evidence-v1"

DIMENSIONS = (
    ("发文主体", "authority_groups"),
    ("交易场所", "trading_venues"),
    ("标的及业务品种", "underlying_business_types"),
    ("客户主体", "client_entity_types"),
    ("资金来源", "funding_sources"),
    ("产品载体", "product_vehicles"),
    ("涉及交易行为监管", "conduct_categories"),
)

TAG_PATTERNS = {
    "场外": (r"场外", r"柜台", r"非集中清算", r"银行间市场", r"协议交易"),
    "场内": (r"证券交易所", r"期货交易所", r"交易所市场", r"集中交易", r"竞价交易"),
    "综合业务": (r"业务活动", r"投资管理", r"资产管理", r"证券期货", r"制定本(?:法|办法|规定|规则|指引)"),
    "权益类": (r"股票", r"股权", r"权益类", r"上市公司", r"股票期权"),
    "利率及债券类": (r"利率", r"债券", r"固定收益", r"国债", r"回购"),
    "商品类": (r"商品", r"期货", r"大宗商品", r"套期保值"),
    "信用类": (r"信用衍生", r"信用保护", r"信用风险缓释", r"信用违约"),
    "可转债": (r"可转换公司债券", r"可交换公司债券", r"可转债"),
    "融资融券及证券出借": (r"融资融券", r"证券出借", r"转融通"),
    "外汇类": (r"外汇", r"汇率", r"结售汇", r"货币掉期"),
    "证券公司": (r"证券公司", r"证券经营机构"),
    "证券公司资管子公司": (r"证券公司资产管理子公司", r"证券公司资管子公司"),
    "基金管理公司": (r"基金管理公司", r"基金管理人"),
    "基金子公司": (r"基金管理公司子公司", r"基金子公司"),
    "私募基金管理人": (r"私募基金管理人", r"私募投资基金管理人"),
    "期货公司": (r"期货公司", r"期货经营机构"),
    "期货风险管理子公司": (r"风险管理公司", r"期货风险管理"),
    "商业银行": (r"商业银行", r"银行业金融机构"),
    "政策性银行": (r"政策性银行",),
    "外资银行": (r"外资银行", r"外国银行"),
    "银行理财子公司": (r"理财公司", r"银行理财子公司"),
    "保险集团（控股）公司": (r"保险集团(?:（控股）|\\(控股\\))公司", r"保险控股公司"),
    "保险公司": (r"保险公司",),
    "保险资产管理公司": (r"保险资产管理公司", r"保险资管"),
    "信托公司": (r"信托公司",),
    "养老金管理机构": (r"养老金管理", r"年金基金管理"),
    "普通非金融企业": (r"非金融企业", r"企业客户"),
    "上市公司": (r"上市公司",),
    "中央企业": (r"中央企业",),
    "地方国有企业": (r"地方国有企业", r"地方国资"),
    "国有控股上市公司": (r"国有控股上市公司",),
    "党政机关": (r"党政机关", r"行政单位"),
    "事业单位": (r"事业单位",),
    "科研院所": (r"科研院所", r"科学事业单位"),
    "高等院校": (r"高等学校", r"高等院校"),
    "社保基金管理机构": (r"社会保障基金", r"社保基金"),
    "社保经办机构": (r"社会保险经办机构", r"社保经办"),
    "基金会": (r"基金会",),
    "慈善组织": (r"慈善组织",),
    "红十字会": (r"红十字会",),
    "QFII/RQFII": (r"合格境外机构投资者", r"人民币合格境外机构投资者", r"QFII", r"RQFII"),
    "境外银行": (r"境外银行",),
    "境外券商": (r"境外证券公司", r"境外券商"),
    "境外基金": (r"境外基金",),
    "境外保险机构": (r"境外保险",),
    "境外企业": (r"境外企业", r"境外非金融"),
    "港澳机构": (r"香港", r"澳门", r"港澳"),
    "境外交易者及境外经纪机构": (r"境外交易者", r"境外经纪机构"),
    "跨境资金": (r"跨境资金", r"境外投资", r"境内外资金", r"外汇资金", r"汇出", r"汇入"),
    "自有资金": (r"自有资金", r"固有资金", r"自营资金"),
    "国资及财政资金": (r"国有资产", r"财政资金", r"国资"),
    "社保养老资金": (r"社会保障基金", r"社会保险基金", r"养老保险基金", r"企业年金", r"职业年金"),
    "保险资金": (r"保险资金",),
    "慈善捐赠资金": (r"慈善财产", r"捐赠财产", r"捐赠资金"),
    "科研事业单位资金": (r"科研资金", r"科学事业单位", r"事业收入"),
    "资管": (r"资产管理计划", r"资产管理产品", r"资产管理业务"),
    "公募基金": (r"公开募集证券投资基金", r"公募基金"),
    "私募基金": (r"私募投资基金", r"私募证券投资基金"),
    "理财": (r"理财产品", r"理财业务"),
    "信托": (r"信托计划", r"信托产品", r"信托业务"),
    "市场交易行为": (
        r"异常交易", r"操纵市场", r"内幕交易", r"短线交易", r"交易行为",
        r"报单", r"申报", r"不得", r"禁止",
    ),
    "机构交易内控": (
        r"内部控制", r"内控制度", r"合规管理", r"信息隔离", r"内部授权",
        r"内部审计", r"岗位职责",
    ),
    "风险控制措施": (
        r"风险管理", r"风险控制", r"风险限额", r"压力测试", r"保证金",
        r"应急预案", r"风险监测",
    ),
}

NEW_DOCUMENT_OVERRIDES = {
    "证券市场程序化交易管理规定（试行）": {
        "authority_groups": ["证监会"],
        "trading_venues": ["场内"],
        "underlying_business_types": ["综合业务"],
        "client_entity_types": [
            "证券公司", "基金管理公司", "私募基金管理人",
            "保险公司", "保险资产管理公司", "QFII/RQFII",
        ],
        "client_entity_groups": [],
        "funding_sources": [],
        "product_vehicles": [],
        "conduct_categories": ["市场交易行为", "机构交易内控", "风险控制措施"],
    },
    "关于上市公司内幕信息知情人登记管理制度的规定": {
        "authority_groups": ["证监会"],
        "trading_venues": [],
        "underlying_business_types": ["权益类"],
        "client_entity_types": ["上市公司"],
        "client_entity_groups": ["企业及国资类"],
        "funding_sources": [],
        "product_vehicles": [],
        "conduct_categories": [],
    },
}


def normalize_title(value: str) -> str:
    value = re.sub(r"\.(?:pdf|docx?|html)$", "", value, flags=re.I)
    value = re.sub(r"[\s《》【】()（）·•・“”‘’\[\]：:]", "", value)
    return (
        value
        .replace("2021年修订", "")
        .replace("2017年修订", "")
        .replace("2023年修正", "")
        .replace("2022年修订", "2022年修正")
    )


def compact_excerpt(text: str, match: re.Match[str] | None, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    center = match.start() if match else 0
    start = max(0, center - 80)
    end = min(len(text), start + limit)
    return f"{'…' if start else ''}{text[start:end].strip()}{'…' if end < len(text) else ''}"


def locator(block: dict) -> str:
    text = str(block.get("text", ""))
    article = re.match(r"^(第[一二三四五六七八九十百千万零〇\d]+条)", text)
    parts = [article.group(1) if article else str(block.get("block_type", "正文"))]
    page = block.get("source_page_start")
    if page not in (None, ""):
        parts.append(f"第{int(page) + 1}页")
    if block.get("block_id"):
        parts.append(str(block["block_id"]))
    return " / ".join(parts)


def find_block_evidence(document: dict, tag: str) -> tuple[dict, str, str]:
    patterns = TAG_PATTERNS.get(tag, (re.escape(tag),))
    blocks = document.get("structured_blocks", [])
    for block in blocks:
        text = str(block.get("text", ""))
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return block, match.group(0), compact_excerpt(text, match)
    title = document["document_title"]
    for pattern in patterns:
        match = re.search(pattern, title, re.I)
        if match:
            fallback = next((block for block in blocks if block.get("text")), {})
            text = str(fallback.get("text", title))
            return fallback, match.group(0), compact_excerpt(text, None)
    fallback = next(
        (
            block for block in blocks
            if block.get("block_type") in {"article", "paragraph"} and block.get("text")
        ),
        next((block for block in blocks if block.get("text")), {}),
    )
    return fallback, "", compact_excerpt(str(fallback.get("text", document.get("clean_text", ""))), None)


def evidence_reason(dimension: str, tag: str) -> str:
    return {
        "交易场所": f"法规正文体现与“{tag}”交易场所相关的适用范围或交易安排",
        "标的及业务品种": f"法规正文明确涉及“{tag}”对应的标的或业务品种",
        "客户主体": f"法规正文将“{tag}”列为适用、参与或受监管主体",
        "资金来源": f"法规正文明确涉及“{tag}”的来源、运用或管理",
        "产品载体": f"法规正文明确以“{tag}”相关产品或计划作为制度载体",
        "涉及交易行为监管": f"法规正文包含“{tag}”对应的行为规范或控制要求",
    }.get(dimension, f"法规发布信息支持“{tag}”分类")


def generated_evidence(document: dict, dimension: str, tag: str) -> dict:
    official_url = document.get("official_url", "")
    if dimension == "发文主体":
        return {
            "dimension": dimension,
            "tag": tag,
            "reason": f"法规发布机关属于“{tag}”分类",
            "basis": f"发布机关：{document.get('issuing_authority', '')}",
            "location": "法规元数据 / 发布机关",
            "page": "",
            "block_id": "",
            "matched_text": document.get("issuing_authority", ""),
            "evidence_level": "A-官方发布信息",
            "citation_nature": "法规元数据",
            "special_review_result": "逐标签补齐",
            "official_url": official_url,
        }
    block, matched_text, excerpt = find_block_evidence(document, tag)
    fallback = not matched_text
    return {
        "dimension": dimension,
        "tag": tag,
        "reason": evidence_reason(dimension, tag),
        "basis": excerpt,
        "location": locator(block) if block else "正文适用范围",
        "page": (int(block["source_page_start"]) + 1) if block and block.get("source_page_start") not in (None, "") else "",
        "block_id": block.get("block_id", "") if block else "",
        "matched_text": matched_text,
        "evidence_level": "B-正文适用范围综合判断" if fallback else "A-正文直接条款",
        "citation_nature": "规范化法规原文摘录",
        "special_review_result": "待人工复核" if fallback else "逐标签补齐",
        "official_url": official_url,
    }


def merge_document(current: dict, baseline: dict | None) -> tuple[dict, list[dict]]:
    title = current["document_title"]
    if baseline:
        current["official_url"] = baseline.get("official_url", "")
        for _dimension, field in DIMENSIONS:
            current[field] = list(baseline.get(field, []))
        current["client_entity_groups"] = list(baseline.get("client_entity_groups", []))
        original_evidence = baseline.get("classification_evidence", [])
    else:
        override = NEW_DOCUMENT_OVERRIDES.get(title)
        if not override:
            raise RuntimeError(f"旧版未收录且没有七维分类规则：{title}")
        for field, values in override.items():
            current[field] = list(values)
        original_evidence = []

    existing = {
        (row.get("dimension"), row.get("tag")): row
        for row in original_evidence
    }
    evidence_rows = []
    for dimension, field in DIMENSIONS:
        for tag in current.get(field, []):
            row = dict(existing.get((dimension, tag)) or generated_evidence(current, dimension, tag))
            row.update({
                "document_id": current["document_id"],
                "document_title": title,
                "issuing_authority": current.get("issuing_authority", ""),
                "dimension": dimension,
                "tag": tag,
                "official_url": current.get("official_url", ""),
            })
            evidence_rows.append(row)

    summary = "；".join(
        f"{dimension}：{'、'.join(current.get(field, []))}"
        for dimension, field in DIMENSIONS
        if current.get(field)
    )
    current.update({
        "classification_evidence": evidence_rows,
        "classification_version_new": CLASSIFICATION_VERSION,
        "classification_review_status": "七维标签逐项关联法规原文",
        "classification_basis_new": summary,
        "classification_summary": summary,
        "source_text_status": "规范化完整正文",
        "text_mode": "embedded",
        "official_review_note": "筛选标签与Excel证据明细使用同一份逐标签证据数据。",
    })
    return current, evidence_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="用旧版七维筛选器生成216部完整正文HTML")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--classifications-output", type=Path, default=DEFAULT_CLASSIFICATIONS)
    parser.add_argument("--evidence-output", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    baseline_payload = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline_by_title = {
        normalize_title(row["document_title"]): row
        for row in baseline_payload["documents"]
    }
    current_payload = public_data(
        DEFAULT_CHUNKS_PATH,
        DEFAULT_DOCUMENTS_DIR,
        DEFAULT_CLASSIFICATIONS_PATH,
    )
    documents = []
    all_evidence = []
    matched_baseline_titles = set()
    for current in current_payload["documents"]:
        key = normalize_title(current["document_title"])
        baseline = baseline_by_title.get(key)
        if baseline:
            matched_baseline_titles.add(key)
        merged, evidence = merge_document(current, baseline)
        documents.append(merged)
        all_evidence.extend(evidence)

    missing_baseline = sorted(set(baseline_by_title) - matched_baseline_titles)
    if missing_baseline:
        raise RuntimeError(f"旧版法规未匹配到当前正文：{missing_baseline}")
    if len(documents) != 216:
        raise RuntimeError(f"预期216部完整正文，实际{len(documents)}")
    if any(not document.get("clean_text") for document in documents):
        raise RuntimeError("存在空正文")

    current_payload["summary"] = {
        "documents": len(documents),
        "original_legacy_documents": len(baseline_by_title),
        "newly_completed_documents": len(documents) - len(baseline_by_title),
        "authorities": len({document["navigation_authority"] for document in documents}),
        "chunks": sum(document.get("chunk_count", 0) for document in documents),
        "reader_source": "216部规范化完整正文",
        "classification_dimensions": 7,
        "classification_version": CLASSIFICATION_VERSION,
        "official_urls_preserved_from_legacy": len(baseline_by_title),
    }
    current_payload["documents"] = documents
    template = args.template.read_text(encoding="utf-8")
    if template.count("{{VIEWER_DATA_JSON}}") != 1:
        raise RuntimeError("七维模板缺少唯一数据占位符")
    html = template.replace(
        "{{VIEWER_DATA_JSON}}",
        json.dumps(current_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")

    classifications = {
        "classification_version": CLASSIFICATION_VERSION,
        "dimensions": {
            dimension: sorted({
                tag
                for document in documents
                for tag in document.get(field, [])
            })
            for dimension, field in DIMENSIONS
        },
        "documents": [
            {
                "document_id": document["document_id"],
                "document_title": document["document_title"],
                "issuing_authority": document.get("issuing_authority", ""),
                "official_url": document.get("official_url", ""),
                **{field: document.get(field, []) for _dimension, field in DIMENSIONS},
                "client_entity_groups": document.get("client_entity_groups", []),
                "classification_summary": document["classification_summary"],
                "classification_evidence_count": len(document["classification_evidence"]),
            }
            for document in documents
        ],
    }
    args.classifications_output.write_text(
        json.dumps(classifications, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with args.evidence_output.open("w", encoding="utf-8") as handle:
        for row in all_evidence:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    level_counts = Counter(row.get("evidence_level", "") for row in all_evidence)
    audit = {
        "classification_version": CLASSIFICATION_VERSION,
        "legacy_documents": len(baseline_by_title),
        "current_documents": len(documents),
        "full_text_documents": sum(bool(document.get("clean_text")) for document in documents),
        "preserved_legacy_official_urls": len(baseline_by_title),
        "new_document_titles": [
            document["document_title"]
            for document in documents
            if normalize_title(document["document_title"]) not in baseline_by_title
        ],
        "classification_assignments": sum(
            len(document.get(field, []))
            for document in documents
            for _dimension, field in DIMENSIONS
        ),
        "evidence_rows": len(all_evidence),
        "evidence_level_counts": dict(level_counts),
        "fallback_rows": [
            {
                "document_title": row["document_title"],
                "dimension": row["dimension"],
                "tag": row["tag"],
                "location": row.get("location", ""),
            }
            for row in all_evidence
            if row.get("evidence_level") == "B-正文适用范围综合判断"
        ],
    }
    args.audit_output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "documents": len(documents),
        "chunks": current_payload["summary"]["chunks"],
        "evidence_rows": len(all_evidence),
        "evidence_level_counts": dict(level_counts),
        "fallback_rows": len(audit["fallback_rows"]),
        "bytes": len(html.encode("utf-8")),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
