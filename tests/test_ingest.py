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
