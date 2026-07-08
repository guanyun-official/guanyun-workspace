"""Account 统一定义 loader(候选C):frontmatter=strategy / 正文=画像。零网络。"""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import accounts, config

class TestAccounts(unittest.TestCase):
    def setUp(self):
        self._orig = config.WORKSPACE                 # 存原值,tearDown 还原(防污染其它测试)
        self.d = Path(tempfile.mkdtemp())
        (self.d/"brands"/"B"/"accounts").mkdir(parents=True)
        config.WORKSPACE = self.d
        (self.d/"brands"/"B"/"accounts"/"甲号.md").write_text(
            '---\n{"account":"甲号","cadence":{"posts_per_day":1}}\n---\n\n# 甲号画像\n考据向风格', encoding="utf-8")

    def tearDown(self):
        config.WORKSPACE = self._orig
    def test_splits_frontmatter_and_prose(self):
        a = accounts.load("甲号","B")
        self.assertEqual(a.strategy["cadence"]["posts_per_day"], 1)   # frontmatter
        self.assertIn("考据向风格", a.profile_text)                    # 正文
        self.assertNotIn("cadence", a.profile_text)                   # 正文不含 frontmatter
    def test_missing_returns_none(self):
        self.assertIsNone(accounts.load("不存在","B"))
    def test_load_all(self):
        self.assertIn("甲号", accounts.load_all("B"))

if __name__=="__main__": unittest.main()
