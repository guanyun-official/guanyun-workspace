"""回归锁:精简后的 ar_check 必须与引擎同源、且继续验证精简骨架的命门,不被静默改回/掏空。

大刀阔斧后老锁(materialize_day/account_kernel/media/usage/近30天趋势)随重层一起去;
新锁盯住精简骨架的三件命门:第一目标 A 可跑、精简唯一源、红线不可绕。零网络(只读源码 + md frontmatter)。"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchestrator import accounts  # noqa: E402

_DEAD_GLOB = re.compile(r"""glob\(\s*['"]\*\.strategy\.json""")


def _ar_src() -> str:
    return (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")


class TestArCheckSync(unittest.TestCase):
    def test_no_dead_strategy_json_glob(self):
        """ar_check 不得再 glob 已废弃的 *.strategy.json 后缀数声明。"""
        self.assertIsNone(_DEAD_GLOB.search(_ar_src()),
                          "ar_check 仍在 glob 已废弃的 *.strategy.json——应复用 accounts.load_all 同源计数")

    def test_ar_check_reuses_engine_loader(self):
        """ar_check 与 planner/薄执行器同源:复用 orchestrator.accounts,不另写文件约定。"""
        self.assertIn("accounts", _ar_src(),
                      "ar_check 应复用 orchestrator.accounts,避免声明格式漂移")

    def test_ar_check_guards_declaration_health(self):
        """ar_check 须接入 accounts.problems,坏 frontmatter 才会验收报红。"""
        self.assertIn("problems", _ar_src(),
                      "ar_check 未接入 accounts.problems——坏 {号}.md 声明不会被验收发现")

    def test_engine_sees_declarations(self):
        """数据前提:引擎从 {号}.md 至少解析出 3 个非空 strategy 声明。"""
        declared = {n: a.strategy for n, a in accounts.load_all("巧荷").items() if a.strategy}
        self.assertGreaterEqual(len(declared), 3,
                                f"accounts.load_all 只解析出 {len(declared)} 个 strategy 声明,ar_check 需 >=3")

    def test_ar_check_verifies_thin_executor_A(self):
        """精简命门①:ar_check 必须真跑薄执行器验第一目标 A,否则骨架断了也误报 SCORE=100。"""
        src = _ar_src()
        self.assertIn("draft", src)
        self.assertIn("generate_draft", src)
        self.assertIn("few-shot", src, "ar_check 未验证 gen_skill few-shot 真进生成(A 的核心缺口)")

    def test_ar_check_guards_single_source(self):
        """精简命门②:ar_check 必须校 Base 账号表 ↔ workspace 声明,锁住账号真相不双写。"""
        src = _ar_src()
        self.assertIn("账号表", src)
        self.assertIn("load_all", src)
        self.assertIn("唯一源", src)

    def test_ar_check_guards_redline(self):
        """精简命门③:ar_check 必须锁红线——AI声明门 + 薄执行器过 base 闸/只到草稿待发。"""
        src = _ar_src()
        self.assertIn("assert_ai_declared", src)
        self.assertIn("assert_base_allowed", src)
        self.assertIn("红线", src)


if __name__ == "__main__":
    unittest.main()
