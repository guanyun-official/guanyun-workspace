"""素材增量入库:源可换(local/netpan)、按 key 去重、机械拆解(转码)。零网络。"""
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(assets: Path):
    """把 ASSET_ROOT 指到临时目录再 reload,隔离台账。"""
    os.environ["GY_ASSET_ROOT"] = str(assets)
    import scripts.ingest as ing
    importlib.reload(ing)
    import scripts.ingest_incremental as inc
    importlib.reload(inc)
    return inc


class TestLocalSource(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "src").mkdir()
        (self.d / "src" / "a.jpg").write_text("x")
        (self.d / "src" / "b.mov").write_text("y")
        (self.d / "src" / "note.txt").write_text("z")     # other→跳过
        self.inc = _fresh(self.d / "assets")

    def test_list_skips_non_media(self):
        items = self.inc.LocalSource(str(self.d / "src")).list()
        names = sorted(i["name"] for i in items)
        self.assertEqual(names, ["a.jpg", "b.mov"])       # note.txt 被排除

    def test_plan_dedups_seen(self):
        items = self.inc.LocalSource(str(self.d / "src")).list()
        seen = {items[0]["key"]}
        self.assertEqual(len(self.inc.plan(items, seen)), 1)

    def test_run_transcodes_and_records_seen(self):
        src = self.inc.LocalSource(str(self.d / "src"))
        # 造一个 heic,验证 process 会转 jpg(mock sips 不真跑)
        (self.d / "src" / "c.heic").write_text("h")
        with mock.patch("orchestrator.media._run_convert") as rc:
            done = self.inc.run(src, self.d / "cache", write_seen=True)
        codes = {d["素材编号"] for d in done}
        self.assertEqual(codes, {"a", "b", "c"})
        rc.assert_called()                                # heic 触发转码
        # 幂等:再跑一次无新素材
        again = self.inc.run(src, self.d / "cache", write_seen=True)
        self.assertEqual(again, [])

    def test_pointer_is_durable_file_uri(self):
        it = self.inc.LocalSource(str(self.d / "src")).list()[0]
        self.assertTrue(self.inc.LocalSource(str(self.d / "src")).pointer(it).startswith("file://"))


class TestNetpanSourceStub(unittest.TestCase):
    def test_list_empty_in_stub(self):
        inc = _fresh(Path(tempfile.mkdtemp()) / "assets")
        # stub 下 netpan.list_dir 返 []，源自然空
        self.assertEqual(inc.NetpanSource().list(), [])


if __name__ == "__main__":
    unittest.main()
