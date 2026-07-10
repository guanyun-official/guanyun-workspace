"""回归锁:ar_check 的「strategy 声明」计数必须与引擎(accounts.load_all)同源。

历史 bug:候选C 重构把 {号}.strategy.json 塌成 {号}.md 的 JSON frontmatter,
planner 随之迁到 accounts.load_all;但 ar_check.py 仍按 *.strategy.json 文件后缀数,
命中 0 个 → P3「每天发什么」+「模式泛化」失败 → SCORE 从 100 掉到 80。
本测试锁住:验收脚本不得再按已废弃的文件后缀数声明,必须复用引擎加载器。
零网络(只读源码 + 读 md frontmatter)。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchestrator import accounts  # noqa: E402

# 匹配对已废弃后缀的实际 glob 调用(任意引号);注释里提及历史 bug 不算(允许文档化)。
_DEAD_GLOB = re.compile(r"""glob\(\s*['"]\*\.strategy\.json""")


class TestArCheckSync(unittest.TestCase):
    def test_no_dead_strategy_json_glob(self):
        """ar_check 不得再 glob *.strategy.json 数声明(候选C 后该后缀已不存在)。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIsNone(
            _DEAD_GLOB.search(src),
            "ar_check 仍在 glob 已废弃的 *.strategy.json 后缀数声明——应复用 accounts.load_all 同源计数",
        )

    def test_ar_check_reuses_engine_loader(self):
        """强制 ar_check 与 planner 同源:引用 accounts 加载器,而非另写一套文件约定。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn(
            "accounts", src,
            "ar_check 应复用 orchestrator.accounts(与 planner 同源),避免声明格式漂移",
        )

    def test_ar_check_guards_declaration_health(self):
        """ar_check 须接入 accounts.problems,坏 frontmatter 才会验收报红(否则健壮性形同虚设)。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn(
            "problems", src,
            "ar_check 未接入 accounts.problems——坏 {号}.md 声明不会被验收发现",
        )

    def test_engine_sees_declarations(self):
        """数据前提:引擎从 {号}.md 至少解析出 3 个非空 strategy 声明(ar_check 通过的门槛)。"""
        declared = {n: a.strategy for n, a in accounts.load_all("观云").items() if a.strategy}
        self.assertGreaterEqual(
            len(declared), 3,
            f"accounts.load_all 只解析出 {len(declared)} 个 strategy 声明,ar_check 需 >=3",
        )

    def test_ar_check_requires_daily_plan_materialization(self):
        """“每天发什么”不能只会算报告；成熟度门必须锁住 Planner→Note 接线。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn(
            "materialize_day",
            src,
            "ar_check 未验证 Planner→Note 物化能力，排产与状态推进断线也会误报 SCORE=100",
        )
        self.assertIn(
            "preflight = materialize_day",
            (ROOT / "orchestrator" / "run.py").read_text(encoding="utf-8"),
            "daily 排产必须通过 engine preflight 在单 writer 锁内执行",
        )

    def test_ar_check_requires_account_kernel_audit(self):
        """账号表与 workspace Account data 不能双写真相；成熟度门要锁住 SourceOwnership。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn("account_kernel", src)
        self.assertIn("build_audit", src)
        self.assertIn("账号内核", src)
        self.assertIn("唯一源", src)

    def test_ar_check_requires_base_workbench_dry_run(self):
        """Base 重构不能靠手工点 UI；成熟度门要锁住 BaseWorkbench dry-run。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn("base_workbench", src)
        self.assertIn("build_plan", src)
        self.assertIn("has_blocking_drift", src)
        self.assertIn("Base工作台", src)

    def test_ar_check_requires_media_task_gate_for_ai_editing(self):
        """AI剪不能退回“跳过/伪装成片”；成熟度门要锁住 MediaTask 与 ready gate。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn("media_processing.ensure_task", src)
        self.assertIn("READY_NOTE", src)
        self.assertIn("approved_material_codes", src)

    def test_ar_check_requires_usage_projection_drift_guard(self):
        """usage ledger 是唯一真值，ar_check 必须锁住 Bitable 投影对账告警。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn("_usage_projection_drift", src)
        self.assertIn("usage账本漂移", src)
        self.assertIn("note_clips", src)

    def test_ar_check_requires_playbook_performance_trends(self):
        """方法论表现不能退回纯静态均值；成熟度门要锁住时间窗趋势。"""
        src = (ROOT / "scripts" / "ar_check.py").read_text(encoding="utf-8")
        self.assertIn("近30天", src)
        self.assertIn("周环比", src)
        self.assertIn("PUBLISHED_AT", src)


if __name__ == "__main__":
    unittest.main()
