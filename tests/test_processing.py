"""加工环骨架(processing.py):provenance 传播焊死 + gated 加工步(默认关/缺钩子=passthrough)。零网络。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, processing  # noqa: E402


class TestDeriveSource(unittest.TestCase):
    def test_all_real_stays_real(self):
        self.assertEqual(processing.derive_source(["实拍", "实拍"], used_ai_generation=False), "实拍")

    def test_any_ai_input_becomes_ai(self):
        self.assertEqual(processing.derive_source(["实拍", "AI生成"]), "AI生成")   # 任一输入AI→成片AI

    def test_used_ai_generation_becomes_ai_even_if_inputs_real(self):
        # 输入全实拍,但加工过程用了AI生成新画面 → 成片仍=AI生成(须声明)
        self.assertEqual(processing.derive_source(["实拍"], used_ai_generation=True), "AI生成")

    def test_empty_defaults_real(self):
        self.assertEqual(processing.derive_source([]), "实拍")   # 纯剪辑/拼接,像素都实拍→免声明


class TestMaybeProcess(unittest.TestCase):
    def test_off_is_passthrough_even_with_hooks(self):
        with mock.patch.object(config, "PROCESSING_ENABLED", False):
            out = processing.maybe_process(["m1", "m2"], decide=lambda *a, **k: {"加工": True},
                                           execute=lambda p: "prod")
        self.assertEqual(out, ["m1", "m2"])           # 默认关→原样返回原图

    def test_on_but_no_hooks_passthrough(self):
        with mock.patch.object(config, "PROCESSING_ENABLED", True):
            self.assertEqual(processing.maybe_process(["m1"]), ["m1"])   # 开着但没接技能→安全退回原图

    def test_on_decide_no_process_uses_raw(self):
        with mock.patch.object(config, "PROCESSING_ENABLED", True):
            out = processing.maybe_process(["m1", "m2"], decide=lambda *a, **k: {"加工": False},
                                           execute=lambda p: "prod")
        self.assertEqual(out, ["m1", "m2"])           # 技能判"不加工"→用原图

    def test_on_decide_process_returns_produced(self):
        captured = {}

        def decide(ids, **k):
            captured["ids"] = ids
            return {"加工": True, "kind": "拼图"}

        def execute(plan):
            captured["plan"] = plan
            return "SP-260713-001"

        with mock.patch.object(config, "PROCESSING_ENABLED", True):
            out = processing.maybe_process(["m1", "m2"], account="ootd号", decide=decide, execute=execute)
        # **成片排第一,原素材保留在后**(2026-07-14 改的行为,原来是"成片替换原图")。
        # 小红书第一张图就是封面 → 成片(封面/拼图)必须排第一。但**它是"补一张",不是"换掉全部"**:
        # 原来直接把 3 张上身图换成 1 张拼图,笔记就只剩一张图了 —— 那不是加工,那是删素材。
        self.assertEqual(out, ["SP-260713-001", "m1", "m2"])
        self.assertEqual(captured["ids"], ["m1", "m2"])
        self.assertEqual(captured["plan"]["kind"], "拼图")

    def test_execute_failure_is_reported_never_silent(self):
        """**执行炸了必须说话**(2026-07-14):老实现 `except Exception: return material_ids` ——
        AI 判了该加封面、执行炸了(如图像模型没开通),它**一声不吭退回原图**,人还以为封面加上了。
        "安全退回"听着稳,落实下来是个永不作声的黑洞。降级可以,装死不行。"""
        def boom(_plan):
            raise RuntimeError("图像模型未开通")

        report: list = []
        with mock.patch.object(config, "PROCESSING_ENABLED", True):
            out = processing.maybe_process(
                ["m1"], decide=lambda *a, **k: {"加工": True, "kind": "AI封面", "理由": "没有主图"},
                execute=boom, report=report)
        self.assertEqual(out, ["m1"])                       # 退回原素材(不乱挂)
        self.assertTrue(report, "执行失败了却一个字都不说 = 黑洞")
        self.assertIn("没做成", report[0])                   # 明说没做成
        self.assertIn("图像模型未开通", report[0])            # 明说为什么
        self.assertIn("没有主图", report[0])                 # 明说它本来想干嘛

    def test_no_process_says_nothing(self):
        """判"不用加工"→ **不该有任何噪音**(没事发生就别吵人;天天报"我没做什么"=下次没人看)。"""
        report: list = []
        with mock.patch.object(config, "PROCESSING_ENABLED", True):
            processing.maybe_process(["m1"], decide=lambda *a, **k: {"加工": False},
                                     execute=lambda p: "x", report=report)
        self.assertEqual(report, [])


class ExecutorsMatchWhatAICanDecide(unittest.TestCase):
    def test_every_decidable_kind_has_a_real_hand(self):
        """**AI 判得出的 kind,执行端必须真有那只手**。
        否则就是"在 decide 的 prompt 里多写一句话就当做完了" —— AI 会照着判,而执行端根本没实现,
        然后 maybe_process 报一句"kind 不支持",人一脸问号。这正是"想起来方便的逻辑"。
        这条测试是那面镜子:改 prompt 加新 kind,必须同时在 _EXECUTORS 里加实现,否则红。"""
        from orchestrator import compose
        decidable = {k for k in ("AI封面", "拼图") if k in compose._DECIDE_PROMPT}
        self.assertTrue(decidable, "prompt 里一个 kind 都没有?")
        self.assertLessEqual(decidable, set(compose._EXECUTORS),
                             f"AI 能判但没人能做:{decidable - set(compose._EXECUTORS)}")

    def test_processing_enabled_reads_config(self):
        with mock.patch.object(config, "PROCESSING_ENABLED", True):
            self.assertTrue(processing.processing_enabled())
        with mock.patch.object(config, "PROCESSING_ENABLED", False):
            self.assertFalse(processing.processing_enabled())


if __name__ == "__main__":
    unittest.main()
