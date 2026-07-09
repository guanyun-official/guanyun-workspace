import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.cron_status as cs  # noqa: E402
from orchestrator.bitable import RunLogFields as RLF  # noqa: E402


def completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestCronStatus(unittest.TestCase):
    def test_missing_crontab_warns_by_default_and_fails_when_required(self):
        runner = lambda *_a, **_k: completed(returncode=1)

        self.assertEqual(cs.check_crontab(runner=runner).status, "WARN")
        self.assertEqual(cs.check_crontab(require_installed=True, runner=runner).status, "FAIL")

    def test_installed_crontab_requires_daily_heartbeat_and_backup(self):
        block = f"""{cs.MARK_BEGIN}
0 9 * * * cd /x && python3 -m orchestrator.run --mode daily --llm stub
*/30 9-21 * * * cd /x && python3 -m orchestrator.run --mode heartbeat --llm stub
30 23 * * * cd /x && python3 scripts/backup_tables.py
{cs.MARK_END}
"""

        check = cs.check_crontab(runner=lambda *_a, **_k: completed(block))

        self.assertEqual(check.status, "PASS")
        self.assertIn("llm=stub", check.detail)

    def test_incomplete_marked_crontab_fails(self):
        block = f"{cs.MARK_BEGIN}\n0 9 * * * cd /x && python3 -m orchestrator.run --mode daily --llm stub\n{cs.MARK_END}"

        check = cs.check_crontab(runner=lambda *_a, **_k: completed(block))

        self.assertEqual(check.status, "FAIL")

    def test_backup_status_uses_latest_test_directory(self):
        root = Path(tempfile.mkdtemp())
        old = root / "test-20260709"
        new = root / "test-20260710"
        old.mkdir()
        new.mkdir()
        for i in range(5):
            (new / f"{i}.json").write_text("{}", encoding="utf-8")

        check = cs.check_backups(root)

        self.assertEqual(check.status, "PASS")
        self.assertIn("test-20260710", check.detail)

    def test_run_logs_warn_when_latest_is_stale(self):
        now = datetime(2026, 7, 10, 12, 0)
        stale = int((now - timedelta(days=2)).timestamp() * 1000)
        rows = [{"fields": {RLF.TIME: stale, RLF.ACTION: "heartbeat轮询", RLF.RESULT: "成功", RLF.SUMMARY: "old"}}]

        check = cs.check_run_logs(within_hours=24, list_records=lambda _table: rows, now=now)

        self.assertEqual(check.status, "WARN")
        self.assertIn("age_h=48.0", check.detail)

    def test_main_nonzero_when_required_cron_missing(self):
        with unittest.mock.patch.object(
            cs,
            "run_checks",
            return_value=[cs.Check("crontab", "FAIL", "missing")],
        ):
            self.assertEqual(cs.main(["--require-installed"]), 1)


if __name__ == "__main__":
    unittest.main()
