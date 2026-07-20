from __future__ import annotations

from pathlib import Path
import re

from models import SourceBlock


RATE_DEFINITION_FILE = "中国银行间市场利率衍生产品交易定义文件（2022年版）.pdf"
CREDIT_VALUATION_FILE = "证券投资基金投资信用衍生品估值指引(试行).pdf"
FORMULA_MARKER = "【公式（按原PDF二维排版线性化）】"


def _set_formula_data(
    block: SourceBlock,
    expressions: list[str],
    latex_expressions: list[str],
    *,
    conversion_status: str = "verified_linearized_and_latex",
) -> None:
    """Keep a searchable expression and a source-verified display expression."""
    block.formula_data = {
        "raw_text": block.text,
        "expressions": expressions,
        "latex_expressions": latex_expressions,
        # Retain the old scalar key for consumers that only display one formula.
        "latex": latex_expressions[0] if len(latex_expressions) == 1 else "",
        "formula_label": "公式",
        "source_page": block.page,
        "conversion_status": conversion_status,
    }


def _replace_between(text: str, start: str, end: str, formula: str, tail: str | None = None) -> str:
    # A formula block may be followed by a badly ordered PDF text-layer copy
    # of the same variable definitions.  Replace the complete remainder of
    # that block so the verified definitions are not duplicated.
    pattern = re.compile(f"({re.escape(start)}).*", re.S)
    suffix = tail if tail is not None else end
    return pattern.sub(
        lambda match: f"{match.group(1)}\n{FORMULA_MARKER}{formula}\n{suffix}",
        text,
        count=1,
    )


def _rate_definition(blocks: list[SourceBlock]) -> int:
    changed = 0
    for block in blocks:
        if block.page != 16 or "贴现因子适用如下公式" not in block.text:
            continue
        expression = "λ = 1 / [1 + (r × N / D)]"
        updated = _replace_between(
            block.text,
            "贴现因子适用如下公式:",
            "其中,",
            expression,
            "其中,λ 是贴现因子。",
        )
        if updated != block.text:
            block.text = updated
            _set_formula_data(block, [expression], [r"\lambda=\frac{1}{1+\frac{rN}{D}}"])
            changed += 1
    return changed


# Each tuple is: lead, end marker, searchable expression, display LaTeX,
# verified variable definitions.  The definitions are kept in the source text
# so that the HTML reader and retrieval index see the same corrected wording.
CREDIT_FORMULAS: dict[int, list[tuple[str, str, str, str, str]]] = {
    6: [(
        "估值公式如下:",
        "其中:",
        "V_CRMW = [(1 - exp((d / TY) × ln(1 - D))) × FV × (1 - R)] / [1 + r_d × (d / TY)]",
        r"V_{\mathrm{CRMW}}=\frac{\left[1-\exp\left(\frac{d}{TY}\ln(1-D)\right)\right]FV(1-R)}{1+r_d\left(\frac{d}{TY}\right)}",
        "其中:\nV_CRMW：估值日CRMW估值\nFV：标的债券到期时还本付息金额\nTY：标的债券计息年实际天数\nD：考虑CRMW创设机构风险下标的债券（标的主体）年化违约率\nd：标的债券估值日到到期日实际天数\nr_d：估值日期限d对应的基准即期收益率曲线值\nR：标的债券（标的主体）回收率",
    )],
    7: [
        (
            "估值公式如下:",
            "其中:",
            "V_CRMW = FV / [1 + y_s × (d / TY)] - FV / [1 + y_d × (d / TY)]",
            r"V_{\mathrm{CRMW}}=\frac{FV}{1+y_s\left(\frac{d}{TY}\right)}-\frac{FV}{1+y_d\left(\frac{d}{TY}\right)}",
            "其中:\nV_CRMW：估值日CRMW估值\nFV：标的债券到期时还本付息金额\nTY：标的债券计息年实际天数\nd：标的债券估值日到到期日实际天数\ny_s：被CRMW创设机构保险后的估价收益率\ny_d：标的债券的估价收益率",
        ),
        (
            "估值公式如下:",
            "其中:",
            "V_CRMW = {[(1 - exp(t_1 × ln(1 - D))) × FV × (1 - R)] / (1 + r_1)^{t_1}} + ⋯ + "
            "{[exp(t_1 × ln(1 - D)) × (1 - D)^{n-2} × D × FV × (1 - R)] / (1 + r_n)^{t_n}}",
            r"V_{\mathrm{CRMW}}=\frac{\left[1-\exp\left(t_1\ln(1-D)\right)\right]FV(1-R)}{(1+r_1)^{t_1}}+\cdots+\frac{\exp\left(t_1\ln(1-D)\right)(1-D)^{n-2}DFV(1-R)}{(1+r_n)^{t_n}}",
            "其中:\nV_CRMW：估值日CRMW估值\nFV：标的债券到期时还本付息金额\nD：考虑CRMW创设机构风险下标的债券（标的主体）年化违约率\nt_{1,2,n}：标的债券距估值日第1、2、3……n次现金流的时间长度\nr_{1,2,n}：估值日期限对应的基准即期收益率曲线值\nR：标的债券（标的主体）回收率\nn：标的债券剩余付息次数",
        ),
    ],
    8: [(
        "估值公式如下:",
        "其中:",
        "V_CRMW = [CF_1/(1+y_s)^1 + CF_2/(1+y_s)^2 + ⋯ + CF_n/(1+y_s)^n] - "
        "[CF_1/(1+y_d)^1 + CF_2/(1+y_d)^2 + ⋯ + CF_n/(1+y_d)^n]",
        r"V_{\mathrm{CRMW}}=\left[\frac{CF_1}{(1+y_s)^1}+\frac{CF_2}{(1+y_s)^2}+\cdots+\frac{CF_n}{(1+y_s)^n}\right]-\left[\frac{CF_1}{(1+y_d)^1}+\frac{CF_2}{(1+y_d)^2}+\cdots+\frac{CF_n}{(1+y_d)^n}\right]",
        "其中:\nV_CRMW：估值日CRMW估值\nCF_{1,2,n}：标的债券第1、2、……、n次现金流\nt_{1,2,n}：标的债券距估值日第1、2、……、n次现金流的时间长度\ny_s：被CRMW创设机构保险后的估价收益率\ny_d：标的债券的估价收益率\nn：标的债券剩余付息次数",
    )],
    10: [(
        "隐含违约率公式如下:",
        "其中:",
        "PV = {exp[(d/TY) × ln(1-P)] × FV + [1-exp((d/TY) × ln(1-P))] × FV × R} / "
        "[1 + r_d × (d/TY)]",
        r"PV=\frac{\exp\left(\frac{d}{TY}\ln(1-P)\right)FV+\left[1-\exp\left(\frac{d}{TY}\ln(1-P)\right)\right]FVR}{1+r_d\left(\frac{d}{TY}\right)}",
        "其中:\nPV：估值日标的债券全价\nFV：标的债券到期时还本付息金额\nTY：标的债券计息年实际天数\nP：标的债券年化隐含违约率\nd：标的债券估值日到到期日实际天数\nr_d：估值日期限d对应的基准即期收益率曲线值\nR：估值日标的债券回收率",
    )],
    11: [(
        "隐含违约率公式如下:",
        "其中:",
        "PV = {exp[t_1 × ln(1-P)] × CF_1 + [1-exp(t_1 × ln(1-P))] × CF_n × R} / (1+r_1)^{t_1} + ⋯ + "
        "{exp[t_1 × ln(1-P)] × (1-P)^{n-2} × [(1-P) × CF_n + P × CF_n × R]} / (1+r_n)^{t_n}",
        r"PV=\frac{\exp\left(t_1\ln(1-P)\right)CF_1+\left[1-\exp\left(t_1\ln(1-P)\right)\right]CF_nR}{(1+r_1)^{t_1}}+\frac{\exp\left(t_1\ln(1-P)\right)(1-P)^{n-2}\left[(1-P)CF_n+PCF_nR\right]}{(1+r_n)^{t_n}}",
        "其中:\nPV：估值日标的债券全价\nCF_{1,2,n}：标的债券第1、2、……、n次现金流\nt_{1,2,n}：标的债券距估值日第1、2、……、n次现金流的时间长度\nP：标的债券年化隐含违约率\nr_{1,2,n}：估值日期限对应的基准即期收益率曲线值\nR：估值日标的债券回收率",
    )],
}


COMPLEX_PAGE_NINE_FORMULA = (
    "V_CRMW = FV × (1-R) × ∫_{t}^{T_n} {[1/(1+r_{s-t})^{s-t}] × h × exp[-h(s-t)]} ds "
    "- 100 × C_1 × [Σ_{i=j+1}^{n} {(T_i-T_{i-1}) × [1/(1+r_{T_i-t})^{T_i-t}] × "
    "[1-exp(-h(T_i-t))]} + ∫_{t}^{T_{j+1}} {(s-T_j) × [1/(1+r_{s-t})^{s-t}] × h × "
    "exp[-h(s-t)]} ds + Σ_{k=j+1}^{n-1} ∫_{T_k}^{T_{k+1}} {(s-T_k) × "
    "[1/(1+r_{s-t})^{s-t}] × h × exp[-h(s-t)]} ds]"
)
COMPLEX_PAGE_NINE_LATEX = r"""\begin{aligned}
V_{\mathrm{CRMW}}={}&FV(1-R)\int_t^{T_n}\frac{h\exp[-h(s-t)]}{(1+r_{s-t})^{s-t}}\,ds\\
&-100C_1\Bigg[\sum_{i=j+1}^{n}(T_i-T_{i-1})\frac{1-\exp[-h(T_i-t)]}{(1+r_{T_i-t})^{T_i-t}}\\
&\quad+\int_t^{T_{j+1}}\frac{(s-T_j)h\exp[-h(s-t)]}{(1+r_{s-t})^{s-t}}\,ds\\
&\quad+\sum_{k=j+1}^{n-1}\int_{T_k}^{T_{k+1}}\frac{(s-T_k)h\exp[-h(s-t)]}{(1+r_{s-t})^{s-t}}\,ds\Bigg]
\end{aligned}"""
COMPLEX_PAGE_NINE_CONDITION = "注：T_j < t < T_{j+1}"
COMPLEX_PAGE_NINE_DEFINITIONS = (
    "其中:\nV_CRMW：估值日CRMW估值\nC_1：凭证固定支付票息（单位%）\n"
    "FV：标的债券到期时还本付息金额\nh：考虑CRMW创设机构风险下标的债券（标的主体）违约强度\n"
    "T_{1,2,n}：凭证固定票息付息日距凭证创设日的时间长度\n"
    "t：估值日距凭证创设日的时间长度\nR：标的债券（标的主体）回收率\n"
    "r_u：剩余期限u对应的基准即期收益率曲线值\nn：凭证固定票息支付次数"
)


CREDIT_DEFAULT_PROBABILITY_TEXT = (
    "考虑 CRMW 创设机构风险下标的债券(标的主体)年化违约概率 D = P(A∩B̄),定义为:\n"
    f"{FORMULA_MARKER}P(A∩B̄) = P(A|B̄) × P(B̄)\n"
    "其中:\nP(A)：标的债券年化违约概率\nP(B)=1-P(B̄)：创设机构年化违约概率\n"
    "P(A|B̄)：条件年化违约概率。\n"
    "在创设机构和标的债券发行人违约相关性w很小的情况下,P(A|B̄)可近似为P(A);"
    "在相关性w很大的情况下,P(A|B̄)可近似为0。现实中相关性一般位于0和1之间,因此可通过相关系数加权近似为:\n"
    f"{FORMULA_MARKER}P(A∩B̄) = (1-w) × P(A) × P(B̄)"
)


def _credit_valuation(blocks: list[SourceBlock]) -> int:
    changed = 0
    seen_on_page: dict[int, int] = {}
    for block in blocks:
        if "年化违约概率" in block.text and ("P AB" in block.text or "P(A" in block.text):
            block.text = CREDIT_DEFAULT_PROBABILITY_TEXT
            _set_formula_data(
                block,
                ["P(A∩B̄) = P(A|B̄) × P(B̄)", "P(A∩B̄) = (1-w) × P(A) × P(B̄)"],
                [r"P(A\cap\bar{B})=P(A\mid\bar{B})P(\bar{B})", r"P(A\cap\bar{B})=(1-w)P(A)P(\bar{B})"],
            )
            changed += 1
            continue
        if (
            block.text.startswith("T 1 V =")
            or "∫_{t}^{T_n}" in block.text
            or (block.page in {8, 9, 10} and "V = FV" in block.text and "T 1" in block.text)
        ):
            block.text = f"{FORMULA_MARKER}{COMPLEX_PAGE_NINE_FORMULA}\n{COMPLEX_PAGE_NINE_CONDITION}\n{COMPLEX_PAGE_NINE_DEFINITIONS}"
            _set_formula_data(block, [COMPLEX_PAGE_NINE_FORMULA], [COMPLEX_PAGE_NINE_LATEX])
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
        start, end, formula, latex, definitions = candidates[occurrence]
        updated = _replace_between(block.text, start, end, formula, definitions)
        seen_on_page[block.page] = occurrence + 1
        if updated != block.text:
            block.text = updated
            _set_formula_data(block, [formula], [latex])
            changed += 1
    return changed


def apply_verified_formula_overrides(path: Path, blocks: list[SourceBlock]) -> int:
    """Preserve verified formula order while retaining the original files."""
    if path.name == RATE_DEFINITION_FILE:
        return _rate_definition(blocks)
    if path.name == CREDIT_VALUATION_FILE:
        return _credit_valuation(blocks)
    return 0
