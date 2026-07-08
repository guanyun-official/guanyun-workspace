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

    def test_bad_frontmatter_is_visible_not_silent(self):
        """坏 JSON frontmatter 不许被静默当成'无声明':须带 error 且能被 problems() 发现。

        防的正是「一个号 {号}.md 写坏→引擎静默少排一个号,半夜无人知」这个接缝健壮性洞。
        """
        (self.d / "brands" / "B" / "accounts" / "坏号.md").write_text(
            '---\n{ 这不是合法JSON,, }\n---\n\n# 坏号画像\n随便', encoding="utf-8")
        all_ = accounts.load_all("B")
        self.assertIn("坏号", all_, "坏号被静默丢弃了(应保留并标错)")
        self.assertEqual(all_["坏号"].strategy, {}, "坏 JSON 的 strategy 应为空")
        self.assertTrue(all_["坏号"].error, "坏 frontmatter 必须带 error 标记(不许静默)")
        probs = accounts.problems("B")
        self.assertIn("坏号", probs, "problems() 应能发现解析失败的账号")
        self.assertNotIn("甲号", probs, "好账号不应出现在 problems()")

    def test_good_account_has_no_error(self):
        self.assertIsNone(accounts.load("甲号", "B").error)
        self.assertEqual(accounts.problems("B"), {})

if __name__=="__main__": unittest.main()
