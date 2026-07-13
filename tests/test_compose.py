"""加工执行(compose.py):拼图(PIL 确定性)+ 保守 decide 规则。零网络(grid/decide 纯本地)。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image  # noqa: E402
from orchestrator import compose  # noqa: E402


class TestGridCompose(unittest.TestCase):
    def test_makes_one_image_from_many(self):
        d = Path(tempfile.mkdtemp())
        paths = []
        for i in range(3):
            p = d / f"{i}.jpg"
            Image.new("RGB", (100, 80), (i * 50, 10, 10)).save(p)
            paths.append(str(p))
        out = str(d / "grid.jpg")
        compose.grid_compose(paths, out)
        self.assertTrue(Path(out).exists())
        w, h = Image.open(out).size
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            compose.grid_compose([], "/tmp/none.jpg")


class TestSimpleDecide(unittest.TestCase):
    def test_proposes_grid_for_dapei(self):
        d = compose.simple_decide(["a", "b", "c"], mode="搭配图")
        self.assertTrue(d["加工"])
        self.assertEqual(d["kind"], "拼图")
        self.assertEqual(d["inputs"], ["a", "b", "c"])

    def test_no_process_for_non_dapei_mode(self):
        self.assertFalse(compose.simple_decide(["a", "b"], mode="图文OOTD")["加工"])

    def test_no_process_single_material(self):
        self.assertFalse(compose.simple_decide(["a"], mode="搭配图")["加工"])   # <2 不拼


if __name__ == "__main__":
    unittest.main()
