import json
import re
import unittest
from pathlib import Path

from scripts.build_legacy_style_viewer import DEFAULT_OUTPUT, VIEWER_DATA_PATTERN


class PersonalWorkspaceViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html_path = Path(DEFAULT_OUTPUT)
        cls.html = cls.html_path.read_text(encoding="utf-8")
        script_start = cls.html.rfind("<script>") + len("<script>")
        script_end = cls.html.find("</script>", script_start)
        cls.javascript = cls.html[script_start:script_end]

    def test_filter_keeps_authority_and_favorite_only(self):
        match = re.search(r"const DIMENSIONS=\[(.*?)\];", self.javascript, re.DOTALL)
        self.assertIsNotNone(match)
        dimensions = match.group(1)
        self.assertIn("label:'发文主体'", dimensions)
        self.assertIn("label:'收藏'", dimensions)
        self.assertNotIn("label:'交易场所'", dimensions)
        self.assertNotIn("label:'客户主体'", dimensions)

    def test_regulation_cards_do_not_render_classification_tags(self):
        self.assertNotIn('class="classification-tags"', self.html)
        self.assertNotIn('class="classification-tag"', self.html)
        self.assertNotIn("function compactTags", self.javascript)
        self.assertNotIn("function cardTags", self.javascript)

    def test_regulation_list_uses_eight_items_per_page(self):
        self.assertIn("pageSize:8", self.javascript)
        self.assertNotIn("pageSize:7", self.javascript)

    def test_word_workspace_contract_is_present(self):
        for token in (
            'id="reader-document" contenteditable="true"',
            'id="editor-toolbar"',
            "function addCommentFromSelection",
            "function saveCurrentDocument",
            "function beginDrawing",
            "e.key.toLowerCase()==='s'",
        ):
            self.assertIn(token, self.html)
        self.assertNotIn("仅保存在当前浏览器，可通过导出文件备份", self.html)

    def test_personal_workspace_seed_is_valid(self):
        match = re.search(
            r'<script type="application/json" id="personal-workspace-seed">(.*?)</script>',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(json.loads(match.group(1))["version"], 2)

    def test_rebuild_can_replace_data_without_replacing_shell(self):
        matches = list(VIEWER_DATA_PATTERN.finditer(self.html))
        self.assertEqual(len(matches), 1)
        shell = VIEWER_DATA_PATTERN.sub(
            lambda item: f'{item.group(1)}{{{{VIEWER_DATA_JSON}}}}{item.group(2)}',
            self.html,
            count=1,
        )
        self.assertEqual(shell.count("{{VIEWER_DATA_JSON}}"), 1)
        self.assertIn("personal-workspace-seed", shell)
        self.assertIn("function addCommentFromSelection", shell)


if __name__ == "__main__":
    unittest.main()
