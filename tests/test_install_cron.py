"""cron 安装脚本预览契约(lean)。大刀阔斧后重引擎删:cron 只留 backup + 周复盘,
内容生成走薄执行器 draft_one(手动,轻调度器见 #8),不再挂 orchestrator.run daily/heartbeat。"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestInstallCronPreview(unittest.TestCase):
    def _preview(self, *args: str) -> str:
        return subprocess.check_output(["bash", "scripts/install_cron.sh", *args], cwd=ROOT, text=True)

    def test_preview_has_backup_and_weekly(self):
        out = self._preview()
        self.assertIn("backup_tables.py", out)      # 数据安全底线:每日备份
        self.assertIn("collect_metrics", out)       # 周日效果回流采集
        self.assertIn("claude -p", out)             # 周复盘飞轮

    def test_preview_has_no_dangling_deleted_engine_ref(self):
        out = self._preview()
        self.assertNotIn("orchestrator.run", out, "重引擎已删,cron 不得再悬空引用 orchestrator.run")

    def test_preview_notes_manual_thin_executor(self):
        out = self._preview()
        self.assertIn("draft_one", out, "预览应说明内容生成走薄执行器(手动,轻调度器见 #8)")

    def test_unknown_argument_fails(self):
        proc = subprocess.run(["bash", "scripts/install_cron.sh", "--bogus"],
                              cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
