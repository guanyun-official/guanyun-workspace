"""通用策略解释器:mode来自strategy声明(改data变行为),引擎零账号特定逻辑。"""
import sys, tempfile, unittest
from datetime import date
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

    def test_view_lookup_uses_declared_view_key_not_playbook_id(self):
        """Playbook id 是方法论身份，view 才是盘侧 bin 键；两者允许不同。"""
        import scripts.planner as pl
        root = Path(tempfile.mkdtemp())
        original_root = pl.mv.ASSET_ROOT
        pl.mv.ASSET_ROOT = root
        try:
            pl.mv.add_select("V号", "archive-bin", "GY-1", "/raw/a.mp4", "video:0-6", root=root)
            strategies = {
                "V号": {
                    "account": "V号",
                    "cadence": {"posts_per_day": 1},
                    "autonomy": "approve",
                    "playbooks": [{
                        "id": "考据", "content_type": "文物对照", "weight": 1.0,
                        "material_needs": ["文物对照图"], "view": "archive-bin",
                    }],
                }
            }
            result = self._run(strategies, {"衣服总表": [], "素材表": [], "笔记表": []})
        finally:
            pl.mv.ASSET_ROOT = original_root

        self.assertEqual(result["V号"]["今日发"]["来源"], "视图")
        self.assertEqual(result["V号"]["今日发"]["方法论"], "考据")

    def test_playbook_performance_feedback_surfaced(self):
        # G7 反馈:已发笔记按方法论聚合均赞 → planner 输出「方法论表现」(闭环学习信号可见)
        s = {"F号": {"account": "F号", "cadence": {"posts_per_day": 1}, "autonomy": "approve"}}
        tables = {"衣服总表": [], "素材表": [], "笔记表": [
            _rec({"排期编号": "N1", "账号(自动)": "F号", "状态": "已发", "方法论": "考据", "点赞": 300}),
            _rec({"排期编号": "N2", "账号(自动)": "F号", "状态": "已发", "方法论": "考据", "点赞": 100}),
            _rec({"排期编号": "N3", "账号(自动)": "F号", "状态": "已发", "方法论": "ootd", "点赞": 50})]}
        perf = self._run(s, tables)["F号"]["方法论表现"]
        self.assertEqual(perf["考据"]["均赞"], 200.0, "考据两条均赞 (300+100)/2=200")
        self.assertEqual(perf["ootd"]["条数"], 1)

    def test_materialize_day_creates_one_idempotent_note(self):
        """daily 排产把现成成片物化为 Note；同一天重跑不得重复创建。"""
        import scripts.planner as pl
        strategies = {
            "A号": {
                "account": "A号",
                "cadence": {"posts_per_day": 1},
                "autonomy": "approve",
                "material_needs": {"唯美ootd": ["上身视频"]},
            }
        }
        tables = {
            "衣服总表": [_rec({"衣服编号": "S1", "款式名称": "甲"})],
            "笔记表": [],
            "素材表": [_rec({
                "素材编号": "M1", "拍摄状态": "已拍", "关联衣服": "S1", "类型": "上身视频",
            })],
            "内容类型表": [{"record_id": "ct-1", "fields": {"内容类型名": "唯美ootd"}}],
        }
        created = []

        def list_records(table):
            return tables[table]

        def create_record(table, fields):
            self.assertEqual(table, "笔记表")
            created.append(fields)
            tables["笔记表"].append({"record_id": "note-1", "fields": fields})
            return "note-1"

        with mock.patch.object(pl, "load_strategies", return_value=strategies), \
             mock.patch.object(pl.feishu_io, "list_records", side_effect=list_records), \
             mock.patch.object(pl.feishu_io, "create_record", side_effect=create_record):
            first = pl.materialize_day(day=date(2026, 7, 9))
            second = pl.materialize_day(day=date(2026, 7, 9))

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["existing"], 1)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["状态"], "待出文案")
        self.assertEqual(created[0]["内容类型"], ["ct-1"])
        self.assertEqual(created[0]["方法论"], "唯美ootd")
        self.assertEqual(created[0]["关联衣服"], ["r"])
        self.assertEqual(created[0]["关联素材"], ["r"])

    def test_sku_fallback_uses_playbook_matching_the_ready_material(self):
        """SKU 成片只能归到素材需求匹配的方法论，不能被更高权重的不相关方法论抢走。"""
        strategies = {
            "A号": {
                "account": "A号",
                "cadence": {"posts_per_day": 1},
                "autonomy": "approve",
                "playbooks": [
                    {
                        "id": "考据", "content_type": "文物对照", "weight": 0.8,
                        "material_needs": ["文物对照图"], "view": "考据",
                    },
                    {
                        "id": "穿搭", "content_type": "唯美ootd", "weight": 0.2,
                        "material_needs": ["上身视频"], "view": "穿搭",
                    },
                ],
            }
        }
        tables = {
            "衣服总表": [_rec({"衣服编号": "S1", "款式名称": "甲"})],
            "笔记表": [],
            "素材表": [_rec({
                "素材编号": "M1", "拍摄状态": "已拍", "关联衣服": "S1", "类型": "上身视频",
            })],
        }

        today = self._run(strategies, tables)["A号"]["今日发"]

        self.assertEqual(today["来源"], "现成成片")
        self.assertEqual(today["方法论"], "穿搭")

    def test_materialize_day_does_not_publish_raw_material_as_finished_media(self):
        """只有原料、仍需 AI 剪辑时不创建 Note，避免原料沿发布状态机被当成成片。"""
        import scripts.planner as pl
        strategies = {
            "A号": {
                "account": "A号",
                "cadence": {"posts_per_day": 1},
                "autonomy": "approve",
                "material_needs": {"唯美ootd": ["上身视频"]},
            }
        }
        tables = {
            "衣服总表": [_rec({"衣服编号": "S1", "款式名称": "甲"})],
            "笔记表": [],
            "素材表": [_rec({
                "素材编号": "M1", "拍摄状态": "已拍", "关联衣服": "S1", "类型": "商品图",
            })],
            "内容类型表": [{"record_id": "ct-1", "fields": {"内容类型名": "唯美ootd"}}],
        }
        with mock.patch.object(pl, "load_strategies", return_value=strategies), \
             mock.patch.object(pl.feishu_io, "list_records", side_effect=lambda table: tables[table]), \
             mock.patch.object(pl.feishu_io, "create_record") as create:
            result = pl.materialize_day(day=date(2026, 7, 9))

        create.assert_not_called()
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["skipped"], [{"account": "A号", "reason": "media_processing_not_wired"}])

    def test_materialize_day_projects_view_clip_into_note(self):
        """View 候选创建 Note 时投影 playbook、clip_id 与原始 Material 关联。"""
        import scripts.planner as pl
        root = Path(tempfile.mkdtemp())
        original_root = pl.mv.ASSET_ROOT
        pl.mv.ASSET_ROOT = root
        try:
            clip = pl.mv.add_select("A号", "考据", "M1", "/raw/a.mp4", "video:0-6", root=root)
            strategies = {
                "A号": {
                    "account": "A号",
                    "cadence": {"posts_per_day": 1},
                    "autonomy": "approve",
                    "playbooks": [{
                        "id": "考据", "content_type": "文物对照", "weight": 1.0,
                        "material_needs": ["文物对照图"], "view": "考据",
                    }],
                }
            }
            tables = {
                "衣服总表": [],
                "笔记表": [],
                "素材表": [{"record_id": "mat-1", "fields": {
                    "素材编号": "M1", "拍摄状态": "已拍", "类型": "商品图",
                }}],
                "内容类型表": [{"record_id": "ct-1", "fields": {"内容类型名": "文物对照"}}],
            }
            created = []
            with mock.patch.object(pl, "load_strategies", return_value=strategies), \
                 mock.patch.object(pl.feishu_io, "list_records", side_effect=lambda table: tables[table]), \
                 mock.patch.object(pl.feishu_io, "create_record",
                                   side_effect=lambda _table, fields: created.append(fields) or "note-1"):
                result = pl.materialize_day(day=date(2026, 7, 9))
        finally:
            pl.mv.ASSET_ROOT = original_root

        self.assertEqual(result["created"], 1)
        self.assertEqual(created[0]["方法论"], "考据")
        self.assertEqual(created[0]["内容类型"], ["ct-1"])
        self.assertEqual(created[0]["关联子素材"], clip)
        self.assertEqual(created[0]["关联素材"], ["mat-1"])
