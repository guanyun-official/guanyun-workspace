import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.trial_smoke as ts  # noqa: E402
from scripts.cron_status import Check as CronCheck  # noqa: E402
from scripts.preflight_operational import Check as PreflightCheck  # noqa: E402


def completed(stdout: str = "ok", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def passing_trial_report() -> dict:
    return {
        "checks": [
            {"name": "run_logs", "status": "PASS", "detail": "ok"},
            {"name": "daily", "status": "PASS", "detail": "1"},
            {"name": "heartbeat", "status": "PASS", "detail": "1"},
            {"name": "run_failures", "status": "PASS", "detail": "0"},
        ],
        "run_summary": {"daily_count": 1, "heartbeat_count": 1, "cost_cny": 0.0},
    }


class TestTrialSmoke(unittest.TestCase):
    def test_smoke_runs_cron_equivalent_steps_with_dry_alerts(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            self.assertEqual(kwargs["env"]["ALERT_DRY_RUN"], "1")
            return completed(stdout=f"{args[-1]} ok")

        with mock.patch.object(ts.preflight_operational, "run_checks", return_value=[PreflightCheck("base", "PASS", "ok")]), \
                mock.patch.object(ts.cron_status, "run_checks", return_value=[CronCheck("crontab", "WARN", "not installed")]), \
                mock.patch.object(ts.trial_report, "build_report", return_value=passing_trial_report()):
            result = ts.run_smoke(
                llm="stub",
                limit=20,
                skip_plan=False,
                real_alerts=False,
                now=datetime(2026, 7, 10, 12, 0),
                runner=runner,
            )

        commands = [c[0] for c in calls]
        self.assertEqual(len(commands), 3)
        self.assertIn("--mode", commands[0])
        self.assertIn("daily", commands[0])
        self.assertNotIn("--skip-plan", commands[0])
        self.assertIn("heartbeat", commands[1])
        self.assertIn("scripts/backup_tables.py", commands[2])
        self.assertEqual(result["start"], "2026-07-10T12:00:00")
        self.assertEqual(result["alerts"], "dry")
        self.assertTrue(all(s["status"] == "PASS" for s in result["steps"]))

    def test_skip_plan_is_explicit_diagnostic_mode(self):
        commands = []

        def runner(args, **_kwargs):
            commands.append(args)
            return completed()

        with mock.patch.object(ts.preflight_operational, "run_checks", return_value=[PreflightCheck("base", "PASS", "ok")]), \
                mock.patch.object(ts.cron_status, "run_checks", return_value=[]), \
                mock.patch.object(ts.trial_report, "build_report", return_value=passing_trial_report()):
            ts.run_smoke(
                llm="stub",
                limit=5,
                skip_plan=True,
                real_alerts=False,
                now=datetime(2026, 7, 10, 12, 0),
                runner=runner,
            )

        self.assertIn("--skip-plan", commands[0])
        self.assertIn("5", commands[0])

    def test_command_failure_makes_smoke_fail(self):
        def runner(args, **_kwargs):
            if "daily" in args:
                return completed(stdout="daily failed", returncode=1)
            return completed()

        with mock.patch.object(ts.preflight_operational, "run_checks", return_value=[PreflightCheck("base", "PASS", "ok")]), \
                mock.patch.object(ts.cron_status, "run_checks", return_value=[]), \
                mock.patch.object(ts.trial_report, "build_report", return_value=passing_trial_report()):
            result = ts.run_smoke(
                llm="stub",
                limit=20,
                skip_plan=False,
                real_alerts=False,
                now=datetime(2026, 7, 10, 12, 0),
                runner=runner,
            )

        statuses = {s["name"]: s["status"] for s in result["steps"]}
        self.assertEqual(statuses["daily"], "FAIL")

    def test_orchestrator_json_output_is_summarized(self):
        detail = ts._summarize_command_output(
            'env=test test_mode=True mode=daily llm=stub\n{"mode":"daily","actions":[["N","催审"]],"errors":[],"planning":{"created":1,"existing":2}}\n',
            0,
        )

        self.assertEqual(detail, "mode=daily actions=1 errors=0 planning_created=1 planning_existing=2")

    def test_locked_orchestrator_run_is_a_failed_smoke_step(self):
        step = ts._run_command(
            "daily",
            ["python", "-m", "orchestrator.run"],
            env={},
            runner=lambda *_a, **_k: completed(stdout='{"skipped":"locked"}', returncode=0),
        )

        self.assertEqual(step.status, "FAIL")
        self.assertEqual(step.detail, "skipped=locked")

    def test_trial_report_failure_makes_smoke_fail(self):
        report = passing_trial_report()
        report["checks"][0]["status"] = "FAIL"

        with mock.patch.object(ts.preflight_operational, "run_checks", return_value=[PreflightCheck("base", "PASS", "ok")]), \
                mock.patch.object(ts.cron_status, "run_checks", return_value=[]), \
                mock.patch.object(ts.trial_report, "build_report", return_value=report):
            result = ts.run_smoke(
                llm="stub",
                limit=20,
                skip_plan=True,
                real_alerts=False,
                now=datetime(2026, 7, 10, 12, 0),
                runner=lambda *_a, **_k: completed(),
            )

        statuses = {s["name"]: s["status"] for s in result["steps"]}
        self.assertEqual(statuses["trial_report"], "FAIL")


if __name__ == "__main__":
    unittest.main()
