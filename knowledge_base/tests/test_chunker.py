from pathlib import Path
import sys
import unittest

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAM_ROOT))

import config
from chunkers.recursive import chunk_document
from models import ParsedDocument, SourceBlock


def document(texts: list[str]) -> ParsedDocument:
    blocks = [SourceBlock(text, block_id=f"b{index:03d}") for index, text in enumerate(texts, start=1)]
    return ParsedDocument(Path("sample.docx"), "docx", blocks, {"document_title": "测试管理办法"})


class ChunkerTests(unittest.TestCase):
    def setUp(self) -> None:
        config.ENABLE_LLM_SEMANTIC_REVIEW = False

    def test_short_chapter_kept_whole(self):
        doc = document(["第一章 总则", "第一条 为了规范业务，制定本办法。", "第二条 本办法适用于相关机构。"])
        chunks, rendered, _ = chunk_document(doc)
        self.assertEqual(len(chunks), 1)
        self.assertIn("第一章 总则", rendered[0]["text"])
        self.assertIn("第一条", rendered[0]["text"])

    def test_long_article_splits_on_complete_sentences(self):
        long_text = "第一条 " + "".join(f"机构应当建立第{i}项风险控制机制。" for i in range(100))
        doc = document(["第一章 风险管理", long_text])
        chunks, rendered, _ = chunk_document(doc)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(item["body"].replace("\n", "")) <= config.MAX_CHARS for item in rendered))
        self.assertTrue(all("第一条" in item["text"] for item in rendered))

    def test_section_boundary_is_preserved(self):
        texts = ["第一章 业务管理", "第一节 投资者适当性", "第一条 " + "投资者应当符合适当性要求。" * 55, "第二节 保证金", "第二条 " + "交易双方应当缴纳保证金。" * 55]
        doc = document(texts)
        chunks, _, _ = chunk_document(doc)
        sections = {chunk.hierarchy.get("section_title") for chunk in chunks}
        self.assertIn("第一节 投资者适当性", sections)
        self.assertIn("第二节 保证金", sections)

    def test_source_blocks_are_covered(self):
        doc = document(["第一章 总则", "第一条 " + "应当履行义务。" * 150])
        chunks, _, _ = chunk_document(doc)
        covered = {block_id for chunk in chunks for unit in chunk.units for block_id in unit.block_ids}
        self.assertEqual(covered, {"b001", "b002"})

    def test_unbreakable_long_field_is_marked_oversized(self):
        doc = document(["A" * 1300 + "，完成。"])
        chunks, rendered, _ = chunk_document(doc)
        oversized = [(chunk, item) for chunk, item in zip(chunks, rendered) if len(item["body"].replace("\n", "")) > config.MAX_CHARS]
        self.assertTrue(oversized)
        self.assertTrue(all(chunk.is_oversized for chunk, _ in oversized))


if __name__ == "__main__":
    unittest.main()
