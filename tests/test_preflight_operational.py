import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.preflight_operational as pf  # noqa: E402
from orchestrator import config  # noqa: E402


def completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestOperationalPreflight(unittest.TestCase):
    def test_environment_requires_operational_base_and_test_mode(self):
        with mock.patch.object(config, "BASE_TOKEN", config.PROD_BASE), \
                mock.patch.object(config, "TEST_MODE", False), \
                mock.patch.object(config, "ENV_NAME", "prod"):
            checks = pf.check_environment()

        self.assertEqual([c.status for c in checks], ["FAIL", "FAIL", "FAIL"])

    def test_residual_records_fail_preflight(self):
        rows = [
            {"fields": {"排期编号": "_STRESS-Q1", "状态": "待发布"}},
            {"fields": {"排期编号": "NORMAL", "状态": "已发"}},
        ]

        check = pf.check_residuals(lambda _table: rows)

        self.assertEqual(check.status, "FAIL")
        self.assertIn("_STRESS-Q1", check.detail)

    def test_cron_preview_checks_selected_llm(self):
        check = pf.check_cron_preview(
            "stub",
            runner=lambda *_a, **_k: completed("--mode daily --llm stub\n--mode heartbeat --llm stub\n"),
        )

        self.assertEqual(check.status, "PASS")

    def test_existing_cron_block_is_warn_not_fail(self):
        check = pf.check_crontab_state(runner=lambda *_a, **_k: completed(pf.MARK_BEGIN))

        self.assertEqual(check.status, "WARN")

    def test_main_returns_nonzero_on_fail(self):
        with mock.patch.object(pf, "run_checks", return_value=[pf.Check("x", "FAIL", "bad")]):
            self.assertEqual(pf.main(["--llm", "stub"]), 1)


if __name__ == "__main__":
    unittest.main()
