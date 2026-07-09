"""通用策略解释器:mode来自strategy声明(改data变行为),引擎零账号特定逻辑。"""
import sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
def _rec(f): return {"fields": f, "record_id": "r"}

class TestPlanner(unittest.TestCase):
    def _run(self, strategies, tables):
        import scripts.planner as pl
        with mock.patch.object(pl, "load_strategies", return_value=strategies), \
             mock.patch.object(pl.feishu_io, "list_records", side_effect=lambda t: tables[t]):
            return pl.plan()
    def test_manual_strategy_skips_engine(self):
        s = {"实验号": {"account":"实验号","mode":"手动","cadence":{"posts_per_day":0,"pattern":"manual"}}}
        tables = {"衣服总表":[], "笔记表":[], "素材表":[]}
        p = self._run(s, tables)
        self.assertFalse(p["实验号"]["自动"])          # 声明manual→引擎不自动
    def test_drip_ready_and_shoot_from_strategy(self):
        s = {"A号": {"account":"A号","mode":"缓发","cadence":{"posts_per_day":1,"pattern":"drip"},
                    "material_needs":{"ct":["上身视频"]},"runway_alert_days":3,"autonomy":"approve"}}
        tables = {
            "衣服总表":[_rec({"衣服编号":"S1","款式名称":"甲"}),_rec({"衣服编号":"S2","款式名称":"乙"})],
            "笔记表":[],
            "素材表":[_rec({"拍摄状态":"已拍","关联衣服":"S1","类型":"上身视频"})],  # S1有素材
        }
        p = self._run(s, tables)
        self.assertTrue(p["A号"]["自动"])
        self.assertEqual(p["A号"]["今日发"]["来源"], "现成成片")  # 无视图→回退SKU现成成片
        self.assertEqual(p["A号"]["今日发"]["sku"], "S1")
        self.assertTrue(any(x["sku"]=="S2" for x in p["A号"]["拍摄需求"]))  # S2无任何素材→催拍

    def test_raw_material_is_editable_not_shoot(self):
        # 用户洞察:有原始素材(非目标成片)→交剪辑skill,不催拍
        s = {"A号": {"account":"A号","cadence":{"posts_per_day":1},
                    "material_needs":{"ct":["上身视频"]},"autonomy":"approve"}}
        tables = {
            "衣服总表":[_rec({"衣服编号":"S3","款式名称":"丙"})],
            "笔记表":[],
            "素材表":[_rec({"拍摄状态":"已拍","关联衣服":"S3","类型":"商品图"})],  # 有原料但非上身视频
        }
        p = self._run(s, tables)
        self.assertEqual(p["A号"]["今日发"]["来源"], "AI剪")    # 无视图+无现成成片→回退AI剪
        self.assertEqual(p["A号"]["今日发"]["sku"], "S3")
        self.assertFalse(any(x["sku"]=="S3" for x in p["A号"]["拍摄需求"]))  # 不催拍
        self.assertEqual(p["A号"]["余量天数"], 1)              # 可剪算进余量
    def test_unlaunched_skipped(self):
        s = {"官号": {"account":"官号","mode":"叙事","cadence":{"posts_per_day":0},"posts_per_week":2,"launched":False}}
        p = self._run(s, {"衣服总表":[], "笔记表":[], "素材表":[]})
        self.assertFalse(p["官号"]["自动"])          # launched:false→不自动

    def test_explicit_playbooks_drive_planning(self):
        # G4:显式声明两套方法论→排产按其 material_needs 取并集,输出 surfaces 方法论(加方法论=写声明零代码)
        s = {"多号": {"account":"多号","cadence":{"posts_per_day":1},"autonomy":"approve",
                     "playbooks":[
                         {"id":"上身流","weight":0.5,"material_needs":["上身视频"],"view":"上身流"},
                         {"id":"细节流","weight":0.5,"material_needs":["工艺特写"],"view":"细节流"}]}}
        tables = {
            "衣服总表":[_rec({"衣服编号":"S1","款式名称":"甲"})],
            "笔记表":[],
            "素材表":[_rec({"拍摄状态":"已拍","关联衣服":"S1","类型":"上身视频"})],  # 命中"上身流"需求
        }
        p = self._run(s, tables)
        ids = [pb["id"] for pb in p["多号"]["方法论"]]
        self.assertEqual(ids, ["上身流","细节流"], "两套方法论都应 surface")
        self.assertEqual(p["多号"]["今日发"]["sku"], "S1")  # 无视图→SKU回退,S1有上身视频命中需求

    def test_view_readiness_is_sku_optional(self):
        # G6:视图可发余量这条轴 SKU 无关——视图里选入的子素材不挂 SKU 也算可发,used 会被扣掉
        import scripts.planner as pl
        root = Path(tempfile.mkdtemp()); orig = pl.mv.ASSET_ROOT; pl.mv.ASSET_ROOT = root
        try:
            pl.mv.add_select("V号", "考据", "GY-1", "/raw/a.mp4", "video:0-6", root=root)   # 不挂 SKU
            cid2 = pl.mv.add_select("V号", "考据", "GY-1", "/raw/a.mp4", "video:20-26", root=root)
            pl.mv.record_usage(cid2, "PQ-1", "考据", ts=1, root=root)                        # 已被本号笔记用掉
            s = {"V号": {"account":"V号","cadence":{"posts_per_day":1},"autonomy":"approve","runway_alert_days":3,
                        "playbooks":[{"id":"考据","weight":1.0,"material_needs":["文物对照图"],"view":"考据"}]}}
            tables = {"衣服总表":[], "素材表":[],
                      "笔记表":[_rec({"排期编号":"PQ-1","账号(自动)":"V号","状态":"已发"})]}
            p = self._run(s, tables)
            vr = {v["id"]: v for v in p["V号"]["视图余量"]}
            self.assertEqual(vr["考据"]["已选"], 2)
            self.assertEqual(vr["考据"]["可发"], 1, "2 选入 − 1 已用 = 1 可发,全程不挂 SKU")
            # G9:视图有可发→今日发走视图主轴(而非 SKU)
            self.assertEqual(p["V号"]["今日发"]["来源"], "视图")
            self.assertEqual(p["V号"]["今日发"]["方法论"], "考据")
        finally:
            pl.mv.ASSET_ROOT = orig
