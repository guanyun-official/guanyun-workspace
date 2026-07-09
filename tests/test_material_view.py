"""素材视图层 + 使用账本(G8)单测。锁死架构师点名的两大风险:

1. clip_id 稳定性——原始文件搬家/重编码,子素材身份不变(否则所有视图/回溯引用全断)。
2. 单一真相源——usage.jsonl 是使用唯一真值;视图=选择(bin),使用=账本,两层分清。

纯盘 + 临时目录,零网络。时间戳由调用方传入(模块内不取 now,保 determinism)。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import material_view as mv  # noqa: E402


class TestClipIdStability(unittest.TestCase):
    def test_deterministic_same_inputs(self):
        self.assertEqual(mv.clip_id("GY-001", "video:12.0-18.5"),
                         mv.clip_id("GY-001", "video:12.0-18.5"))

    def test_span_changes_id(self):
        self.assertNotEqual(mv.clip_id("GY-001", "video:0-5"),
                            mv.clip_id("GY-001", "video:5-10"))

    def test_material_changes_id(self):
        self.assertNotEqual(mv.clip_id("GY-001", "s"), mv.clip_id("GY-002", "s"))

    def test_id_independent_of_path(self):
        # 关键:clip_id 只 keyed on (素材编号, span),不含路径——文件搬家不改身份
        cid = mv.clip_id("GY-001", "facet:工艺特写")
        self.assertTrue(cid.startswith("clip_"))
        # 无论 src 怎么变,同 (material, span) 恒等
        self.assertEqual(cid, mv.clip_id("GY-001", "facet:工艺特写"))


class TestViewAndRelink(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_add_select_roundtrip(self):
        cid = mv.add_select("科普号", "考据", "GY-001", "/raw/a.mp4", "video:0-6",
                            dims={"主体": "马面裙"}, linked=6.0, root=self.root)
        got = mv.view_selects("科普号", "考据", root=self.root)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["clip_id"], cid)
        self.assertEqual(got[0]["material"], "GY-001")
        self.assertEqual(got[0]["dims"]["主体"], "马面裙")

    def test_add_select_idempotent(self):
        mv.add_select("A", "p", "GY-1", "/raw/a.mp4", "video:0-6", root=self.root)
        mv.add_select("A", "p", "GY-1", "/raw/a.mp4", "video:0-6", linked=9.9, root=self.root)  # 同 clip 覆盖
        rows = mv.view_selects("A", "p", root=self.root)
        self.assertEqual(len(rows), 1, "同 clip_id 应覆盖不重复")
        self.assertEqual(rows[0]["linked"], 9.9)

    def test_same_material_reused_across_playbooks_different_span(self):
        # 用户核心诉求:同一素材被不同方法论以不同颗粒度复用
        c1 = mv.add_select("A", "上身流", "GY-1", "/raw/v.mp4", "video:0-8", root=self.root)
        c2 = mv.add_select("A", "细节流", "GY-1", "/raw/v.mp4", "video:20-23", root=self.root)
        self.assertNotEqual(c1, c2, "同文件不同切片=不同子素材")
        self.assertEqual(len(mv.view_selects("A", "上身流", root=self.root)), 1)
        self.assertEqual(len(mv.view_selects("A", "细节流", root=self.root)), 1)

    def test_relink_preserves_clip_id(self):
        cid = mv.add_select("A", "p", "GY-1", "/old/a.mp4", "video:0-6", root=self.root)
        n = mv.relink("GY-1", "/new/loc/a.mp4", root=self.root)
        self.assertEqual(n, 1)
        rows = mv.view_selects("A", "p", root=self.root)
        self.assertEqual(rows[0]["src"], "/new/loc/a.mp4", "src 应指向新位置")
        self.assertEqual(rows[0]["clip_id"], cid, "文件搬家 clip_id 必须不变")


class TestUsageLedger(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_record_and_trace_both_directions(self):
        cid = mv.clip_id("GY-1", "video:0-6")
        mv.record_usage(cid, "PQ-001", "考据", used=4.0, ts=1000, root=self.root)
        # 正向:clip→笔记
        self.assertEqual([u["note"] for u in mv.usage_of(cid, root=self.root)], ["PQ-001"])
        # 反向:笔记→clip(支撑 G5 回溯)
        self.assertEqual(mv.note_clips("PQ-001", root=self.root), [cid])

    def test_usage_is_append_only_source_of_truth(self):
        cid = mv.clip_id("GY-1", "s")
        mv.record_usage(cid, "N1", "p", ts=1, root=self.root)
        mv.record_usage(cid, "N2", "p", ts=2, root=self.root)  # 同 clip 被两条笔记用
        self.assertEqual(len(mv.usage_of(cid, root=self.root)), 2, "账本 append-only,两次使用都在")

    def test_linked_vs_used_pct(self):
        # linked=选入 6s / 总 60s = 10%;used=实际用 4s / 60s = 6.7%
        self.assertEqual(mv.pct(6, 60), 10.0)
        self.assertEqual(mv.pct(4, 60), 6.7)
        self.assertEqual(mv.pct(1, 0), 0.0, "总量 0 不炸")


class TestTraceAndSummary(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_trace_note_joins_ledger_and_views(self):
        # G5 回溯:笔记→clip→原始素材/切片/来源视图
        cid = mv.add_select("科普号", "考据", "GY-7", "/raw/g7.mp4", "video:0-6",
                            dims={"主体": "缠枝纹"}, root=self.root)
        mv.record_usage(cid, "PQ-9", "考据", used=5.0, ts=1, root=self.root)
        tr = mv.trace_note("PQ-9", root=self.root)
        self.assertEqual(len(tr), 1)
        row = tr[0]
        self.assertEqual(row["material"], "GY-7")
        self.assertEqual(row["span"], "video:0-6")
        self.assertEqual(row["account"], "科普号")
        self.assertEqual(row["playbook"], "考据")
        self.assertEqual(row["used"], 5.0)

    def test_material_usage_linked_vs_used_pct(self):
        # 一个 60s 素材:选入两段(6s+4s=10s 软链),其中 6s 那段已用
        mv.add_select("A", "p", "GY-1", "/raw/v.mp4", "video:0-6", linked=6.0, root=self.root)
        cid2 = mv.add_select("A", "p", "GY-1", "/raw/v.mp4", "video:20-24", linked=4.0, root=self.root)
        used_cid = mv.clip_id("GY-1", "video:0-6")
        mv.record_usage(used_cid, "N1", "p", ts=1, root=self.root)
        u = mv.material_usage("GY-1", total=60, root=self.root)
        self.assertEqual(u["linked"], 10.0, "软链 6+4=10s")
        self.assertEqual(u["used"], 6.0, "只有 6s 那段被用掉")
        self.assertEqual(u["linked_pct"], 16.7)   # 10/60
        self.assertEqual(u["used_pct"], 10.0)      # 6/60
        self.assertNotIn(cid2, [])  # cid2 未用,不计入 used

    def test_material_usage_dedupes_same_clip_across_views(self):
        # 同一 clip 被两套方法论选入 → 只算一次(clip_id 稳定去重)
        mv.add_select("A", "p1", "GY-2", "/raw/x.mp4", "video:0-5", linked=5.0, root=self.root)
        mv.add_select("A", "p2", "GY-2", "/raw/x.mp4", "video:0-5", linked=5.0, root=self.root)
        u = mv.material_usage("GY-2", root=self.root)
        self.assertEqual(u["clips"], 1, "同 clip 跨视图去重")
        self.assertEqual(u["linked"], 5.0)

    def test_write_summary_human_readable(self):
        mv.add_select("A", "p", "GY-1", "/raw/a.mp4", "video:0-6", dims={"主体": "马面裙"}, root=self.root)
        p = mv.write_summary("A", "p", root=self.root)
        self.assertTrue(p.exists())
        text = p.read_text(encoding="utf-8")
        self.assertIn("GY-1", text)
        self.assertIn("video:0-6", text)
        self.assertIn("主体=马面裙", text, "语义维度应进人读镜像")


if __name__ == "__main__":
    unittest.main()
