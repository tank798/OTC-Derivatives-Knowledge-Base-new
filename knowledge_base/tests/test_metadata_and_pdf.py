from pathlib import Path
import sys
import unittest

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAM_ROOT))

from models import SourceBlock
from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from parsers.docx_parser import paragraph_xml_text, strip_front_page_metadata, strip_word_toc
from parsers.legacy_doc_parser import _blocks_from_plain_text
from parsers.text_parser import _OfficialBodyHTML
from parsers.pdf_parser import merge_cross_page_paragraphs, normalize_pdf_table_cell, normalize_semantic_table, remove_toc_entries, split_semantic_table_content
from parsers.pdf_formula_overrides import apply_verified_formula_overrides
from utils.metadata import infer_metadata
from utils.text import clean_text, is_page_number


class MetadataAndPdfTests(unittest.TestCase):
    def test_front_page_timestamp_is_removed_but_article_date_is_kept(self):
        blocks = [
            SourceBlock("测试定义文件", block_id="b1"),
            SourceBlock("时间:2014-08-22", block_id="b2"),
            SourceBlock("声明", block_id="b3"),
            SourceBlock("第一条 自2026-11-16起施行。", block_id="b4"),
        ]
        filtered, removed = strip_front_page_metadata(blocks)
        self.assertEqual(removed, 1)
        self.assertEqual([block.block_id for block in filtered], ["b1", "b3", "b4"])

    def test_quoted_legal_basis_is_not_document_title(self):
        blocks = [SourceBlock("第一条 根据《中华人民共和国证券法》制定本办法。", block_id="b1")]
        metadata = infer_metadata(blocks, Path("证券公司操作风险管理指引.docx"))
        self.assertEqual(metadata["document_title"], "证券公司操作风险管理指引")
        self.assertEqual(metadata["document_title_source"], "filename")

    def test_source_prefix_is_removed_from_filename_title(self):
        metadata = infer_metadata([], Path("19_GFEX_广州期货交易所_广州期货交易所碳酸锂期货、期权业务细则.docx"))
        self.assertEqual(metadata["document_title"], "广州期货交易所碳酸锂期货、期权业务细则")

    def test_toc_entries_are_removed_as_a_group(self):
        lines = ["目 录", "第一章 总则 1", "第二章 证券发行 2", "第三章 证券交易 7", "中华人民共和国证券法"]
        filtered, removed = remove_toc_entries(lines)
        self.assertEqual(removed, 4)
        self.assertEqual(filtered, ["中华人民共和国证券法"])

    def test_non_chapter_toc_entries_are_removed(self):
        lines = ["目录", "一、总则 ................................................................ 2", "二、估值处理 ........ 3", "三、会计处理 ........ 4", "正文"]
        filtered, removed = remove_toc_entries(lines)
        self.assertEqual(removed, 4)
        self.assertEqual(filtered, ["正文"])

    def test_cross_page_sentence_and_word_are_joined(self):
        blocks = [
            SourceBlock("第五条 并至少每", page=1, block_id="b1"),
            SourceBlock("季度将管理情况书面报告。", page=2, block_id="b2"),
            SourceBlock("第六条 新条文。", page=2, block_id="b3"),
        ]
        merged, count = merge_cross_page_paragraphs(blocks)
        self.assertEqual(count, 1)
        self.assertEqual(merged[0].text, "第五条 并至少每季度将管理情况书面报告。")
        self.assertEqual(merged[1].text, "第六条 新条文。")

    def test_cross_page_numeric_continuation_is_not_mistaken_for_heading(self):
        blocks = [
            SourceBlock("家庭金融资产不低于", page=1, block_id="b1"),
            SourceBlock("500 万元,或者近 3 年本人年均收入不低于 40 万元;", page=2, block_id="b2"),
        ]
        merged, count = merge_cross_page_paragraphs(blocks)
        self.assertEqual(count, 1)
        self.assertIn("不低于500 万元", merged[0].text)

    def test_cross_page_join_stops_at_new_legal_structure(self):
        blocks = [
            SourceBlock("前一页末尾无句号", page=1, block_id="b1"),
            SourceBlock("（二）新的分项。", page=2, block_id="b2"),
        ]
        merged, count = merge_cross_page_paragraphs(blocks)
        self.assertEqual(count, 0)
        self.assertEqual(len(merged), 2)

    def test_pdf_semantic_table_requires_two_nonempty_columns(self):
        note_box = [["", "注：这是一行说明", ""], ["", "继续说明", ""]]
        self.assertEqual(normalize_semantic_table(note_box), [])
        table = [["项目", "", "比例"], ["净资本", "", "100%"]]
        self.assertEqual(normalize_semantic_table(table), [["项目", "比例"], ["净资本", "100%"]])

    def test_pdf_table_cell_visual_wraps_are_collapsed(self):
        self.assertEqual(normalize_pdf_table_cell("债\n券、票据"), "债券、票据")
        self.assertEqual(normalize_pdf_table_cell("Net-to-\nGross Ratio"), "Net-to-Gross Ratio")
        self.assertEqual(normalize_pdf_table_cell("未来 30\n日现金流出"), "未来 30日现金流出")

    def test_semantic_table_separates_note_rows_and_preserves_order(self):
        rows = [
            ["注：这是表格前的较长说明文字，不应被当作表格单元格。", "", ""],
            ["说明的续行内容。", "", ""],
            ["受让方风险敞口", "=", "市场价值"],
            ["数值", "+", "独立金额"],
            ["由此可见，后续的较长解释文字也不是表格的数据行。", "", ""],
        ]
        segments = split_semantic_table_content(rows)
        self.assertEqual([kind for kind, _ in segments], ["text", "table", "text"])
        self.assertIn("说明的续行内容", segments[0][1])
        self.assertEqual(len(segments[1][1]), 2)
        self.assertIn("后续的较长解释", segments[2][1])

    def test_word_toc_is_removed_before_repeated_first_chapter(self):
        blocks = [
            SourceBlock("目录", block_id="b1"),
            SourceBlock("第一章 总则", block_id="b2"),
            SourceBlock("第二章 业务", block_id="b3"),
            SourceBlock("第一章 总则", block_id="b4"),
            SourceBlock("第一条 正文。", block_id="b5"),
        ]
        filtered, removed = strip_word_toc(blocks)
        self.assertEqual(removed, 3)
        self.assertEqual([block.block_id for block in filtered], ["b4", "b5"])

    def test_styled_word_toc_does_not_delete_chapter_based_guide_body(self):
        blocks = [
            SourceBlock("附件", style="Normal", block_id="b1"),
            SourceBlock("目录", style="Normal", block_id="b2"),
            SourceBlock("第一章 总体要求 1", style="toc 1", block_id="b3"),
            SourceBlock("一、概述 1", style="toc 2", block_id="b4"),
            SourceBlock("说明及声明", style="List Paragraph", block_id="b5"),
            SourceBlock("为便于做市商开展业务，制定本指南。", style="Normal", block_id="b6"),
            SourceBlock("第一章 总体要求", style="List Paragraph", block_id="b7"),
            SourceBlock("一、概述", style="Heading 2", block_id="b8"),
            SourceBlock("本所采用竞争性做市商制度。", style="Normal", block_id="b9"),
            SourceBlock("附件4：做市协议", style="Normal", block_id="b10"),
            SourceBlock("第二条 协议正文。", style="Normal", block_id="b11"),
        ]
        filtered, removed = strip_word_toc(blocks)
        self.assertEqual(removed, 3)
        self.assertEqual([block.block_id for block in filtered], ["b1", "b5", "b6", "b7", "b8", "b9", "b10", "b11"])

    def test_spaced_page_number_is_detected(self):
        self.assertTrue(is_page_number("— 1 0 —"))
        self.assertTrue(is_page_number("III"))

    def test_symbol_private_use_characters_are_normalized(self):
        self.assertEqual(clean_text("A\uf03dB\uf02bC\uf0b4D"), "A=B+C×D")
        self.assertNotIn("\uf03d", clean_text("A\uf03dB"))

    def test_wrapped_decimal_is_repaired_without_joining_list_items(self):
        self.assertEqual(clean_text("1.\n1 权益类衍生品交易"), "1.1 权益类衍生品交易")
        self.assertEqual(clean_text("5.\n625%—6.25%"), "5.625%—6.25%")
        self.assertEqual(clean_text("7.\n2.1交易条款"), "7.2.1交易条款")
        self.assertEqual(clean_text("1.\n2. 第二项"), "1.\n2. 第二项")

    def test_docx_smart_tag_text_is_not_dropped(self):
        document = Document()
        paragraph = document.add_paragraph("Shibor O/N:")
        smart_tag = OxmlElement("w:smartTag")
        run = OxmlElement("w:r")
        text = OxmlElement("w:t")
        text.text = "1M、3M、6M、9M、1Y"
        run.append(text)
        smart_tag.append(run)
        paragraph._p.append(smart_tag)
        wrapped = Paragraph(paragraph._p, paragraph._parent)
        self.assertEqual(paragraph_xml_text(wrapped), "Shibor O/N:1M、3M、6M、9M、1Y")

    def test_legacy_doc_toc_cleanup_keeps_body_articles(self):
        text = """测试定义文件\n目录\n第一条 通用定义 1\n第二条 日期定义 2\n第一条 通用定义\n正文\n第二条 日期定义\n正文二"""
        blocks, warnings = _blocks_from_plain_text(text)
        values = [block.text for block in blocks]
        self.assertEqual(values, ["测试定义文件", "第一条 通用定义", "正文", "第二条 日期定义", "正文二"])
        self.assertTrue(any("目录" in warning for warning in warnings))

    def test_legacy_doc_toc_cleanup_preserves_preface_before_first_article(self):
        text = """主协议\n目录\n第一条 协议构成 1\n第二条 支付义务 2\n为明确交易双方的权利和义务，双方签署本主协议。\n第一条 协议构成\n正文"""
        blocks, _ = _blocks_from_plain_text(text)
        self.assertEqual(
            [block.text for block in blocks],
            ["主协议", "为明确交易双方的权利和义务,双方签署本主协议。", "第一条 协议构成", "正文"],
        )

    def test_rate_definition_fraction_is_restored_from_verified_pdf_layout(self):
        blocks = [SourceBlock(
            "贴现因子适用如下公式:λ =1 + ( r ×N / D )其中,λ 是贴现因子。",
            page=16,
            block_id="b1",
        )]
        changed = apply_verified_formula_overrides(Path("中国银行间市场利率衍生产品交易定义文件（2022年版）.pdf"), blocks)
        self.assertEqual(changed, 1)
        self.assertIn("λ = 1 / [1 + (r × N / D)]", blocks[0].text)

    def test_credit_valuation_formula_preserves_fraction_and_exponent_order(self):
        blocks = [SourceBlock(
            "(一)基于违约率的方法估值公式如下:*ln(1-D)乱码其中:V为估值。",
            page=6,
            block_id="b1",
        )]
        changed = apply_verified_formula_overrides(Path("证券投资基金投资信用衍生品估值指引(试行).pdf"), blocks)
        self.assertEqual(changed, 1)
        self.assertIn("exp((d / TY) × ln(1 - D))", blocks[0].text)
        self.assertIn("/ [1 + r_d × (d / TY)]", blocks[0].text)

    def test_credit_default_probability_preserves_complement_event(self):
        blocks = [SourceBlock(
            "考虑 CRMW 风险下年化违约概率 D = P AB,且 P AB = P A| B ×P B。",
            page=10,
            block_id="b1",
        )]
        changed = apply_verified_formula_overrides(Path("证券投资基金投资信用衍生品估值指引(试行).pdf"), blocks)
        self.assertEqual(changed, 1)
        self.assertIn("P(A∩B̄) = P(A|B̄) × P(B̄)", blocks[0].text)

    def test_official_html_footnote_marker_is_structured(self):
        parser = _OfficialBodyHTML()
        parser.feed('<div class="TRS_Editor"><p>第十七条① 正文。</p><p>①原第十七条已删除。</p></div>')
        self.assertEqual(parser.parts, ["第十七条 正文。", "修订注1：原第十七条已删除。"])


if __name__ == "__main__":
    unittest.main()
