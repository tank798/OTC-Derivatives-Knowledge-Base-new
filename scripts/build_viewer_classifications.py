#!/usr/bin/env python3
"""Build auditable viewer classifications from every canonical regulation body."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = ROOT / "data/processed/documents/json"
OUTPUT_PATH = ROOT / "data/metadata/viewer_classifications.json"
EVIDENCE_PATH = ROOT / "data/metadata/viewer_classification_evidence.jsonl"
CLASSIFICATION_VERSION = "2026-07-24-body-evidence-v1"


@dataclass(frozen=True)
class Rule:
    label: str
    patterns: tuple[str, ...]
    explanation: str


ENTITY_RULES = (
    Rule("证券公司", (r"证券公司", r"证券经营机构"), "正文明确规范证券公司或证券经营机构"),
    Rule(
        "基金及私募机构",
        (r"基金管理人", r"基金管理公司", r"基金托管人", r"证券投资基金", r"私募(?:投资)?基金"),
        "正文明确涉及基金管理、托管或私募基金主体",
    ),
    Rule(
        "银行及理财机构",
        (r"商业银行", r"银行业金融机构", r"理财公司", r"银行理财", r"银行间市场成员"),
        "正文明确涉及银行、理财机构或银行间市场成员",
    ),
    Rule(
        "期货机构",
        (r"期货公司", r"期货经营机构", r"期货交易所", r"风险管理公司", r"期货市场监控中心"),
        "正文明确涉及期货公司、风险管理公司或期货市场基础设施",
    ),
    Rule(
        "保险机构",
        (r"保险公司", r"保险机构", r"保险资产管理", r"保险资金"),
        "正文明确涉及保险机构、保险资管或保险资金",
    ),
    Rule("信托机构", (r"信托公司", r"信托机构", r"信托业务"), "正文明确涉及信托机构或信托业务"),
    Rule(
        "上市公司及相关主体",
        (r"上市公司", r"挂牌公司", r"发行人", r"控股股东", r"实际控制人"),
        "正文明确涉及上市公司、挂牌公司、发行人或其相关主体",
    ),
    Rule(
        "机构投资者",
        (r"社会保障基金", r"基本养老保险基金", r"企业年金", r"职业年金", r"慈善组织", r"事业单位"),
        "正文明确涉及社保、年金、慈善组织或事业单位等机构投资者",
    ),
    Rule(
        "境外投资者",
        (r"境外机构投资者", r"境外投资者", r"合格境外", r"外国投资者", r"跨境"),
        "正文明确涉及境外投资者或跨境参与主体",
    ),
    Rule(
        "其他金融机构",
        (r"金融机构", r"金融资产投资公司", r"金融基础设施"),
        "正文明确规范金融机构或金融基础设施",
    ),
    Rule(
        "其他市场参与者",
        (r"投资者", r"交易者", r"市场参与人", r"会员", r"客户"),
        "正文明确涉及投资者、交易者、会员或客户",
    ),
)


BUSINESS_RULES = (
    Rule("场外期权", (r"场外期权",), "正文直接涉及场外期权业务"),
    Rule("收益互换", (r"收益互换",), "正文直接涉及收益互换业务"),
    Rule("收益凭证", (r"收益凭证",), "正文直接涉及收益凭证业务"),
    Rule(
        "信用衍生品",
        (r"信用衍生", r"信用保护", r"信用风险缓释", r"信用违约互换"),
        "正文涉及信用衍生品、信用保护或信用风险缓释工具",
    ),
    Rule(
        "利率与债券衍生品",
        (r"利率互换", r"远期利率协议", r"债券远期", r"利率衍生", r"债券借贷", r"回购.*衍生"),
        "正文涉及利率、债券远期或相关衍生交易",
    ),
    Rule(
        "外汇衍生品",
        (r"外汇衍生", r"外汇远期", r"外汇掉期", r"货币掉期", r"人民币外汇"),
        "正文涉及外汇远期、掉期或其他外汇衍生交易",
    ),
    Rule(
        "商品及期货衍生品",
        (r"商品衍生", r"期货交易", r"期货市场", r"套期保值", r"期货合约"),
        "正文涉及商品衍生品、期货交易或套期保值",
    ),
    Rule("股票期权", (r"股票期权",), "正文直接涉及股票期权业务"),
    Rule(
        "证券与可转债交易",
        (r"证券交易", r"可转换公司债券", r"可转债", r"股票交易", r"融资融券", r"转融通"),
        "正文涉及证券、股票、融资融券或可转换公司债券交易",
    ),
    Rule(
        "资产管理产品",
        (r"资产管理产品", r"资产管理业务", r"理财产品", r"基金产品", r"保险资产管理产品"),
        "正文涉及基金、理财、保险资管或其他资产管理产品",
    ),
    Rule(
        "机构与资金准入",
        (r"投资范围", r"资金运用", r"准入条件", r"合格投资者", r"可投资"),
        "正文规定机构、资金或投资者的准入及可投资范围",
    ),
    Rule("场外衍生品", (r"场外衍生", r"金融衍生产品交易", r"衍生品交易"), "正文直接涉及场外或金融衍生品交易"),
)


TOPIC_RULES = (
    Rule(
        "业务准入",
        (r"业务准入", r"准入条件", r"备案管理", r"资格管理", r"申请.*资格", r"许可"),
        "正文规定业务资格、许可、备案或准入条件",
    ),
    Rule(
        "交易管理",
        (r"交易管理", r"交易规则", r"交易行为", r"交易指令", r"交易合同", r"主协议"),
        "正文规定交易规则、交易行为、交易指令或合约安排",
    ),
    Rule(
        "产品运作",
        (r"产品运作", r"募集", r"申购", r"赎回", r"产品管理", r"托管"),
        "正文规定产品募集、申赎、管理或托管运作",
    ),
    Rule(
        "投资范围与持仓",
        (r"投资范围", r"投资比例", r"持仓", r"持股", r"投资限制", r"标的资产"),
        "正文规定投资范围、比例、标的或持仓限制",
    ),
    Rule(
        "估值定价",
        (r"估值", r"定价", r"公允价值", r"参考价格", r"转股价格"),
        "正文规定估值、定价、公允价值或价格形成",
    ),
    Rule(
        "保证金与清算",
        (r"保证金", r"履约保障", r"清算", r"结算", r"净额结算", r"中央对手"),
        "正文规定保证金、履约保障、清算或结算机制",
    ),
    Rule(
        "信息披露与报送",
        (r"信息披露", r"报告制度", r"报送", r"报告信息", r"登记管理", r"备案报告"),
        "正文规定信息披露、报告、登记或报送义务",
    ),
    Rule(
        "内控与利益冲突",
        (r"内部控制", r"内控制度", r"合规管理", r"利益冲突", r"信息隔离墙", r"关联交易"),
        "正文规定内部控制、合规、信息隔离或利益冲突管理",
    ),
    Rule(
        "风险管理",
        (r"风险管理", r"风险控制", r"风险监测", r"压力测试", r"风险指标", r"应急处置"),
        "正文规定风险识别、控制、监测、压力测试或应急处置",
    ),
    Rule(
        "投资者适当性与保护",
        (r"投资者适当性", r"适当性管理", r"投资者保护", r"风险承受能力", r"合格投资者"),
        "正文规定投资者适当性、风险承受能力或保护机制",
    ),
    Rule(
        "监督检查与处罚",
        (r"监督管理", r"监督检查", r"自律管理", r"行政处罚", r"纪律处分", r"法律责任"),
        "正文规定监管、自律检查、处罚或法律责任",
    ),
    Rule(
        "跨境投资与互联",
        (r"跨境", r"境外投资", r"互联互通", r"境内外", r"外国投资者"),
        "正文规定跨境投资、境内外活动或市场互联互通",
    ),
    Rule(
        "程序化与异常交易",
        (r"程序化交易", r"高频交易", r"异常交易", r"报单.*撤单", r"算法交易"),
        "正文规定程序化、高频或异常交易行为",
    ),
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def excerpt(text: str, match: re.Match[str], limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    start = max(0, match.start() - 55)
    end = min(len(compact), match.end() + 105)
    value = compact[start:end].strip()
    return f"{'…' if start else ''}{value}{'…' if end < len(compact) else ''}"


def block_locator(block: dict) -> str:
    text = block.get("text", "")
    article = re.match(r"^(第[一二三四五六七八九十百千万零〇\d]+条)", text)
    page_start = block.get("source_page_start")
    page_end = block.get("source_page_end")
    parts: list[str] = []
    if article:
        parts.append(article.group(1))
    elif block.get("block_type"):
        parts.append(str(block["block_type"]))
    if page_start:
        page = f"第{page_start}页"
        if page_end and page_end != page_start:
            page = f"第{page_start}-{page_end}页"
        parts.append(page)
    parts.append(str(block.get("block_id", "")))
    return " / ".join(part for part in parts if part)


def find_evidence(document: dict, patterns: Iterable[str]) -> dict | None:
    title = document["metadata"]["document_title"]
    for pattern in patterns:
        match = re.search(pattern, title, re.I)
        if match:
            return {
                "matched_text": match.group(0),
                "locator": "法规标题",
                "page": "",
                "block_id": "",
                "excerpt": title,
            }
    for block in document.get("structured_blocks", []):
        text = block.get("text", "")
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return {
                    "matched_text": match.group(0),
                    "locator": block_locator(block),
                    "page": block.get("source_page_start") or "",
                    "block_id": block.get("block_id", ""),
                    "excerpt": excerpt(text, match),
                }
    return None


def rule_score(document: dict, rule: Rule) -> tuple[int, int]:
    title = document["metadata"]["document_title"]
    blocks = document.get("structured_blocks", [])
    body = "\n".join(block.get("text", "") for block in blocks)
    early_body = "\n".join(block.get("text", "") for block in blocks[:15])
    headings = "\n".join(
        block.get("text", "")
        for block in blocks
        if block.get("block_type") in {
            "document_title", "part", "chapter", "section",
            "guide_heading", "guide_subheading", "guide_minor_heading",
        }
    )
    total_matches = sum(len(re.findall(pattern, body, re.I)) for pattern in rule.patterns)
    score = min(total_matches, 20)
    if any(re.search(pattern, title, re.I) for pattern in rule.patterns):
        score += 50
    if any(re.search(pattern, early_body, re.I) for pattern in rule.patterns):
        score += 12
    if any(re.search(pattern, headings, re.I) for pattern in rule.patterns):
        score += 20
    return score, total_matches


def classify(document: dict, dimension: str, rules: tuple[Rule, ...], cap: int) -> tuple[list[str], list[dict]]:
    labels: list[str] = []
    evidence_rows: list[dict] = []
    candidates: list[tuple[int, int, int, Rule, dict]] = []
    for rule_index, rule in enumerate(rules):
        score, match_count = rule_score(document, rule)
        if score < 2:
            continue
        evidence = find_evidence(document, rule.patterns)
        if not evidence:
            continue
        candidates.append((score, match_count, -rule_index, rule, evidence))
    candidates.sort(reverse=True, key=lambda item: item[:3])
    metadata = document["metadata"]
    for score, match_count, _rule_index, rule, evidence in candidates[:cap]:
        labels.append(rule.label)
        evidence_rows.append({
            "document_id": document["document_id"],
            "document_title": metadata["document_title"],
            "issuing_authority": metadata.get("issuing_authority", ""),
            "dimension": dimension,
            "label": rule.label,
            "reason": rule.explanation,
            "rule_score": score,
            "match_count": match_count,
            **evidence,
        })
    return labels, evidence_rows


def load_documents(path: Path) -> list[dict]:
    documents = [json.loads(file.read_text(encoding="utf-8")) for file in path.glob("*.json")]
    documents.sort(key=lambda item: (
        int(item.get("metadata", {}).get("catalog_index") or 9999),
        item["metadata"]["document_title"],
    ))
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description="依据完整法规正文重建查看器分类及证据映射")
    parser.add_argument("--documents-dir", type=Path, default=DOCUMENTS_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--evidence-output", type=Path, default=EVIDENCE_PATH)
    args = parser.parse_args()

    documents = load_documents(args.documents_dir.resolve())
    classifications: list[dict] = []
    all_evidence: list[dict] = []
    for document in documents:
        entities, entity_evidence = classify(document, "适用对象", ENTITY_RULES, 5)
        businesses, business_evidence = classify(document, "业务类型", BUSINESS_RULES, 5)
        topics, topic_evidence = classify(document, "监管事项", TOPIC_RULES, 8)
        if not entities:
            entities = ["其他市场参与者"]
            entity_evidence = [{
                "document_id": document["document_id"],
                "document_title": document["metadata"]["document_title"],
                "issuing_authority": document["metadata"].get("issuing_authority", ""),
                "dimension": "适用对象",
                "label": "其他市场参与者",
                "reason": "正文未限定特定机构类型，按一般市场参与主体归类",
                "matched_text": "",
                "locator": "适用范围综合判断",
                "page": "",
                "block_id": "",
                "excerpt": document["clean_text"][:180].replace("\n", " "),
            }]
        if not businesses:
            businesses = ["综合监管"]
            business_evidence = [{
                "document_id": document["document_id"],
                "document_title": document["metadata"]["document_title"],
                "issuing_authority": document["metadata"].get("issuing_authority", ""),
                "dimension": "业务类型",
                "label": "综合监管",
                "reason": "法规正文为综合性监管要求，未限定单一衍生品业务",
                "matched_text": "",
                "locator": "全文适用范围综合判断",
                "page": "",
                "block_id": "",
                "excerpt": document["clean_text"][:180].replace("\n", " "),
            }]
        if not topics:
            topics = ["监督检查与处罚"]
            topic_evidence = [{
                "document_id": document["document_id"],
                "document_title": document["metadata"]["document_title"],
                "issuing_authority": document["metadata"].get("issuing_authority", ""),
                "dimension": "监管事项",
                "label": "监督检查与处罚",
                "reason": "正文为规范性监管文件，按总体监管要求归类",
                "matched_text": "",
                "locator": "全文综合判断",
                "page": "",
                "block_id": "",
                "excerpt": document["clean_text"][:180].replace("\n", " "),
            }]
        evidence_rows = entity_evidence + business_evidence + topic_evidence
        all_evidence.extend(evidence_rows)
        classifications.append({
            "document_id": document["document_id"],
            "document_title": document["metadata"]["document_title"],
            "applicable_entities": entities,
            "business_categories": businesses,
            "regulatory_topics": topics,
            "classification_version": CLASSIFICATION_VERSION,
            "classification_basis": "依据完整规范化正文逐块匹配；每个标签均保留原文页码、块号和摘录",
            "classification_evidence_count": len(evidence_rows),
        })

    payload = {
        "classification_version": CLASSIFICATION_VERSION,
        "dimensions": {
            "适用对象": [rule.label for rule in ENTITY_RULES],
            "业务类型": [rule.label for rule in BUSINESS_RULES] + ["综合监管"],
            "监管事项": [rule.label for rule in TOPIC_RULES],
        },
        "documents": classifications,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    with args.evidence_output.open("w", encoding="utf-8") as handle:
        for row in all_evidence:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({
        "documents": len(classifications),
        "evidence_rows": len(all_evidence),
        "output": str(args.output),
        "evidence_output": str(args.evidence_output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
