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


class TestNetpanSource(unittest.TestCase):
    """NetpanSource 的契约:**把网盘给的东西过滤成待入库清单**(去掉目录、去掉非图非视频)。

    原来这条测试写的是 `test_list_empty_in_stub`,直接断言 `NetpanSource().list() == []`,
    **前提是"这台机器的网盘恰好是 stub 模式"**。可真配了 BDUSS 的机器上 netpan 是 real 模式,
    它会真去列网盘目录——2026-07-14 我往待入库箱传了压测图,这条测试当场变红。
    **测试不该赌环境**(而且赌的还是"环境是 stub"——正是我们不该依赖的东西)。
    改成显式控制 seam:不管这台机器有没有网盘凭证,契约都成立。
    """

    def _src(self, entries):
        from unittest import mock
        from orchestrator import netpan
        inc = _fresh(Path(tempfile.mkdtemp()) / "assets")
        with mock.patch.object(netpan, "list_dir", lambda remote: entries):
            return inc.NetpanSource().list()

    def test_empty_inbox_gives_empty_list(self):
        self.assertEqual(self._src([]), [])

    def test_filters_dirs_and_non_media(self):
        """真实的待入库箱里会混进目录和人误传的文件(实测:箱里躺着个 gy_probe2.txt)——都得过滤掉。"""
        got = self._src([
            {"name": "子目录", "path": "/巧荷素材/待入库/子目录", "is_dir": True},
            {"name": "gy_probe2.txt", "path": "/巧荷素材/待入库/gy_probe2.txt", "is_dir": False},
            {"name": "DSC001.jpg", "path": "/巧荷素材/待入库/DSC001.jpg", "is_dir": False},
        ])
        self.assertEqual([x["name"] for x in got], ["DSC001.jpg"])   # 只剩真图/视频
        self.assertTrue(got[0]["key"])                                # 带耐久指针(去重/寻址靠它)


if __name__ == "__main__":
    unittest.main()
