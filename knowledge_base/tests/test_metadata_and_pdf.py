from pathlib import Path
import sys
import unittest

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAM_ROOT))

from models import SourceBlock
from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from parsers.docx_parser import paragraph_xml_text, strip_word_toc
from parsers.legacy_doc_parser import _blocks_from_plain_text
from parsers.text_parser import _OfficialBodyHTML
from parsers.pdf_parser import remove_toc_entries
from utils.metadata import infer_metadata
from utils.text import clean_text, is_page_number


class MetadataAndPdfTests(unittest.TestCase):
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

    def test_official_html_footnote_marker_is_structured(self):
        parser = _OfficialBodyHTML()
        parser.feed('<div class="TRS_Editor"><p>第十七条① 正文。</p><p>①原第十七条已删除。</p></div>')
        self.assertEqual(parser.parts, ["第十七条 正文。", "修订注1：原第十七条已删除。"])


if __name__ == "__main__":
    unittest.main()
