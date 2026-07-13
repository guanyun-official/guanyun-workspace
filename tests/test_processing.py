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
        self.assertEqual(out, ["SP-260713-001"])      # 加工→成片id替换原图
        self.assertEqual(captured["ids"], ["m1", "m2"])
        self.assertEqual(captured["plan"]["kind"], "拼图")

    def test_processing_enabled_reads_config(self):
        with mock.patch.object(config, "PROCESSING_ENABLED", True):
            self.assertTrue(processing.processing_enabled())
        with mock.patch.object(config, "PROCESSING_ENABLED", False):
            self.assertFalse(processing.processing_enabled())


if __name__ == "__main__":
    unittest.main()
