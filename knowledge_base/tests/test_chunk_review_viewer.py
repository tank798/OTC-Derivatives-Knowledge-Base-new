import unittest

from knowledge_base.build_chunk_review_viewer import (
    DEFAULT_CHUNKS_PATH,
    DEFAULT_CLASSIFICATIONS_PATH,
    DEFAULT_DOCUMENTS_DIR,
    DEFAULT_TEMPLATE_PATH,
    first_issuing_authority,
    navigation_authority,
    public_data,
    validity_category,
)


class ChunkReviewViewerTests(unittest.TestCase):
    def test_joint_authority_uses_first_top_level_issuer(self):
        self.assertEqual(first_issuing_authority("中国人民银行、中国银保监会、中国证监会"), "中国人民银行")
        self.assertEqual(
            first_issuing_authority("中国人民银行办公厅（经人民银行、银保监会、证监会共同研究）"),
            "中国人民银行办公厅（经人民银行、银保监会、证监会共同研究）",
        )
        self.assertEqual(
            navigation_authority("中国人民银行办公厅（经人民银行、银保监会、证监会共同研究）"),
            "中国人民银行",
        )

    def test_historical_bank_insurance_authorities_map_to_nfra(self):
        self.assertEqual(navigation_authority("中国银保监会办公厅（历史机构）"), "国家金融监督管理总局")
        self.assertEqual(navigation_authority("中国银监会（历史机构）"), "国家金融监督管理总局")
        self.assertEqual(navigation_authority("中国保险监督管理委员会"), "国家金融监督管理总局")

    def test_validity_filter_uses_base_status_without_changing_raw_value(self):
        self.assertEqual(validity_category("现行有效（2025-05-13修正）"), "现行有效")
        self.assertEqual(validity_category("现行有效（部分条款经后续文件修改）"), "现行有效")
        self.assertEqual(validity_category("现行使用（官网仍列示）"), "现行使用（官网仍列示）")
        self.assertEqual(validity_category("已公布、尚未施行"), "已公布、尚未施行")

    def test_public_viewer_uses_actual_file_extensions_and_preserves_totals(self):
        data = public_data(DEFAULT_CHUNKS_PATH, DEFAULT_DOCUMENTS_DIR, DEFAULT_CLASSIFICATIONS_PATH)
        expected_documents = len(list(DEFAULT_DOCUMENTS_DIR.glob("*.json")))
        self.assertEqual(data["summary"]["documents"], expected_documents)
        self.assertEqual(data["summary"]["chunks"], sum(len(document["chunks"]) for document in data["documents"]))
        self.assertGreater(data["summary"]["chunks"], 0)
        self.assertEqual(data["documents"][0]["navigation_authority"], "中国证券监督管理委员会")
        self.assertIn(
            "公开募集证券投资基金投资信用衍生品指引",
            {document["document_title"] for document in data["documents"]},
        )
        self.assertTrue(all(chunk["character_count"] > 0 for document in data["documents"] for chunk in document["chunks"]))
        self.assertTrue(all(document["clean_text"] for document in data["documents"]))
        self.assertTrue(all(document["structured_blocks"] for document in data["documents"]))
        self.assertEqual({document["source_type"] for document in data["documents"]}, {"DOC", "DOCX", "PDF"})
        normalized_titles = {
            "期货公司风险管理公司业务试点指引",
            "期货公司风险管理公司标准仓单充抵场外衍生品交易保证金实施细则（试行）",
            "组合类保险资产管理产品实施细则",
            "中国银行间市场金融衍生产品交易主协议（2009年版）",
            "中国银行间市场金融衍生产品交易主协议（凭证特别版）",
            "中国银行间市场金融衍生产品交易主协议（跨境文本-2022年版）",
            "中国银行间市场金融衍生产品交易转让式履约保障文件（变动保证金-2025年版）",
            "全国银行间同业拆借中心信用风险缓释工具交易规则",
            "内地与香港利率互换市场互联互通合作清算衍生品协议（2024年版）",
        }
        normalized_documents = [
            document for document in data["documents"]
            if document["document_title"] in normalized_titles
        ]
        self.assertEqual(len(normalized_documents), len(normalized_titles))
        self.assertTrue(
            all(
                document["validity_status"] == document["validity_category"] == "现行有效"
                for document in normalized_documents
            )
        )

    def test_generated_viewer_keeps_removed_process_counts_out_of_ui(self):
        template = DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertNotIn('class="summary"', template)
        self.assertNotIn('id="authority-count"', template)
        self.assertNotIn("getElementById('authority-count')", template)
        self.assertNotIn("countText=", template)
        self.assertNotIn("显示 ${chunks.length}", template)
        self.assertNotIn("定位链接", template)
        self.assertNotIn("fullText", template)
        self.assertIn("structured_blocks", template)
        self.assertIn(".reader-nav[hidden]{display:none}", template)
        self.assertIn("requestAnimationFrame(()=>{if(resetScroll){body.scrollTop=0;}", template)


if __name__ == "__main__":
    unittest.main()
