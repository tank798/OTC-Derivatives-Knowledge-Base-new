from __future__ import annotations

import re
from pathlib import Path

from models import SourceBlock


RATE_DEFINITION_FILE = "中国银行间市场利率衍生产品交易定义文件（2022年版）.pdf"
CREDIT_VALUATION_FILE = "证券投资基金投资信用衍生品估值指引(试行).pdf"


def _replace_between(text: str, start: str, end: str, formula: str) -> str:
    pattern = re.compile(f"({re.escape(start)}).*?({re.escape(end)})", re.S)
    return pattern.sub(lambda match: f"{match.group(1)}\n【公式（按原PDF二维排版线性化）】{formula}\n{match.group(2)}", text, count=1)


def _rate_definition(blocks: list[SourceBlock]) -> int:
    changed = 0
    for block in blocks:
        if block.page != 16 or "贴现因子适用如下公式" not in block.text:
            continue
        updated = _replace_between(
            block.text,
            "贴现因子适用如下公式:",
            "其中,",
            "λ = 1 / [1 + (r × N / D)]",
        )
        if updated != block.text:
            block.text = updated
            changed += 1
    return changed


CREDIT_FORMULAS: dict[int, list[tuple[str, str, str]]] = {
    6: [(
        "估值公式如下:", "其中:",
        "V_CRMW = [(1 - exp((d / TY) × ln(1 - D))) × FV × (1 - R)] / [1 + r_d × (d / TY)]",
    )],
    7: [
        (
            "估值公式如下:", "其中:",
            "V_CRMW = FV / [1 + y_s × (d / TY)] - FV / [1 + y_d × (d / TY)]",
        ),
        (
            "估值公式如下:", "其中:",
            "V_CRMW = {[(1 - exp(t_1 × ln(1 - D))) × FV × (1 - R)] / (1 + r_1)^{t_1}} + ⋯ + "
            "{[exp(t_1 × ln(1 - D)) × (1 - D)^{n-2} × D × FV × (1 - R)] / (1 + r_n)^{t_n}}",
        ),
    ],
    8: [(
        "估值公式如下:", "其中:",
        "V_CRMW = [CF_1/(1+y_s)^1 + CF_2/(1+y_s)^2 + ⋯ + CF_n/(1+y_s)^n] - "
        "[CF_1/(1+y_d)^1 + CF_2/(1+y_d)^2 + ⋯ + CF_n/(1+y_d)^n]",
    )],
    10: [(
        "隐含违约率公式如下:", "其中:",
        "PV = {exp[(d/TY) × ln(1-P)] × FV + [1-exp((d/TY) × ln(1-P))] × FV × R} / "
        "[1 + r_d × (d/TY)]",
    )],
    11: [(
        "隐含违约率公式如下:", "其中:",
        "PV = {exp[t_1 × ln(1-P)] × CF_1 + [1-exp(t_1 × ln(1-P))] × CF_n × R} / (1+r_1)^{t_1} + ⋯ + "
        "{exp[t_1 × ln(1-P)] × (1-P)^{n-2} × [(1-P) × CF_n + P × CF_n × R]} / (1+r_n)^{t_n}",
    )],
}


COMPLEX_PAGE_NINE_FORMULA = (
    "V_CRMW = FV × (1-R) × ∫_{t}^{T_n} {[1/(1+r_{s-t})^{s-t}] × h × exp[-h(s-t)]} ds "
    "- 100 × C_1 × [Σ_{i=j+1}^{n} {(T_i-T_{i-1}) × [1/(1+r_{T_i-t})^{T_i-t}] × "
    "[1-exp(-h(T_i-t))]} + ∫_{t}^{T_{j+1}} {(s-T_j) × [1/(1+r_{s-t})^{s-t}] × h × "
    "exp[-h(s-t)]} ds + Σ_{k=j+1}^{n-1} ∫_{T_k}^{T_{k+1}} {(s-T_k) × "
    "[1/(1+r_{s-t})^{s-t}] × h × exp[-h(s-t)]} ds]；其中 T_j < t < T_{j+1}"
)

CREDIT_DEFAULT_PROBABILITY_TEXT = (
    "考虑 CRMW 创设机构风险下标的债券(标的主体)年化违约概率 D = P(A∩B̄),定义为:\n"
    "【公式(按原PDF二维排版线性化)】P(A∩B̄) = P(A|B̄) × P(B̄)\n"
    "其中,P(A)为标的债券年化违约概率,P(B)=1-P(B̄)为创设机构年化违约概率,P(A|B̄)为条件年化违约概率。"
    "在创设机构和标的债券发行人违约相关性w很小的情况下,P(A|B̄)可近似为P(A);"
    "在相关性w很大的情况下,P(A|B̄)可近似为0。现实中相关性一般位于0和1之间,因此可通过相关系数加权近似为:\n"
    "【公式(按原PDF二维排版线性化)】P(A∩B̄) = (1-w) × P(A) × P(B̄)"
)


def _credit_valuation(blocks: list[SourceBlock]) -> int:
    changed = 0
    seen_on_page: dict[int, int] = {}
    for block in blocks:
        if block.page == 10 and "年化违约概率" in block.text and "P AB" in block.text:
            block.text = CREDIT_DEFAULT_PROBABILITY_TEXT
            changed += 1
            continue
        if block.page == 9 and block.text.startswith("T 1 V ="):
            marker = "其中:"
            suffix = block.text.split(marker, 1)[1] if marker in block.text else block.text
            block.text = f"【公式（按原PDF二维排版线性化）】{COMPLEX_PAGE_NINE_FORMULA}\n{marker}{suffix}"
            changed += 1
            continue
        candidates = CREDIT_FORMULAS.get(block.page, [])
        if not candidates:
            continue
        occurrence = seen_on_page.get(block.page, 0)
        if "估值公式如下:" not in block.text and "隐含违约率公式如下:" not in block.text:
            continue
        if occurrence >= len(candidates):
            continue
        start, end, formula = candidates[occurrence]
        updated = _replace_between(block.text, start, end, formula)
        seen_on_page[block.page] = occurrence + 1
        if updated != block.text:
            block.text = updated
            changed += 1
    return changed


def apply_verified_formula_overrides(path: Path, blocks: list[SourceBlock]) -> int:
    """Linearize formulas verified against the rendered original PDF.

    PDF text layers do not encode fraction bars or two-dimensional operator
    layout.  These narrow, source-specific overrides preserve mathematical
    order without changing the original files.
    """
    if path.name == RATE_DEFINITION_FILE:
        return _rate_definition(blocks)
    if path.name == CREDIT_VALUATION_FILE:
        return _credit_valuation(blocks)
    return 0
