"""引擎各动作 handler 的特征化测试:锁住每个 Action 的副作用(写回/日报/告警)。

why:此前只有 route()(决定动作)和 ASSEMBLE 红线路径被测,GEN_COPY/MARK_PUBLISHED/
CLOSE_LOOP/COLLECT_METRICS/LIST_IDEA/REMIND_* 这些 handler 的实际副作用没有单测护住——
engine.run 的调度块一重构就可能静默改变行为而无人察觉。这里端到端跑 engine.run(隔离
LOCK/STATE、stub 飞书读写、捕获 alerts),把每个动作"该写什么状态/该进哪个日报清单"钉死,
作为 dispatch 表重构(M2)的安全网。零网络零成本。
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import alerts, engine, feishu_io, reminders  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402
from orchestrator.bitable import NoteStatus as NS  # noqa: E402

MS = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731
NOW = datetime.now()


def run_one(note_fields: dict, llm_mode: str = "stub", mode: str = "heartbeat"):
    """跑一轮,只喂一条笔记;返回 (summary, updates, sent)。全隔离,可重复,不抢真实 cron 锁。"""
    note = {"record_id": "recA", "fields": note_fields}
    updates, sent = [], []
    box = Path(tempfile.mkdtemp())
    with mock.patch.object(feishu_io, "list_records", lambda t: [note] if t == "笔记表" else []), \
            mock.patch.object(feishu_io, "update_record",
                              lambda t, rid, patch: updates.append((t, rid, patch))), \
            mock.patch.object(feishu_io, "log_run", lambda *_a, **_k: None), \
            mock.patch.object(engine, "LOCK_FILE", box / "t.lock"), \
            mock.patch.object(reminders, "STATE_FILE", box / "reminder_state.json"), \
            mock.patch.object(alerts, "send",
                              lambda text, *, title="观云推进器": sent.append((title, text)) or True):
        summary = engine.run(mode=mode, llm_mode=llm_mode)
    return summary, updates, sent


def only_patch(updates: list) -> dict:
    """断言恰好一次写回,返回其 fields patch。"""
    assert len(updates) == 1, f"期望恰好一次写回,实际 {len(updates)}: {updates}"
    return updates[0][2]


class TestActionHandlers(unittest.TestCase):
    def test_list_idea_collects_no_write(self):
        summary, updates, _ = run_one({NF.STATUS: NS.IDEA, NF.CODE: "PQ-IDEA"})
        self.assertIn("PQ-IDEA", summary["ideas"])
        self.assertEqual(updates, [], "列想法储备不应写回任何状态")

    def test_remind_shoot_lists_with_hint_no_write(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.NEED_SHOOT, NF.CODE: "PQ-SHOOT", NF.STORYBOARD: "汉服马面裙特写"})
        self.assertEqual(len(summary["shoot"]), 1)
        self.assertIn("PQ-SHOOT", summary["shoot"][0])
        self.assertIn("汉服马面裙特写", summary["shoot"][0], "催拍应带上要拍什么(F2)")
        self.assertEqual(updates, [], "催拍只提醒不写回")

    def test_gen_copy_writes_draft_and_declares_ai(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.NEED_COPY, NF.CODE: "PQ-COPY", NF.CONTENT_TYPE: "考据"})
        patch = only_patch(updates)
        self.assertEqual(patch[NF.STATUS], NS.DRAFT_PENDING, "生成文案后应置『草稿待发』")
        self.assertTrue(patch[NF.AI_DECLARED], "生成的稿必须置 AI 声明位")
        self.assertTrue(patch[NF.DRAFT], "文案草稿不应为空")
        self.assertIn("next_产物", summary, "生成后应给出下一步产物提示(格式感知)")

    def test_mark_published_on_backfilled_link(self):
        _, updates, _ = run_one(
            {NF.STATUS: NS.TO_PUBLISH, NF.CODE: "PQ-PUB", NF.PUBLISH_LINK: {"link": "https://xhs/x"}})
        patch = only_patch(updates)
        self.assertEqual(patch[NF.STATUS], NS.PUBLISHED, "检测到发布链接回填应置『已发』")
        self.assertIn(NF.PUBLISHED_AT, patch, "置已发应记实际发布日")

    def test_collect_metrics_recent_no_write(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.PUBLISHED, NF.CODE: "PQ-M", NF.PUBLISHED_AT: MS(NOW - timedelta(days=1))})
        self.assertIn("PQ-M", summary.get("metrics_todo", []), "近期已发应进待回流采集清单")
        self.assertEqual(updates, [], "采集阶段不改状态")

    def test_close_loop_when_metrics_window_passed(self):
        _, updates, _ = run_one(
            {NF.STATUS: NS.PUBLISHED, NF.CODE: "PQ-CL", NF.PUBLISHED_AT: MS(NOW - timedelta(days=10))})
        patch = only_patch(updates)
        self.assertEqual(patch[NF.STATUS], NS.LOOPED_BACK, "过了回流窗口应收口置『已回流』")

    def test_remind_review_when_overdue(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.DRAFT_PENDING, NF.CODE: "PQ-REV",
             "_state_changed_at": MS(NOW - timedelta(days=2))})
        self.assertEqual(len(summary["review"]), 1, "超时未审应催审")
        self.assertIn("PQ-REV", summary["review"][0])
        self.assertEqual(updates, [], "催审只提醒不写回")


if __name__ == "__main__":
    unittest.main()
