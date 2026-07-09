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


class TestPlaybooks(unittest.TestCase):
    """G4 多方法论:playbooks_of 显式优先、否则从 content_mix/material_needs 向后兼容合成。"""

    def test_explicit_playbooks_win(self):
        s = {"playbooks": [{"id": "考据", "weight": 0.7, "material_needs": ["文物对照图"], "view": "考据"}]}
        pbs = accounts.playbooks_of(s)
        self.assertEqual(len(pbs), 1)
        self.assertEqual(pbs[0]["id"], "考据")
        self.assertEqual(pbs[0]["view"], "考据")

    def test_synthesized_from_legacy_content_mix(self):
        s = {"content_mix": {"文物对照": 0.6, "工艺科普": 0.4},
             "material_needs": {"文物对照": ["文物对照图"], "工艺科普": ["工艺特写"]}}
        pbs = {pb["id"]: pb for pb in accounts.playbooks_of(s)}
        self.assertEqual(set(pbs), {"文物对照", "工艺科普"}, "每个内容类型合成一个 playbook")
        self.assertEqual(pbs["文物对照"]["weight"], 0.6, "权重取自 content_mix")
        self.assertEqual(pbs["文物对照"]["material_needs"], ["文物对照图"])
        self.assertEqual(pbs["文物对照"]["view"], "文物对照", "view 键默认=内容类型 id")

    def test_synthesized_weight_defaults_even(self):
        s = {"material_needs": {"a": ["x"], "b": ["y"]}}  # 无 content_mix → 均分权重
        pbs = accounts.playbooks_of(s)
        self.assertEqual(len(pbs), 2)
        self.assertAlmostEqual(sum(pb["weight"] for pb in pbs), 1.0, places=1)

    def test_empty_strategy_no_playbooks(self):
        self.assertEqual(accounts.playbooks_of({}), [])

    def test_playbook_for_matches_content_type(self):
        s = {"playbooks": [{"id": "考据", "content_type": "文物对照", "weight": 0.6, "view": "考据"},
                           {"id": "科普", "content_type": "工艺科普", "weight": 0.4, "view": "科普"}]}
        self.assertEqual(accounts.playbook_for(s, "文物对照")["id"], "考据")
        self.assertIsNone(accounts.playbook_for(s, "不存在"), "无匹配返 None")

    def test_playbook_for_picks_highest_weight_on_collision(self):
        s = {"playbooks": [{"id": "低", "content_type": "同", "weight": 0.3, "view": "a"},
                           {"id": "高", "content_type": "同", "weight": 0.7, "view": "b"}]}
        self.assertEqual(accounts.playbook_for(s, "同")["id"], "高", "同 content_type 取最高权重")

    def test_resolve_playbook_explicit_id_wins(self):
        s = {"playbooks": [{"id": "甲", "content_type": "同", "weight": 0.3, "view": "a"},
                           {"id": "乙", "content_type": "同", "weight": 0.7, "view": "b"}]}
        # 显式指定「甲」→ 用甲(消歧义),即便乙权重更高
        self.assertEqual(accounts.resolve_playbook(s, "甲", "同")["id"], "甲")
        # 无显式 → 回退 content_type(取最高权重乙)
        self.assertEqual(accounts.resolve_playbook(s, "", "同")["id"], "乙")


class TestPlaybookValidation(unittest.TestCase):
    """评审 finding#4:显式 playbook 声明坏了不许静默(权重不归一/view 冲突/缺 id)。"""

    def test_valid_explicit_ok(self):
        s = {"playbooks": [{"id": "a", "weight": 0.5, "view": "va"},
                           {"id": "b", "weight": 0.5, "view": "vb"}]}
        self.assertEqual(accounts.validate_playbooks(s), [])

    def test_weights_not_normalized_flagged(self):
        s = {"playbooks": [{"id": "a", "weight": 0.6, "view": "va"},
                           {"id": "b", "weight": 0.6, "view": "vb"}]}
        self.assertTrue(any("权重未归一" in e for e in accounts.validate_playbooks(s)))

    def test_view_collision_flagged(self):
        s = {"playbooks": [{"id": "a", "weight": 0.5, "view": "同"},
                           {"id": "b", "weight": 0.5, "view": "同"}]}
        self.assertTrue(any("view 键冲突" in e for e in accounts.validate_playbooks(s)))

    def test_missing_id_flagged(self):
        s = {"playbooks": [{"weight": 1.0, "view": "va"}]}
        self.assertTrue(any("缺 id" in e for e in accounts.validate_playbooks(s)))

    def test_synthesized_always_valid(self):
        self.assertEqual(accounts.validate_playbooks({"content_mix": {"x": 0.6, "y": 0.4}}), [])


if __name__=="__main__": unittest.main()
