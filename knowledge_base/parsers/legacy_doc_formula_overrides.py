from __future__ import annotations

from pathlib import Path

from models import SourceBlock


BANK_CAPITAL_MANAGEMENT_FILE = "商业银行资本管理办法.doc"
FORMULA_MARKER = "【公式（按原DOC二维排版线性化）】"


def _set_formula_data(block: SourceBlock, expressions: list[str], latex_expressions: list[str]) -> None:
    """Attach formulas transcribed from the original DOC layout.

    The legacy DOC text extractor drops the embedded equation objects.  The
    expressions below are therefore kept as explicit source-verified layout
    data, rather than inferred from surrounding prose.
    """

    block.formula_data = {
        "raw_text": block.text,
        "expressions": expressions,
        "latex_expressions": latex_expressions,
        "latex": latex_expressions[0] if len(latex_expressions) == 1 else "",
        "formula_label": "公式",
        "source_page": block.page,
        "conversion_status": "verified_from_original_doc_layout",
    }


def _replace_formula_lead(
    block: SourceBlock,
    expressions: list[str],
    latex_expressions: list[str],
) -> int:
    text = block.text.rstrip()
    if "计算公式为" not in text or FORMULA_MARKER in text:
        return 0
    block.text = text + "\n" + "\n".join(f"{FORMULA_MARKER}{expression}" for expression in expressions)
    _set_formula_data(block, expressions, latex_expressions)
    return 1


def apply_verified_formula_overrides(path: Path, blocks: list[SourceBlock]) -> int:
    """Restore legacy DOC equations only when verified from the original layout.

    This registry is keyed by the source document and article heading, not by
    any user question or retrieval result.  Other DOC files remain untouched.
    """

    if path.name != BANK_CAPITAL_MANAGEMENT_FILE:
        return 0

    changed = 0
    for block in blocks:
        if block.text.startswith("第十九条") and "资本充足率计算公式为" in block.text:
            changed += _replace_formula_lead(
                block,
                [
                    "资本充足率 = (总资本 - 对应资本扣除项) / 风险加权资产 × 100%",
                    "一级资本充足率 = (一级资本 - 对应资本扣除项) / 风险加权资产 × 100%",
                    "核心一级资本充足率 = (核心一级资本 - 对应资本扣除项) / 风险加权资产 × 100%",
                ],
                [
                    r"\text{资本充足率}=\frac{\text{总资本}-\text{对应资本扣除项}}{\text{风险加权资产}}\times100\%",
                    r"\text{一级资本充足率}=\frac{\text{一级资本}-\text{对应资本扣除项}}{\text{风险加权资产}}\times100\%",
                    r"\text{核心一级资本充足率}=\frac{\text{核心一级资本}-\text{对应资本扣除项}}{\text{风险加权资产}}\times100\%",
                ],
            )
        elif block.text.startswith("第二十条") and "杠杆率计算公式为" in block.text:
            changed += _replace_formula_lead(
                block,
                ["杠杆率 = (一级资本 - 一级资本扣除项) / 调整后表内外资产余额 × 100%"],
                [r"\text{杠杆率}=\frac{\text{一级资本}-\text{一级资本扣除项}}{\text{调整后表内外资产余额}}\times100\%"],
            )
        elif block.text.startswith("第一百二十条") and "计算公式为" in block.text:
            changed += _replace_formula_lead(
                block,
                ["ILM = ln(exp(1) − 1 + (LC / BIC)^{0.8})"],
                [r"ILM=\ln\left(\exp(1)-1+\left(\frac{LC}{BIC}\right)^{0.8}\right)"],
            )
    return changed
