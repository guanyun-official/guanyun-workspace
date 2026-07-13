"""素材摄入冒烟:软链原件不动、manifest 落行。零网络(不测 register)。"""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
class TestIngest(unittest.TestCase):
    def test_link_symlinks_without_moving(self):
        d=Path(tempfile.mkdtemp()); os.environ["GY_ASSET_ROOT"]=str(d/"assets")
        import importlib; import scripts.ingest as ing; importlib.reload(ing)
        src=d/"orig.mp4"; src.write_text("x")
        link=ing.link(str(src),"SKU9","03-成片","a.mp4")
        self.assertTrue(Path(link).is_symlink())
        self.assertTrue(src.exists())               # 原件不动
        self.assertEqual(Path(link).resolve(), src.resolve())
        self.assertTrue((d/"assets"/"SKU9"/"manifest.jsonl").exists())
    def test_scan_lists_files(self):
        d=Path(tempfile.mkdtemp()); (d/"a.jpg").write_text("x"); (d/".hidden").write_text("y")
        import scripts.ingest as ing
        files=ing.scan(str(d))
        self.assertEqual(len(files),1)              # 跳过隐藏文件

    def test_store_produced_uploads_and_registers(self):
        # #40①:成片回传网盘 03-成片 + 登记(来源随像素出处)。mock 掉真上传/写库。
        from unittest import mock
        import scripts.ingest as ing
        from orchestrator import netpan, feishu_io
        created = {}
        with mock.patch.object(netpan, "upload", lambda lp, rd: f"{rd}/{Path(lp).name}"), \
                mock.patch.object(feishu_io, "create_record", lambda t, f: created.update(f) or "recX"):
            rid, ptr = ing.store_produced("/tmp/成片-拼接.mp4", "上身视频", source="实拍",
                                          note="A[0:3]+B后3s 合成", accounts=["recAcc"])
        self.assertEqual(rid, "recX")
        self.assertTrue(ptr.startswith("baidupan:") and ptr.endswith("03-成片/成片-拼接.mp4"))
        self.assertEqual(created["来源"], "实拍")                    # 纯剪辑→实拍(免声明)
        self.assertEqual(created["类型"], "上身视频")

    def test_gen_code_systematic(self):
        import scripts.ingest as ing
        self.assertEqual(ing.gen_code("上身图", "2026-07-02 175609.heic", set()), "ST-260702-001")
        # 同(类型,批次)序号递增
        self.assertEqual(ing.gen_code("上身图", "2026-07-02 x.heic",
                                      {"ST-260702-001", "ST-260702-003"}), "ST-260702-004")
        self.assertEqual(ing.gen_code("上身视频", "2026-06-26 a.mp4", set()), "SV-260626-001")
        self.assertEqual(ing.gen_code("形象图", "无日期.mp4", set()), "XX-000000-001")   # 抽不到日期

    def test_gen_code_covers_12_types(self):
        # 对齐素材表真实 12 类:每类各有独立前缀,互不撞;未知类型→SC(不冒充形象图)
        import scripts.ingest as ing
        want = {"商品图": "SP", "形象图": "XX", "细节图": "XJ", "上身视频": "SV", "上身图": "ST",
                "搭配图": "DP", "空镜·场景": "KJ", "工艺特写": "GY", "制作过程视频": "ZZ",
                "面料·纹理特写": "ML", "文物原图": "WW", "文物对照图": "WD"}
        self.assertEqual(len(set(want.values())), 12)                       # 前缀互不撞
        for mtype, pre in want.items():
            self.assertTrue(ing.gen_code(mtype, "2026-07-02 a.jpg", set()).startswith(f"{pre}-"))
        self.assertTrue(ing.gen_code("没这个类型", "2026-07-02 a.jpg", set()).startswith("SC-"))

    def test_register_separates_relpath_and_link(self):
        # 字段归位:相对路径=系统指针(text),链接=分享链(url,带文件名);打标留空适用账号
        from unittest import mock
        import scripts.ingest as ing
        from orchestrator import feishu_io
        created = {}
        with mock.patch.object(feishu_io, "create_record", lambda t, f: created.update(f) or "recR"):
            rid = ing.register("ST-260702-001", "上身图", "baidupan:/巧荷素材/待入库/a.heic",
                               note="藕荷色对襟·园林·柔光", source="实拍")
        self.assertEqual(rid, "recR")
        self.assertEqual(created["相对路径"], "baidupan:/巧荷素材/待入库/a.heic")   # 系统指针进相对路径
        self.assertEqual(created["链接"]["text"], "a.heic")                        # url 字段带文件名
        self.assertNotIn("适用账号", created)                                      # 打标不管消费,留空
        self.assertNotIn("生成参数", created)                                      # 实拍不填生成参数

    def test_register_forces_ai_source_by_location(self):
        # ★合规:落点在 02-AI生成/ → 强制 AI生成(不管传入 source),漏标AI是硬伤,来源由落点定不靠视觉
        from unittest import mock
        import scripts.ingest as ing
        from orchestrator import feishu_io
        created = {}
        with mock.patch.object(feishu_io, "create_record", lambda t, f: created.update(f) or "r"):
            ing.register("SP-1", "商品图", "baidupan:/巧荷素材/02-AI生成/x.jpg", source="实拍")   # 传实拍
        self.assertEqual(created["来源"], "AI生成")                                          # 落点覆盖→AI生成

    def test_register_ai_records_gen_params(self):
        # AI 素材:来源=AI生成 且填生成参数(provenance 细节)
        from unittest import mock
        import scripts.ingest as ing
        from orchestrator import feishu_io
        created = {}
        with mock.patch.object(feishu_io, "create_record", lambda t, f: created.update(f) or "r"):
            ing.register("ML-000000-001", "面料·纹理特写", "file:///tmp/x.jpg",
                         source="AI生成", gen_params="doubao seedream;提示词:云锦纹理")
        self.assertEqual(created["来源"], "AI生成")
        self.assertEqual(created["生成参数"], "doubao seedream;提示词:云锦纹理")
