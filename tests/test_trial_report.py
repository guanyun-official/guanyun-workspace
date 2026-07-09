import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.trial_report as tr  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402
from orchestrator.bitable import NoteStatus as NS  # noqa: E402
from orchestrator.bitable import RunLogFields as RLF  # noqa: E402


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class TestTrialReport(unittest.TestCase):
    def test_run_summary_counts_activity_failures_cost_and_packages(self):
        now = datetime(2026, 7, 10, 12, 0)
        rows = [
            {"fields": {RLF.TIME: ms(now), RLF.ACTION: "daily轮询", RLF.RESULT: "成功", RLF.SUMMARY: "daily 一轮完成", RLF.COST: 1.25}},
            {"fields": {RLF.TIME: ms(now), RLF.ACTION: "heartbeat轮询", RLF.RESULT: "成功", RLF.SUMMARY: "heartbeat 一轮完成", RLF.DETAIL: "cost_cny=0.75"}},
            {"fields": {RLF.TIME: ms(now), RLF.ACTION: "组装发布包", RLF.RESULT: "成功", RLF.SUMMARY: "发布包就绪:PQ-1"}},
            {"fields": {RLF.TIME: ms(now), RLF.ACTION: "heartbeat轮询", RLF.RESULT: "失败", RLF.SUMMARY: "heartbeat 一轮完成:错误1"}},
        ]

        summary = tr.summarize_run_logs(rows, since=now - timedelta(days=1))

        self.assertEqual(summary["daily_count"], 1)
        self.assertEqual(summary["heartbeat_count"], 2)
        self.assertEqual(summary["package_count"], 1)
        self.assertEqual(len(summary["failures"]), 1)
        self.assertEqual(summary["cost_cny"], 2.0)

    def test_note_summary_counts_published_receipts_and_queues(self):
        now = datetime(2026, 7, 10, 12, 0)
        rows = [
            {"fields": {NF.CODE: "P1", NF.STATUS: NS.PUBLISHED, NF.PUBLISHED_AT: ms(now), NF.PUBLISH_LINK: {"link": "https://xhs/1"}}},
            {"fields": {NF.CODE: "P2", NF.STATUS: NS.PUBLISHED, NF.PUBLISHED_AT: ms(now)}},
            {"fields": {NF.CODE: "Q1", NF.STATUS: NS.TO_PUBLISH}},
            {"fields": {NF.CODE: "R1", NF.STATUS: NS.DRAFT_PENDING}},
            {"fields": {NF.CODE: "A1", NF.STATUS: NS.APPROVED}},
        ]

        summary = tr.summarize_notes(rows, since=now - timedelta(days=1))

        self.assertEqual(summary["published"], ["P1", "P2"])
        self.assertEqual(summary["published_with_link"], ["P1"])
        self.assertEqual(summary["to_publish"], ["Q1"])
        self.assertEqual(summary["review"], ["R1"])
        self.assertEqual(summary["approved"], ["A1"])

    def test_require_activity_turns_missing_daily_heartbeat_into_fail(self):
        run_summary = {
            "total": 0,
            "latest": None,
            "daily_count": 0,
            "heartbeat_count": 0,
            "failures": [],
            "cost_cny": 0,
            "package_count": 0,
        }
        note_summary = {"published": [], "published_with_link": [], "review": [], "approved": [], "to_publish": []}

        checks = tr.build_checks(run_summary, note_summary, require_activity=True)
        statuses = {c.name: c.status for c in checks}

        self.assertEqual(statuses["run_logs"], "FAIL")
        self.assertEqual(statuses["daily"], "FAIL")
        self.assertEqual(statuses["heartbeat"], "FAIL")

    def test_build_report_reads_both_tables(self):
        now = datetime(2026, 7, 10, 12, 0)

        def list_records(table: str):
            if table == "运行日志表":
                return [{"fields": {RLF.TIME: ms(now), RLF.ACTION: "daily轮询", RLF.RESULT: "成功", RLF.SUMMARY: "daily"}}]
            if table == "笔记表":
                return [{"fields": {NF.CODE: "P1", NF.STATUS: NS.PUBLISHED, NF.PUBLISHED_AT: ms(now), NF.PUBLISH_LINK: {"link": "x"}}}]
            raise AssertionError(table)

        report = tr.build_report(days=7, require_activity=False, list_records=list_records, now=now)

        self.assertEqual(report["run_summary"]["daily_count"], 1)
        self.assertEqual(report["note_summary"]["published"], ["P1"])

    def test_build_report_can_start_from_explicit_since(self):
        now = datetime(2026, 7, 10, 12, 0)
        old = now - timedelta(days=2)
        since = now - timedelta(hours=1)

        def list_records(table: str):
            if table == "运行日志表":
                return [
                    {"fields": {RLF.TIME: ms(old), RLF.ACTION: "heartbeat轮询", RLF.RESULT: "失败", RLF.SUMMARY: "old failure"}},
                    {"fields": {RLF.TIME: ms(now), RLF.ACTION: "heartbeat轮询", RLF.RESULT: "成功", RLF.SUMMARY: "new ok"}},
                ]
            if table == "笔记表":
                return []
            raise AssertionError(table)

        report = tr.build_report(days=7, since=since, require_activity=True, list_records=list_records, now=now)
        statuses = {c["name"]: c["status"] for c in report["checks"]}

        self.assertEqual(report["run_summary"]["heartbeat_count"], 1)
        self.assertEqual(statuses["run_failures"], "PASS")


if __name__ == "__main__":
    unittest.main()
