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
