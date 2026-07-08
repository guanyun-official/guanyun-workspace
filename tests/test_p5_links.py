"""P5:记录深链与发布包文案红线。零网络。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config
from orchestrator.engine import _package_text


class TestP5(unittest.TestCase):
    def test_record_url_shape(self):
        u = config.record_url("笔记表", "recXXX")
        self.assertIn(config.BASE_TOKEN, u)
        self.assertIn("table=tbl", u)
        self.assertIn("record=recXXX", u)
        self.assertTrue(u.startswith("https://"))

    def test_package_text_has_redline_and_link(self):
        t = _package_text({"文案草稿": "草稿", "排期编号": "PQ-9"}, "PQ-9", "https://x/rec")
        self.assertIn("AI 生成", t)   # 法规红线提示
        self.assertIn("https://x/rec", t)
        self.assertIn("发布链接", t)  # 回填指引


if __name__ == "__main__":
    unittest.main()
