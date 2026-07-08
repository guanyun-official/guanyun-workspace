"""防搬运红线闸 + 校验引擎单测。

no_source_leak 是「产出绝不含原帖原文片段」这条红线的出口把关(AGENTS.md 红线 +
lib/skill_gate)。此前零测试——红线闸没有回归护栏,改一行归一化/n-gram 就可能悄悄破防,
让搬运内容漏出到发布物料。本测试锁住其行为:
- 逐字复制原文 ≥n 连续字符被拦;
- 改写/占位化放行(n-gram 只抓逐字照搬,不误伤原创);
- 改标点/加空格不能绕过(归一化);
- skip 字段(内部情报留档)豁免;
- 嵌套 payload 全覆盖;
- 短于 n 的源不误伤(设计取舍)。
外加 required/banned_words/each_has/run 汇总。纯文本,零网络。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import skill_gate as g  # noqa: E402

# 李商隐《锦瑟》——当"爆款情报"原文用
SRC = "锦瑟无端五十弦,一弦一柱思华年。庄生晓梦迷蝴蝶,望帝春心托杜鹃。"


class TestNoSourceLeak(unittest.TestCase):
    def test_verbatim_chunk_flagged(self):
        chk = g.no_source_leak(SRC, n=10)
        ok, errs = g.run({"正文": "开头随便写点……锦瑟无端五十弦一弦一柱思华年,然后收尾"}, [chk])
        self.assertFalse(ok, "逐字照搬 ≥10 字应被拦")
        self.assertTrue(any("疑似搬运" in e for e in errs))

    def test_paraphrase_passes(self):
        chk = g.no_source_leak(SRC, n=10)
        ok, errs = g.run(
            {"正文": "这件衣服的灵感取自晚唐诗意,含蓄唯美,想讲的是时光流转与追忆之情。"}, [chk])
        self.assertTrue(ok, f"改写/原创不应被误伤: {errs}")

    def test_punctuation_whitespace_cannot_evade(self):
        chk = g.no_source_leak(SRC, n=10)
        leak = "锦瑟 无端,五十弦!一弦一柱  思华年"  # 复制原文但改标点/加空格
        ok, _ = g.run({"正文": leak}, [chk])
        self.assertFalse(ok, "改标点/空格不应能绕过防搬运(归一化后仍是原文)")

    def test_skip_field_exempt(self):
        chk = g.no_source_leak(SRC, n=10, skip=("情报来源",))
        payload = {"正文": "完全原创的改写内容", "情报来源": SRC}  # 内部留档字段允许含原文
        ok, errs = g.run(payload, [chk])
        self.assertTrue(ok, f"skip 字段不应被判搬运: {errs}")

    def test_nested_payload_covered(self):
        chk = g.no_source_leak(SRC, n=10)
        ok, _ = g.run({"blocks": [{"text": "锦瑟无端五十弦一弦一柱思华年"}]}, [chk])
        self.assertFalse(ok, "嵌套结构里的搬运也要抓到")

    def test_short_source_no_false_positive(self):
        chk = g.no_source_leak("短标题", n=10)  # 源归一化后 <10 字 → 无 n-gram
        ok, _ = g.run({"正文": "短标题正好也出现在这里"}, [chk])
        self.assertTrue(ok, "短于 n 的源不产生保护也不误伤(设计取舍)")


class TestOtherChecks(unittest.TestCase):
    def test_required(self):
        ok, errs = g.run({"a": "x", "b": ""}, [g.required(["a", "b", "c"])])
        self.assertFalse(ok)
        self.assertTrue(any("b" in e and "c" in e for e in errs))
        self.assertTrue(g.run({"a": "x"}, [g.required(["a"])])[0])

    def test_banned_words(self):
        ok, _ = g.run({"t": "最好最全国家级第一"}, [g.banned_words(["国家级", "第一"])])
        self.assertFalse(ok, "命中禁用词应拦")

    def test_banned_words_skip(self):
        ok, _ = g.run({"t": "含第一", "meta": "第一"}, [g.banned_words(["第一"], skip=("t", "meta"))])
        self.assertTrue(ok, "skip 字段里的禁用词不计")

    def test_each_has(self):
        chk = g.each_has("brand_points", ["item", "point", "source"])
        self.assertTrue(g.run({"brand_points": [{"item": "a", "point": "b", "source": "c"}]}, [chk])[0])
        self.assertFalse(g.run({"brand_points": [{"item": "a"}]}, [chk])[0], "缺子键应拦")
        self.assertFalse(g.run({"brand_points": []}, [chk])[0], "空列表应拦")

    def test_run_aggregates_multiple_checks(self):
        ok, _errs = g.run({"x": ""}, [g.required(["x"]), g.banned_words(["坏词"])])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
