from pathlib import Path
import sys
import unittest

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAM_ROOT))

from utils.catalog import canonical_document_id
from config import PROJECT_ROOT, repository_path
from utils.validation import validate_outputs


def chunk(body: str, **values):
    row = {
        "chunk_id": "chunk_test",
        "document_id": "doc_test",
        "file_name": "测试办法.docx",
        "file_path": "/tmp/测试办法.docx",
        "document_title": "测试办法",
        "chunk_index": 1,
        "character_count": len("".join(body.split())),
        "is_oversized": False,
        "is_overlapping": False,
        "overlap_source_chunk_id": "",
        "article_start": "",
        "article_end": "",
        "attachment_name": "",
        "body_text": body,
        "text": "测试办法\n" + body,
    }
    row.update(values)
    return row


class IncrementalAndQualityTests(unittest.TestCase):
    def test_repository_path_is_relative_inside_project(self):
        value = repository_path(PROJECT_ROOT / "data" / "raw" / "监管文件" / "测试办法.docx")
        self.assertEqual(value, "data/raw/监管文件/测试办法.docx")

    def test_article_sequence_resets_for_new_document_part(self):
        first = chunk("第十八条 前一细则末条。", chunk_id="chunk_1", article_start="第十八条", article_end="第十八条", part_title="前一实施细则")
        second = chunk("第一条 新细则首条。", chunk_id="chunk_2", chunk_index=2, article_start="第一条", article_end="第一条", part_title="后一实施细则")
        result = validate_outputs([first, second], [{"status": "success", "chunk_count": 2, "coverage_status": "pass"}], 1200)
        self.assertFalse(any(issue["check"] == "article_order" for issue in result["issues"]))

    def test_document_id_does_not_depend_on_local_path_or_content(self):
        metadata = {"document_title": "证券公司测试办法", "document_number": "中证协发〔2026〕1号", "issuing_authority": "中国证券业协会", "version": ""}
        left = canonical_document_id(metadata, Path("/tmp/a.docx"))
        right = canonical_document_id(metadata, Path("/another/location/b.pdf"))
        self.assertEqual(left, right)

    def test_toc_residue_blocks_validation(self):
        row = chunk("目录\n第一章 总则........1\n第二章 业务........3")
        result = validate_outputs([row], [{"status": "success", "chunk_count": 1, "coverage_status": "pass"}], 1200)
        self.assertFalse(result["passed"])
        self.assertTrue(any(issue["check"] == "table_of_contents_residue" for issue in result["issues"]))

    def test_heading_only_chunk_blocks_validation(self):
        row = chunk("第一章 总则")
        result = validate_outputs([row], [{"status": "success", "chunk_count": 1, "coverage_status": "pass"}], 1200)
        self.assertFalse(result["passed"])
        self.assertTrue(any(issue["check"] == "heading_only_chunk" for issue in result["issues"]))

    def test_short_complete_article_is_only_minor(self):
        row = chunk("第一条 本办法自发布之日起施行。", article_start="第一条", article_end="第一条")
        result = validate_outputs([row], [{"status": "success", "chunk_count": 1, "coverage_status": "pass"}], 1200)
        self.assertTrue(result["passed"])

    def test_semicolon_boundary_is_closed_by_following_overlap(self):
        first = chunk(
            "第五条 下列情形包括：(一)第一项；",
            chunk_id="chunk_1", article_start="第五条", article_end="第五条",
        )
        second = chunk(
            "第五条 下列情形包括：(一)第一项；(二)第二项。",
            chunk_id="chunk_2", chunk_index=2, article_start="第五条", article_end="第五条",
            is_overlapping=True, overlap_source_chunk_id="chunk_1",
        )
        result = validate_outputs([first, second], [{"status": "success", "chunk_count": 2, "coverage_status": "pass"}], 1200)
        self.assertFalse(any(issue["check"] == "possible_split_enumeration" for issue in result["issues"]))

    def test_grouped_article_ranges_do_not_look_like_missing_articles(self):
        rows = []
        for index, (start, end) in enumerate(((1, 11), (12, 16), (17, 25), (26, 40), (41, 60), (61, 80), (81, 100), (101, 120), (121, 140), (141, 154)), start=1):
            row = chunk(f"第{start}条至第{end}条的完整正文。", chunk_id=f"chunk_{index}", chunk_index=index)
            number_names = {1: "第一条", 11: "第十一条", 12: "第十二条", 16: "第十六条", 17: "第十七条", 25: "第二十五条", 26: "第二十六条", 40: "第四十条", 41: "第四十一条", 60: "第六十条", 61: "第六十一条", 80: "第八十条", 81: "第八十一条", 100: "第一百条", 101: "第一百零一条", 120: "第一百二十条", 121: "第一百二十一条", 140: "第一百四十条", 141: "第一百四十一条", 154: "第一百五十四条"}
            row["article_start"] = number_names[start]
            row["article_end"] = number_names[end]
            rows.append(row)
        result = validate_outputs(rows, [{"status": "success", "chunk_count": len(rows), "coverage_status": "pass"}], 1200)
        self.assertFalse(any(issue["check"] == "article_sequence_gap" for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
