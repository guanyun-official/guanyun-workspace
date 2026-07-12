"""拍摄需求单(头侧):素材缺口=目标缓冲−已拍可用,够不提、见底才提,附拍摄要求+参考。零网络。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import shotlist, feishu_io  # noqa: E402
from orchestrator.bitable import AccountFields as AF, MaterialFields as MF, MaterialStatus as MS  # noqa: E402


def _mat(rid, mtype, acc_rid):
    return {"record_id": rid, "fields": {MF.TYPE: mtype, MF.SHOT_STATUS: MS.SHOT,
                                         MF.ACCOUNTS: [{"record_ids": [acc_rid]}]}}


class TestShotNeeds(unittest.TestCase):
    def _run(self, mats):
        base = {
            AF.TABLE: [{"record_id": "recOOTD", "fields": {AF.NAME: "ootd号"}},
                       {"record_id": "recTW1", "fields": {AF.NAME: "图文号1"}}],
            MF.TABLE: mats,
        }
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])):
            return shotlist.shot_needs("巧荷")

    def test_low_inventory_flagged_with_brief_and_ref(self):
        # ootd号 上身视频 只有 1 条已拍(目标 runway_alert_days=4)→ 缺 3,带拍摄要求+参考
        needs = self._run([_mat("m1", "上身视频", "recOOTD")])
        e = [n for n in needs if n["account"] == "ootd号" and n["类型"] == "上身视频"]
        self.assertTrue(e, "库存不足应进拍摄需求单")
        self.assertEqual(e[0]["已有"], 1)
        self.assertGreaterEqual(e[0]["缺"], 1)
        self.assertTrue(e[0]["拍摄要求"] and e[0]["参考"], "要带拍摄要求 brief + 参考")
        self.assertIn("writing-ootd-caption", e[0]["参考"])   # 参考指向该模式风格技能
        self.assertIn("待入库", e[0]["投递去向"])              # 答"人拍完怎么给到":指向网盘投递箱

    def test_enough_inventory_not_flagged(self):
        # 图文号1 上身图 备足 5 条(目标 3)→ 不进单
        mats = [_mat(f"g{i}", "上身图", "recTW1") for i in range(5)]
        needs = self._run(mats)
        tw1_img = [n for n in needs if n["account"] == "图文号1" and n["类型"] == "上身图"]
        self.assertEqual(tw1_img, [], "库存够(≥目标缓冲)就不该提补拍")


if __name__ == "__main__":
    unittest.main()
