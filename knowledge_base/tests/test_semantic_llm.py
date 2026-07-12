from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAM_ROOT))

import config
from chunkers.semantic_llm import review_boundaries
from models import Unit


class SemanticReviewTests(unittest.TestCase):
    def test_json_boundary_response_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            key_path = temp_path / "key.txt"
            key_path.write_text("test-key", encoding="utf-8")
            cache_path = temp_path / "cache.json"
            units = [
                Unit("第一条 定义。", "article", {}, sequence_index=0),
                Unit("第二条 适用范围。", "article", {}, sequence_index=1),
                Unit("第三条 风险控制。", "article", {}, sequence_index=2),
            ]
            old_key = config.DEEPSEEK_API_KEY_FILE
            old_enabled = config.ENABLE_LLM_SEMANTIC_REVIEW
            config.DEEPSEEK_API_KEY_FILE = key_path
            config.ENABLE_LLM_SEMANTIC_REVIEW = True
            try:
                with patch("chunkers.semantic_llm._request", return_value='{"break_before":[2],"overlap_before":[1],"reason":"test"}') as request:
                    breaks, overlaps, warnings = review_boundaries("测试办法", units, cache_path)
                    self.assertEqual(breaks, {2})
                    self.assertEqual(overlaps, {1})
                    self.assertEqual(warnings, [])
                    self.assertEqual(request.call_count, 1)
                with patch("chunkers.semantic_llm._request") as request:
                    review_boundaries("测试办法", units, cache_path)
                    self.assertEqual(request.call_count, 0)
            finally:
                config.DEEPSEEK_API_KEY_FILE = old_key
                config.ENABLE_LLM_SEMANTIC_REVIEW = old_enabled


if __name__ == "__main__":
    unittest.main()
