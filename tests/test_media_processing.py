"""媒体加工任务契约:AI剪进入可恢复任务,不直接冒充成片进入 Note 状态机。"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestMediaProcessing(unittest.TestCase):
    def test_ensure_task_is_idempotent_and_carries_video_editing_gate(self):
        from orchestrator import media_processing as mp

        root = Path(tempfile.mkdtemp())
        playbook = {
            "id": "穿搭",
            "content_type": "唯美ootd",
            "edit_skill": "video-editing",
            "edit_params": {"style": "gentle"},
        }
        candidate = {"sku": "S1", "款式": "甲", "剪成": ["上身视频"]}
        source_materials = [{"code": "M1", "type": "商品图", "link": "素材库/S1/01-原始拍摄/M1.jpg"}]

        first = mp.ensure_task("A号", playbook, candidate, source_materials, day=date(2026, 7, 9), root=root)
        second = mp.ensure_task("A号", playbook, candidate, source_materials, day=date(2026, 7, 10), root=root)

        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "existing")
        self.assertEqual(first["task"]["task_key"], second["task"]["task_key"], "同一账号/方法论/SKU 不应跨天重复加工")
        self.assertEqual(first["task"]["state"], "待生成剪单")
        self.assertEqual(first["task"]["edit_skill"], "video-editing")
        self.assertEqual(first["task"]["edit_params"], {"style": "gentle"})
        self.assertEqual(first["task"]["gates"], ["剪单待人确认", "成片待验收"])

        task_path = root / "_processing" / f"{first['task']['task_key']}.json"
        self.assertTrue(task_path.exists())
        saved = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["source_materials"], source_materials)
        self.assertEqual(saved["output_contract"]["final_mp4"], "")


if __name__ == "__main__":
    unittest.main()
