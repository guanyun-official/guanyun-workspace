import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.sim_day as sim_day  # noqa: E402


class TestSimDayCleanup(unittest.TestCase):
    def test_locked_engine_run_still_deletes_seeded_records(self):
        """真实 Base 压测若撞上单 writer 锁,脚本必须清理本轮播种记录。"""
        created: list[tuple[str, dict]] = []
        deleted: list[str] = []

        def create_record(table: str, fields: dict) -> str:
            rid = f"rec{len(created)}"
            created.append((table, fields))
            return rid

        with mock.patch.object(sim_day.config, "ENV_NAME", "test"), \
                mock.patch.object(sim_day.feishu_io, "create_record", create_record), \
                mock.patch.object(sim_day.feishu_io, "delete_record", lambda _table, rid: deleted.append(rid)), \
                mock.patch.object(sim_day, "run", lambda **_kwargs: {"skipped": "locked"}):
            self.assertEqual(sim_day.main(), 1)

        self.assertEqual(len(created), len(sim_day.SEEDS))
        self.assertEqual(deleted, [f"rec{i}" for i in range(len(sim_day.SEEDS))])


if __name__ == "__main__":
    unittest.main()
