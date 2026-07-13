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
        from tests._search import search_mock
        # 素材走 search_in(按需类型过滤,过滤型mock治假绿);账号表小仍 list_records
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", search_mock(base)):
            return shotlist.shot_needs("巧荷")

    def test_low_inventory_flagged_with_brief_and_ref(self):
        # ootd号 上身视频 只有 1 条已拍(目标 runway_alert_days=4)→ 缺 3,带拍摄要求+参考
        needs = self._run([_mat("m1", "上身视频", "recOOTD")])
        e = [n for n in needs if n["account"] == "ootd号" and n["类型"] == "上身视频"]
        self.assertTrue(e, "库存不足应进拍摄需求单")
        self.assertEqual(e[0]["已有"], 1)
        self.assertGreaterEqual(e[0]["缺"], 1)
        self.assertTrue(e[0]["拍摄要求"] and e[0]["参考"], "要带拍摄要求 brief + 参考")
        self.assertIn("待入库", e[0]["投递去向"])              # 答"人拍完怎么给到":指向网盘投递箱
        # **补拍单的读者是拿相机的人,不是 agent**(2026-07-14 运营视角实测):
        # 原来这里断言参考里要有 `writing-ootd-caption`——那是**代码库里的技能文件路径**。
        # 摄影师在片场、手机上收到这条,他打不开 skills/xxx/SKILL.md,也不该去打开。
        # 参考必须是**他能直接看的画面**(vision 标 + 网盘链接),或库存为空时的诚实兜底。
        ref = e[0]["参考"]
        self.assertNotIn("SKILL.md", ref, "别把代码库文件路径塞给摄影师")
        self.assertNotIn("writing-", ref, "别把技能名塞给摄影师(那是出稿用的,与拍摄无关)")
        self.assertTrue("照着这些已有的拍" in ref or "还一条都没有" in ref,
                        f"参考要么给真画面,要么诚实说没有;实际: {ref[:60]}")
        self.assertNotIn("SKILL.md", e[0]["拍摄要求"], "brief 也别提代码库文件")

    def test_reference_gives_real_pictures_not_file_paths(self):
        """有库存时,参考给的是**真画面 + 可点开的链接**——摄影师照着拍。"""
        mats = [_mat("m1", "上身视频", "recOOTD")]
        mats[0]["fields"][MF.NOTE] = "浅粉色带细闪的汉服衣身局部特写，红棕色木质场景，光线柔和"
        mats[0]["fields"][MF.LINK] = {"link": "https://pan.baidu.com/s/xxx", "text": "v.mp4"}
        needs = self._run(mats)
        ref = [n for n in needs if n["account"] == "ootd号" and n["类型"] == "上身视频"][0]["参考"]
        self.assertIn("浅粉色带细闪", ref)                      # 真画面(豆包 vision 标)
        self.assertIn("https://pan.baidu.com/s/xxx", ref)      # 能点开取参考片

    def test_enough_inventory_not_flagged(self):
        # 图文号1 上身图 备足 5 条(目标 3)→ 不进单
        mats = [_mat(f"g{i}", "上身图", "recTW1") for i in range(5)]
        needs = self._run(mats)
        tw1_img = [n for n in needs if n["account"] == "图文号1" and n["类型"] == "上身图"]
        self.assertEqual(tw1_img, [], "库存够(≥目标缓冲)就不该提补拍")


if __name__ == "__main__":
    unittest.main()
