import unittest

from knowledge_base.build_chunk_review_viewer import (
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
            "中国人民银行办公厅",
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
        data = public_data()
        self.assertEqual(data["summary"]["documents"], 108)
        self.assertEqual(data["summary"]["chunks"], 1221)
        self.assertEqual({document["source_type"] for document in data["documents"]}, {"DOC", "DOCX", "PDF"})
        self.assertTrue(
            any(
                document["validity_status"] != document["validity_category"]
                for document in data["documents"]
            )
        )


if __name__ == "__main__":
    unittest.main()
