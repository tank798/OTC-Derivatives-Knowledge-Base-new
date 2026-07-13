from pathlib import Path
import sys
import unittest

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAM_ROOT))

import config
from chunkers.recursive import chunk_document
from chunkers.structure import build_tree
from chunkers.recursive import apply_structural_overlap, coalesce_structural_units, combine_units, split_node
from models import ChunkDraft, Unit
from models import ParsedDocument, SourceBlock


def document(texts: list[str]) -> ParsedDocument:
    blocks = [SourceBlock(text, block_id=f"b{index:03d}") for index, text in enumerate(texts, start=1)]
    return ParsedDocument(Path("sample.docx"), "docx", blocks, {"document_title": "测试管理办法"})


class ChunkerTests(unittest.TestCase):
    def setUp(self) -> None:
        config.ENABLE_LLM_SEMANTIC_REVIEW = False

    def test_decimal_term_number_stays_on_one_line(self):
        doc = document([
            "第一条 通用定义",
            "1.1 权益类衍生品交易",
            "指交易双方约定的权益类衍生品交易。",
        ])
        _, rendered, _ = chunk_document(doc)
        body = "\n".join(item["body"] for item in rendered)
        self.assertIn("1.1 权益类衍生品交易", body)
        self.assertNotIn("1.\n1 权益类衍生品交易", body)

    def test_list_markers_and_titles_stay_on_the_same_line(self):
        doc = document([
            "一、一般风险事项",
            "(一) 提示客户应当充分了解风险。",
            "(二) 提示客户应当了解业务规则。",
        ])
        _, rendered, _ = chunk_document(doc)
        body = "\n".join(item["body"] for item in rendered)
        self.assertIn("一、一般风险事项", body)
        self.assertIn("(一)提示客户", body)
        self.assertNotIn("一、\n一般风险事项", body)
        self.assertNotIn("(一)\n提示客户", body)

    def test_markdown_table_keeps_rows_and_does_not_add_duplicate_label(self):
        doc = ParsedDocument(
            Path("表格.pdf"), "pdf",
            [SourceBlock("| 项目 | 比例 |\n| --- | --- |\n| 净资本 | 100% |", source_kind="table", block_id="b1")],
            {"document_title": "表格附件"},
        )
        _, rendered, _ = chunk_document(doc)
        self.assertIn("| 净资本 | 100% |", rendered[0]["body"])
        self.assertFalse(rendered[0]["body"].startswith("表格\n"))

    def test_front_declaration_is_separate_from_first_article(self):
        doc = document([
            "声明",
            "本定义文件旨在提供术语释义。" * 20,
            "第一条 通用定义",
            "1.1 权益类衍生品交易",
            "指交易双方约定的交易。",
        ])
        _, rendered, _ = chunk_document(doc)
        self.assertGreaterEqual(len(rendered), 2)
        declaration = next(item["body"] for item in rendered if "声明" in item["body"])
        article = next(item["body"] for item in rendered if "第一条" in item["body"])
        self.assertNotIn("第一条", declaration)
        self.assertNotIn("声明", article)

    def test_split_cover_title_is_absorbed_into_declaration_trace(self):
        doc = ParsedDocument(
            Path("商品定义.doc"),
            "doc",
            [
                SourceBlock("商品衍生品定义文件", block_id="b1"),
                SourceBlock("(2015年版)", block_id="b2"),
                SourceBlock("声 明", block_id="b3"),
                SourceBlock("本文件提供商品衍生品术语释义。" * 20, block_id="b4"),
                SourceBlock("第一条 通用定义", block_id="b5"),
                SourceBlock("1.1商品衍生品交易", block_id="b6"),
                SourceBlock("指交易双方约定的交易。", block_id="b7"),
            ],
            {"document_title": "商品衍生品定义文件(2015年版)"},
        )
        chunks, rendered, _ = chunk_document(doc)
        self.assertFalse(any(item["body"].startswith("商品衍生品定义文件") for item in rendered))
        declaration_index = next(index for index, item in enumerate(rendered) if item["body"].startswith("声明"))
        self.assertTrue({"b1", "b2", "b3", "b4"}.issubset(set(chunks[declaration_index].units[0].block_ids)))

    def test_standalone_subdocument_title_resets_article_sequence(self):
        doc = ParsedDocument(
            Path("三个细则.docx"),
            "docx",
            [
                SourceBlock("组合类保险资产管理产品实施细则", block_id="b1"),
                SourceBlock("第十八条 前一细则最后一条。", block_id="b2"),
                SourceBlock("债权投资计划实施细则", block_id="b3"),
                SourceBlock("第一条 新细则第一条。", block_id="b4"),
            ],
            {"document_title": "三个细则"},
        )
        tree = build_tree(doc)
        parts = [node for node in tree.children if node.kind == "part"]
        self.assertEqual([part.title for part in parts], ["组合类保险资产管理产品实施细则", "债权投资计划实施细则"])
        self.assertEqual([child.title for child in parts[1].children if child.kind == "article"], ["第一条"])

    def test_split_numbered_list_carries_enumeration_context(self):
        previous_unit = Unit(
            "未付款项包括以下款项:\n1、第一项内容;", "text", {},
            article_start="第二十五条", article_end="第二十五条", sequence_index=1,
        )
        current_unit = Unit(
            "2、第二项内容。", "text", {},
            article_start="第二十五条", article_end="第二十五条", sequence_index=2,
        )
        chunks = [ChunkDraft([previous_unit], {}), ChunkDraft([current_unit], {})]
        apply_structural_overlap(chunks)
        self.assertTrue(chunks[1].is_overlapping)
        self.assertIn("未付款项包括以下款项", chunks[1].units[0].body_text)

    def test_embedded_special_terms_heading_resets_article_tree(self):
        doc = ParsedDocument(
            Path("特别版.pdf"), "pdf",
            [
                SourceBlock("第二十五条 通用定义。", block_id="b1"),
                SourceBlock("交易主协议信用风险缓释凭证特别条款本特别条款的一项定义与通用条款相同。", block_id="b2"),
                SourceBlock("第一条 本主协议的构成", block_id="b3"),
                SourceBlock("第二条 本主协议的适用", block_id="b4"),
            ],
            {"document_title": "特别版"},
        )
        tree = build_tree(doc)
        part = next(node for node in tree.children if node.kind == "part")
        self.assertIn("特别条款", part.title)
        self.assertEqual([child.title for child in part.children if child.kind == "article"], ["第一条", "第二条"])

    def test_exact_supplement_heading_starts_new_part(self):
        doc = ParsedDocument(
            Path("主协议.doc"), "doc",
            [
                SourceBlock("第十四条 定义。", block_id="b1"),
                SourceBlock("补充协议", block_id="b2"),
                SourceBlock("主协议补充协议", block_id="b3"),
                SourceBlock("第一条 违约和终止条款", block_id="b4"),
            ],
            {"document_title": "主协议"},
        )
        tree = build_tree(doc)
        self.assertTrue(any(node.kind == "part" and any(child.title == "第一条" for child in node.children) for node in tree.children))

    def test_new_part_cannot_merge_with_previous_article(self):
        previous = Unit("第二十五条 前文。", "article", {"part_title": ""}, article_start="第二十五条", article_end="第二十五条")
        special = Unit("第一条 特别条款。", "article", {"part_title": "信用风险缓释凭证特别条款"}, article_start="第一条", article_end="第一条")
        chunks = combine_units([previous, special])
        self.assertEqual(len(chunks), 2)

    def test_part_own_text_does_not_claim_all_descendant_articles(self):
        doc = ParsedDocument(
            Path("特别版.pdf"), "pdf",
            [
                SourceBlock("交易主协议特别条款本特别条款适用于以下交易。", block_id="b1"),
                SourceBlock("第一条 第一条正文。", block_id="b2"),
                SourceBlock("第二条 " + "第二条正文。" * 200, block_id="b3"),
            ],
            {"document_title": "特别版"},
        )
        part = next(node for node in build_tree(doc).children if node.kind == "part")
        units = split_node(part)
        self.assertEqual(units[0].kind, "part")
        self.assertEqual(units[0].article_start, "")
        self.assertEqual(units[0].article_end, "")

    def test_attachment_heading_merges_forward_with_body(self):
        heading = Unit("附件1", "attachment", {"attachment_name": "附件1"}, attachment_name="附件1")
        body = Unit("第一条 附件正文。", "article", {"attachment_name": "附件1"}, article_start="第一条", article_end="第一条", attachment_name="附件1")
        chunks = combine_units([heading, body])
        self.assertEqual(len(chunks), 1)
        self.assertEqual([unit.kind for unit in chunks[0].units], ["attachment", "article"])

    def test_attachment_is_parent_of_following_chapter(self):
        doc = ParsedDocument(
            Path("附件法规.pdf"), "pdf",
            [SourceBlock("附件:测试办法", block_id="b1"), SourceBlock("第一章 总则", block_id="b2"), SourceBlock("第一条 正文。", block_id="b3")],
            {"document_title": "测试办法"},
        )
        attachment = next(node for node in build_tree(doc).children if node.kind == "attachment")
        self.assertTrue(any(child.kind == "chapter" for child in attachment.children))

    def test_document_title_unit_is_coalesced_into_context(self):
        doc = ParsedDocument(Path("测试办法.docx"), "docx", [], {"document_title": "测试办法"})
        title = Unit("测试办法", "text", {}, block_ids=["b1"])
        body = Unit("正文内容。" * 60, "text", {}, block_ids=["b2"])
        units = coalesce_structural_units(doc, [title, body])
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].block_ids, ["b1", "b2"])

    def test_long_enumeration_uses_context_only_overlap(self):
        previous = Unit("未付款项包括以下款项:\n1、" + "甲" * 1000 + ";", "text", {}, article_start="第二十五条", sequence_index=1)
        current = Unit("2、" + "乙" * 1195 + "。", "text", {}, article_start="第二十五条", sequence_index=2)
        chunks = [ChunkDraft([previous], {}), ChunkDraft([current], {})]
        apply_structural_overlap(chunks)
        self.assertTrue(chunks[1].is_overlapping)
        self.assertIn("未付款项包括以下款项", chunks[1].context_only_prefix)

    def test_numbered_list_without_article_metadata_gets_parent_context(self):
        previous = Unit(
            "1.\n1 信用衍生产品交易【基本术语】定义正文。【适用规则】\n(1) 第一项。",
            "text", {}, sequence_index=1,
        )
        current = Unit("(2) 第二项。", "item", {}, sequence_index=2)
        chunks = [ChunkDraft([previous], {}), ChunkDraft([current], {})]
        apply_structural_overlap(chunks)
        self.assertTrue(chunks[1].is_overlapping)
        self.assertEqual(chunks[1].overlap_source_index, 0)
        self.assertIn("信用衍生产品交易", chunks[1].context_only_prefix)

    def test_mid_sentence_continuation_gets_overlap(self):
        previous = Unit("不可抗力指不能预见、不能避免且不能克服的客观情况,", "article", {}, article_start="第二十五条", sequence_index=1)
        current = Unit("包括但不限于自然灾害和通信瘫痪。", "text", {}, article_start="第二十五条", sequence_index=2)
        chunks = [ChunkDraft([previous], {}), ChunkDraft([current], {})]
        apply_structural_overlap(chunks)
        self.assertTrue(chunks[1].is_overlapping)
        self.assertIn("不可抗力", chunks[1].context_only_prefix)

    def test_repeated_tail_item_overlap_still_carries_parent_definition(self):
        previous = Unit("2.\n2 债务【基本术语】债务的定义。【适用规则】\n(1) 第一项。\n(2) 第二项。", "text", {}, sequence_index=1)
        current = Unit("(2) 第二项。\n(1) 下一组第一项。", "item", {}, sequence_index=2)
        chunks = [ChunkDraft([previous], {}), ChunkDraft([current], {})]
        apply_structural_overlap(chunks)
        self.assertTrue(chunks[1].is_overlapping)
        self.assertIn("债务", chunks[1].context_only_prefix)

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
