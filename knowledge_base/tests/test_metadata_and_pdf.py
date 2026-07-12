from pathlib import Path
import sys
import unittest

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAM_ROOT))

from models import SourceBlock
from parsers.docx_parser import strip_word_toc
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

    def test_spaced_page_number_is_detected(self):
        self.assertTrue(is_page_number("— 1 0 —"))
        self.assertTrue(is_page_number("III"))

    def test_symbol_private_use_characters_are_normalized(self):
        self.assertEqual(clean_text("A\uf03dB\uf02bC\uf0b4D"), "A=B+C×D")
        self.assertNotIn("\uf03d", clean_text("A\uf03dB"))


if __name__ == "__main__":
    unittest.main()
