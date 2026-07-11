"""压测/边界(#34 步骤7):不测文案质量,测『系统在压力/坏输入下——红线不破、不崩、行为确定』。

三类:
1) 红线高压:无论怎么生成/多少号,执行器绝不代勾 AI 声明、绝不越过草稿待发、绝不写生产库(draft 与 collect 两条写路径都焊死)。
2) 坏数据降级:空/None/畸形记录喂进选素材/复盘/取数,不抛未捕获异常,返回安全空/合理默认。
3) 路由确定性:同号重复生成→同 playbook/gen_skill(幂等路由),且永不自带 AI 声明。

全离线(stub/mock、零成本、不触网)。"""
from __future__ import annotations

import unittest
from unittest import mock

from orchestrator import accounts, collect, config, draft, feishu_io, metrics
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS
from orchestrator.guard import GuardError


class RedlineUnderPressure(unittest.TestCase):
    """红线高压:写路径怎么压都不破防。"""

    def test_ai_declared_never_set_for_any_account(self):
        """遍历所有号所有模式生成 → note_fields 永远不含 AI声明(人手勾,机器一个字都不碰),状态永远=草稿待发。"""
        names = accounts.load_all("观云")
        self.assertTrue(names, "一个号都没读到,声明源可能断了")
        for name in names:
            f = draft.generate_draft(name, llm_mode="stub")["note_fields"]
            self.assertNotIn(NF.AI_DECLARED, f, f"{name} 竟自带 AI声明=越过人审门")
            self.assertEqual(f[NF.STATUS], NS.DRAFT_PENDING, f"{name} 状态越过草稿待发")

    def test_draft_write_blocks_prod_base_even_with_valid_result(self):
        """哪怕生成结果完全合法,TEST_MODE 下写生产库必被闸拒(闸先抛,触不到网络)。"""
        r = draft.generate_draft("ootd号", llm_mode="stub")
        o_tok, o_mode = config.BASE_TOKEN, config.TEST_MODE
        try:
            config.BASE_TOKEN, config.TEST_MODE = config.PROD_BASE, True
            with self.assertRaises(GuardError):
                draft.create_draft_note(r)
        finally:
            config.BASE_TOKEN, config.TEST_MODE = o_tok, o_mode

    def test_collect_writeback_blocks_prod_base(self):
        """回流采集也是写路径:生产库同样被闸拒(采集前先过红线闸)。"""
        o_tok, o_mode = config.BASE_TOKEN, config.TEST_MODE
        try:
            config.BASE_TOKEN, config.TEST_MODE = config.PROD_BASE, True
            with self.assertRaises(GuardError):
                collect.collect_and_writeback(mode="stub")
        finally:
            config.BASE_TOKEN, config.TEST_MODE = o_tok, o_mode


class BadDataDegrades(unittest.TestCase):
    """坏数据降级:畸形输入不崩,返回安全值。"""

    def test_select_materials_empty_or_none_needs(self):
        for bad in ([], None):
            self.assertEqual(draft.select_materials(bad), [])  # 空需求→空,不崩

    def test_select_materials_malformed_records_skipped(self):
        """素材记录缺字段/类型怪 → 逐条跳过,不崩、不误选。"""
        garbage = [
            {"record_id": "r1", "fields": {}},                              # 全缺
            {"record_id": "r2", "fields": {"类型": None, "拍摄状态": 123}},   # None/数字
            {"record_id": "r3", "fields": {"类型": "上身视频", "拍摄状态": "待拍"}},  # 类型对但没拍
        ]
        with mock.patch.object(feishu_io, "list_records", lambda t: garbage):
            self.assertEqual(draft.select_materials(["上身视频"]), [])  # 无一命中『已拍』,空,不崩

    def test_metrics_num_eats_garbage(self):
        for g in (None, "", "-", "abc", "8.5万", "1,024", 100, "100", [], {}):
            metrics._num(g)  # 不抛即通过(健壮取数)

    def test_aggregate_empty_and_playbookless(self):
        self.assertEqual(metrics.aggregate_by_playbook([]), {})               # 空→空
        self.assertEqual(metrics.aggregate_by_playbook([{NF.LIKED: 10}]), {})  # 无 playbook 的行被跳过,不崩


class ExtremeInputs(unittest.TestCase):
    """极端输入边界(#34 步骤7 生产级压测):超长/特殊字符/空白 title_seed 与 clothes → 不崩、标题安全截断。"""

    def test_huge_title_seed_no_crash(self):
        r = draft.generate_draft("ootd号", llm_mode="stub", title_seed="观" * 8000)
        self.assertLessEqual(len(r["note_fields"][NF.TITLE]), 60)  # 标题恒截断 ≤60,不把超长塞进标题
        self.assertEqual(r["note_fields"][NF.STATUS], NS.DRAFT_PENDING)

    def test_special_chars_title_seed_no_crash(self):
        for seed in ("OOTD｜🌸风\n入\"大'明；", "<script>alert(1)</script>", "‮反转‬零宽​字符", "，。！×÷—…"):
            r = draft.generate_draft("ootd号", llm_mode="stub", title_seed=seed)
            self.assertTrue(r["note_fields"][NF.TITLE])            # 出标题不炸
            self.assertNotIn(NF.AI_DECLARED, r["note_fields"])     # 极端输入也绝不自带 AI 声明

    def test_bogus_clothes_code_not_grounded_no_crash(self):
        for bad in ("../../../etc/passwd", "GY-不存在", "🌸", "  "):
            r = draft.generate_draft("官号@巧荷·东方美学", llm_mode="stub", clothes=bad)
            self.assertFalse(r["clothes_grounded"])                # 绑不到真实衣服=未落地,不炸
            self.assertIn("严禁编造", r["prompt"])                  # 未绑→仍强制禁编造


class RoutingDeterminism(unittest.TestCase):
    """路由确定性/幂等:同号重复生成→同方法论落点,且永不自带 AI 声明。"""

    def test_same_account_same_routing(self):
        a = draft.generate_draft("ootd号", llm_mode="stub")
        b = draft.generate_draft("ootd号", llm_mode="stub")
        self.assertEqual(a["gen_skill"], b["gen_skill"])
        self.assertEqual(a["playbook_id"], b["playbook_id"])
        self.assertEqual(a["content_type"], b["content_type"])
        self.assertNotIn(NF.AI_DECLARED, a["note_fields"])
        self.assertNotIn(NF.AI_DECLARED, b["note_fields"])


if __name__ == "__main__":
    unittest.main()
