"""网盘薄桥:指针往返 + CLI 输出纯解析 + stub 零真操作红线。零网络、不需 BDUSS。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import netpan  # noqa: E402


class TestPointer(unittest.TestCase):
    def test_pointer_roundtrip(self):
        p = netpan.pointer("/观云素材/01-原始拍摄/a.jpg")
        self.assertTrue(p.startswith("baidupan:"))
        self.assertEqual(netpan.pointer_path(p), "/观云素材/01-原始拍摄/a.jpg")

    def test_pointer_path_passthrough(self):
        # 非本方案指针(file://、http)原样返回,不误伤
        self.assertEqual(netpan.pointer_path("file:///x/a.jpg"), "file:///x/a.jpg")
        self.assertEqual(netpan.pointer_path("https://pan/x"), "https://pan/x")


class TestParseLs(unittest.TestCase):
    SAMPLE = (
        "  #      文件大小       修改日期              文件(目录)\n"
        "  0        -        2026-07-01 08:00:00   01-原始拍摄/\n"
        "  1      1.5MB      2026-07-01 08:01:02   逆光紫藤裙.jpg\n"
        "  2      88.2MB     2026-07-02 09:10:00   走线视频.mov\n"
        "  总: 89.7MB, 文件数: 2, 目录数: 1\n"
    )

    def test_parse_dir_and_files(self):
        items = netpan._parse_ls("/观云素材", self.SAMPLE)
        names = [(i["name"], i["is_dir"]) for i in items]
        self.assertIn(("01-原始拍摄", True), names)
        self.assertIn(("逆光紫藤裙.jpg", False), names)
        self.assertIn(("走线视频.mov", False), names)
        self.assertEqual(len(items), 3)                      # 表头/统计行被过滤
        jpg = next(i for i in items if i["name"] == "逆光紫藤裙.jpg")
        self.assertEqual(jpg["path"], "/观云素材/逆光紫藤裙.jpg")

    def test_parse_empty_and_garbage(self):
        self.assertEqual(netpan._parse_ls("/x", ""), [])
        self.assertEqual(netpan._parse_ls("/x", "乱七八糟没有表格\n---\n"), [])


class TestParseShare(unittest.TestCase):
    def test_link_with_pwd(self):
        out = "链接分享成功\n链接: https://pan.baidu.com/s/1AbCdEf 提取码: x8k2\n"
        self.assertEqual(netpan._parse_share(out),
                         "https://pan.baidu.com/s/1AbCdEf?pwd=x8k2")

    def test_link_without_pwd(self):
        out = "https://pan.baidu.com/s/1Zzz\n"
        self.assertEqual(netpan._parse_share(out), "https://pan.baidu.com/s/1Zzz")

    def test_no_link(self):
        self.assertEqual(netpan._parse_share("失败:未登录\n"), "")


class TestWhoParse(unittest.TestCase):
    """真跑揪出的坑:未登录 who 输出也含 'uid'/'用户名' 字样,只能按 uid≠0 判。"""

    def test_not_logged_in_uid_zero(self):
        self.assertFalse(netpan._who_logged_in("当前帐号 uid: 0, 用户名: , 性别: , 年龄: 0.0"))

    def test_logged_in_real_uid(self):
        self.assertTrue(netpan._who_logged_in("当前帐号 uid: 3821092, 用户名: 观云小助手, 性别: 女, 年龄: 2.0"))

    def test_garbage(self):
        self.assertFalse(netpan._who_logged_in("未登录"))


class TestStubRedline(unittest.TestCase):
    """默认 stub:任何真操作都被挡,离线安全。"""

    def setUp(self):
        self._mode = netpan.MODE
        netpan.MODE = "stub"

    def tearDown(self):
        netpan.MODE = self._mode

    def test_run_refuses_in_stub(self):
        with self.assertRaises(netpan.NetpanError):
            netpan._run(["ls", "/"])

    def test_list_dir_empty(self):
        self.assertEqual(netpan.list_dir("/观云素材"), [])

    def test_logged_in_false(self):
        self.assertFalse(netpan.logged_in())

    def test_pull_upload_refused(self):
        with self.assertRaises(netpan.NetpanError):
            netpan.pull("/观云素材/a.jpg")
        with self.assertRaises(netpan.NetpanError):
            netpan.upload("/tmp/a.jpg", "/观云素材/03-成片")

    def test_share_degrades_to_pointer(self):
        self.assertEqual(netpan.share_link("/观云素材/a.jpg"),
                         netpan.pointer("/观云素材/a.jpg"))

    def test_take_link_pointer_vs_local(self):
        # 网盘指针 → 用时 mint(stub 退化成同指针,不损坏);本地 file:// 原样(不被当网盘路径污染)
        ptr = netpan.pointer("/观云素材/03-成片/x.mp4")
        self.assertEqual(netpan.take_link(ptr), ptr)
        self.assertEqual(netpan.take_link("file:///Users/x/a.jpg"), "file:///Users/x/a.jpg")


if __name__ == "__main__":
    unittest.main()
