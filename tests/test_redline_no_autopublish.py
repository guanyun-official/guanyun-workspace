"""红线端到端锁:未勾 AI 声明的内容,引擎巡检绝不自动组装发布包。

依据《AI 生成合成内容标识办法》(2025-09)+ 观云红线「绝不自动发布」。
runbook 已把 '已批准' → ASSEMBLE_PACKAGE;本测试验证引擎在组装前 guard.assert_ai_declared
硬闸拦截:不改状态、不进 packages、记错并告警。对照组证明硬闸精确拦「未声明」而非全拦。

端到端跑 engine.run,但隔离 LOCK_FILE / reminders.STATE_FILE、stub 飞书读写、捕获 alerts,
故零网络零成本、且不与真实 orchestrator/cron 抢锁(防 flaky)。
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import alerts, engine, feishu_io, reminders  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402


def run_heartbeat_isolated(note_fields: dict):
    """跑一轮 heartbeat,只喂一条笔记;返回 (summary, updates, sent)。全隔离,可重复。"""
    note = {"record_id": "recRL", "fields": note_fields}
    updates, sent = [], []
    box = Path(tempfile.mkdtemp())
    with mock.patch.object(feishu_io, "list_records", lambda t: [note] if t == "笔记表" else []), \
            mock.patch.object(feishu_io, "update_record",
                              lambda t, rid, patch: updates.append((rid, patch))), \
            mock.patch.object(feishu_io, "log_run", lambda *_a, **_k: None), \
            mock.patch.object(engine, "LOCK_FILE", box / "t.lock"), \
            mock.patch.object(reminders, "STATE_FILE", box / "reminder_state.json"), \
            mock.patch.object(alerts, "send",
                              lambda text, *, title="观云推进器": sent.append((title, text)) or True):
        summary = engine.run(mode="heartbeat", llm_mode="stub")
    return summary, updates, sent


class TestRedlineNoAutoPublish(unittest.TestCase):
    def test_undeclared_approved_note_is_blocked(self):
        """员工手动把未勾 AI 声明的笔记拖到『已批准』→ 引擎绝不组装发布包。"""
        summary, updates, sent = run_heartbeat_isolated(
            {NF.STATUS: "已批准", NF.CODE: "PQ-RL", NF.AI_DECLARED: False, NF.ACCOUNT: "科普号"})
        self.assertEqual(summary["packages"], [], "红线破防:未声明内容被组装进发布包")
        self.assertFalse(any(patch.get(NF.STATUS) == "待发布" for _, patch in updates),
                         "红线破防:未声明内容被置为待发布")
        self.assertTrue(any("PQ-RL" in e for e in summary["errors"]), "硬闸拒绝未记录到 errors")
        self.assertTrue(any("硬闸" in t for _, t in sent), "硬闸拒绝未告警")

    def test_declared_approved_note_assembles(self):
        """对照:勾了 AI 声明的『已批准』笔记正常组装——证明硬闸精确拦『未声明』而非全拦。"""
        summary, updates, sent = run_heartbeat_isolated(
            {NF.STATUS: "已批准", NF.CODE: "PQ-OK", NF.AI_DECLARED: True,
             NF.ACCOUNT: "科普号", "文案草稿": "稿"})
        self.assertEqual(len(summary["packages"]), 1, "已声明的已批准笔记应正常组装发布包")
        self.assertTrue(any(patch.get(NF.STATUS) == "待发布" for _, patch in updates),
                        "已声明笔记应被置为待发布")
        self.assertEqual(summary["errors"], [], "已声明笔记不应触发任何硬闸错误")


if __name__ == "__main__":
    unittest.main()
