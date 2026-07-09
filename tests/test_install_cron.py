"""cron 安装脚本预览契约:上线可显式选择 real/stub,避免试运行只能持续烧 LLM。"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestInstallCronPreview(unittest.TestCase):
    def _preview(self, llm: str | None = None) -> str:
        env = os.environ.copy()
        if llm is not None:
            env["GY_CRON_LLM"] = llm
        return subprocess.check_output(["bash", "scripts/install_cron.sh"], cwd=ROOT, env=env, text=True)

    def test_default_preview_uses_real_llm_for_operational_loop(self):
        out = self._preview()
        self.assertIn("--mode daily --llm real", out)
        self.assertIn("--mode heartbeat --llm real", out)

    def test_preview_can_switch_daily_and_heartbeat_to_stub(self):
        out = self._preview("stub")
        self.assertIn("--mode daily --llm stub", out)
        self.assertIn("--mode heartbeat --llm stub", out)
        self.assertNotIn("--llm real >> logs/cron.log", out)


if __name__ == "__main__":
    unittest.main()
