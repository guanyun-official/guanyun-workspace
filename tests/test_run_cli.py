"""推进器 CLI：daily 先排产物化，再推进 Note 状态机。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import run as cli


class TestRunCLI(unittest.TestCase):
    def test_daily_materializes_plan_before_engine(self):
        events = []
        with mock.patch.object(sys, "argv", ["orchestrator.run", "--mode", "daily"]), \
             mock.patch("scripts.planner.materialize_day",
                        side_effect=lambda: events.append("plan") or {"created": 1}), \
             mock.patch.object(cli, "run",
                               side_effect=lambda **_kwargs: events.append("engine") or {"errors": []}):
            code = cli.main()

        self.assertEqual(code, 0)
        self.assertEqual(events, ["plan", "engine"])

    def test_daily_skip_plan_is_available_for_non_mutating_checks(self):
        with mock.patch.object(
            sys, "argv", ["orchestrator.run", "--mode", "daily", "--skip-plan"]
        ), mock.patch("scripts.planner.materialize_day") as materialize, \
             mock.patch.object(cli, "run", return_value={"errors": []}):
            code = cli.main()

        self.assertEqual(code, 0)
        materialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
