"""红线 —— **本仓唯一保留的测试**。

为什么只留红线(2026-07-14 定死):

  **334 条单测全绿的时候,系统正在对运营撒谎。**

  今天真正抓到 bug 的,一条都不是靠测试:
    · 以运营的眼睛真读卡片   → 周报零数据编结论 / 补拍单给摄影师文件路径 / 拦住却甩堆栈
    · 以 agent 身份真去上班   → 干跑撒谎 / 出稿覆盖待审稿 / 待办让人做没有手能做的事
    · 真读一遍 API 返回       → link 字段形态 / note.desc / ModelNotOpen
  而我写的每一个"检查器",自己都有 bug —— **四次**。
  写测试、写探针、写审查器,**全都是"我预测系统会怎样"**,不是"系统真的被用了一次"。

  更毒的是:为了"可测",一切被写成纯函数 → **判断被从模型手里拿出来** → 测试驱动了导轨。
  `test_dispatch` 断言"cadence 会派这 4 条" —— 那条测试**就是把轮转规则焊死的钉子**。
  (那条 cadence 规则和那条测试,2026-07-14 一起删了。)

  **红线是唯一的例外**:它是"绝不能发生的事",**没法靠"用出来"验证**
  (你不能等 AI 内容漏标真发出去了才知道)。所以它必须有机器门守着。

  其余一切:**派子 agent 真跑**(真库 / 真 ARK / 真网盘),人当外部观察者验收。零 mock 零 stub。
"""
from __future__ import annotations

import ast
import importlib
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import config, guard, notes
from orchestrator.bitable import MaterialSource as MSrc, NoteFields as NF, NoteStatus as NS

ROOT = Path(__file__).resolve().parents[1]
PROD_BASE = "N9IVbi6pTatJG5sqyTTcc0vSn4g"
TEST_BASE = "ZhzJbfkOsafwevsWkW8cfoILnfb"


class R1_只写测试库(unittest.TestCase):
    """生产库 `N9IVbi` **焊死不碰,读也不行** —— 守卫必须在**任何 IO 之前**。"""

    def test_prod_base_write_is_refused(self):
        with self.assertRaises(guard.GuardError):
            guard.assert_base_allowed(PROD_BASE, True)

    def test_test_base_is_allowed(self):
        guard.assert_base_allowed(TEST_BASE, True)      # 不误伤

    def test_every_write_atom_guards_before_touching_any_io(self):
        """**守卫必须在任何 IO 之前**(不是"在写之前")。

        真事:老 `dispatch` 曾在守卫前先做了一次读库(`_open_slots`)——
        BASE_TOKEN 指向生产库时,**那次读会真的打到 N9IVbi**。生产库读也不碰。

        测法:把所有 IO 换成"一碰就炸",拿生产库 token 去调**每一个写原子** ——
        必须是 GuardError(守卫拦住了),不是 IOTouched(已经碰了库)。
        """
        from orchestrator import feishu_io

        class IOTouched(AssertionError):
            pass

        def boom(*a, **k):
            raise IOTouched("守卫还没拦住,就已经碰了 IO —— 这一下会打到生产库")

        写原子 = {
            "notes.new": lambda: notes.new("ootd号", "视频唯美OOTD"),
            "notes.write_draft": lambda: notes.write_draft("ootd号", "视频唯美OOTD", "标", "正文"),
            "notes.update": lambda: notes.update("recX", {NF.TITLE: "x"}),
        }
        orig = (config.BASE_TOKEN, config.TEST_MODE)
        try:
            config.BASE_TOKEN, config.TEST_MODE = PROD_BASE, True
            with mock.patch.object(feishu_io, "list_records", boom), \
                    mock.patch.object(feishu_io, "search_in", boom), \
                    mock.patch.object(feishu_io, "search_records", boom), \
                    mock.patch.object(feishu_io, "get_record", boom), \
                    mock.patch.object(feishu_io, "create_record", boom), \
                    mock.patch.object(feishu_io, "update_record", boom), \
                    mock.patch.object(feishu_io, "name_map", boom):
                for name, call in 写原子.items():
                    with self.subTest(原子=name), self.assertRaises(guard.GuardError):
                        call()
        finally:
            config.BASE_TOKEN, config.TEST_MODE = orig

    def test_no_prod_writing_script_exists(self):
        """**不留往生产库写的脚本。** 曾有个 `migrate_p2_to_prod.py`(零调用者)躺在仓里等人手滑。"""
        self.assertFalse((ROOT / "scripts" / "migrate_p2_to_prod.py").exists())


class R2_绝不自动发布(unittest.TestCase):
    """出稿一律止于『草稿待发』。发布是**人的动作**。"""

    def test_write_draft_always_lands_on_draft_pending(self):
        """落库状态写死成『草稿待发』,不是参数 —— agent 传不进别的状态。"""
        src = (ROOT / "orchestrator" / "notes.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "write_draft")
        # write_draft 里给 STATUS 赋的值必须是常量 NS.DRAFT_PENDING,不能是变量(否则可被传成『已发』)
        assigned = [v for n in ast.walk(fn) if isinstance(n, ast.Dict)
                    for k, v in zip(n.keys, n.values)
                    if isinstance(k, ast.Attribute) and k.attr == "STATUS"]
        self.assertTrue(assigned, "write_draft 没给状态赋值?")
        for v in assigned:
            self.assertTrue(isinstance(v, ast.Attribute) and v.attr == "DRAFT_PENDING",
                            "write_draft 的落库状态不是写死的『草稿待发』——它能被传成别的状态")

    def test_no_publish_verb_in_the_action_interface(self):
        """**agent 的手里根本没有"发布"这个动词**(物理上够不着,不是"记得别用")。
        也不许有"批准" —— 审批是人在 base 做的,给它 approve 动词它就能自己批自己的稿。"""
        from orchestrator import cli
        verbs = set(cli.build()._subparsers._group_actions[0].choices)  # type: ignore[attr-defined]
        for 禁 in ("publish", "approve", "note.approve", "publish.publish"):
            self.assertNotIn(禁, verbs, f"Action Interface 里冒出了「{禁}」动词")
        self.assertIn("publish.advance", verbs)   # 只到『待发布』的那只手还在(不误删)


class R3_绝不代勾AI声明(unittest.TestCase):
    """AI 像素 → 素材『来源=AI生成』→ 门要求声明 → **人勾**。机器绝不代勾。"""

    def test_agent_cannot_write_the_ai_declaration_field(self):
        """**新红线**(拆导轨后 agent 能直接改笔记字段了):它写 AI声明 必须被当场拦住。
        以前 harness 组字段,物理上不会写这个字段;现在 `note.update --set AI声明=true` 是一句话的事。"""
        with self.assertRaises(guard.GuardError):
            notes.update("recX", {NF.AI_DECLARED: True})

    def test_ai_material_without_declaration_is_refused(self):
        self.assertTrue(guard.ai_declaration_required([MSrc.AI, MSrc.REAL]))
        with self.assertRaises(guard.GuardError):
            guard.assert_ai_declared({NF.CODE: "含AI素材"}, ai_required=True)

    def test_all_real_shots_need_no_declaration(self):
        """全实拍 → 免勾(**不误伤**:天天误报,人就不看了)。"""
        self.assertFalse(guard.ai_declaration_required([MSrc.REAL, MSrc.REAL]))
        guard.assert_ai_declared({NF.CODE: "全实拍"}, ai_required=False)


class R4_provenance随像素出处(unittest.TestCase):
    """加工产物『来源』**随像素出处**,绝不给 agent 判断(这是合规,不是判断)。"""

    def test_pure_composition_stays_real(self):
        self.assertEqual(guard.derive_source([MSrc.REAL, MSrc.REAL], used_ai_generation=False), MSrc.REAL)

    def test_ai_generated_pixels_flip_to_ai(self):
        self.assertEqual(guard.derive_source([MSrc.REAL, MSrc.REAL], used_ai_generation=True), MSrc.AI)

    def test_any_ai_input_taints_the_output(self):
        self.assertEqual(guard.derive_source([MSrc.AI, MSrc.REAL], used_ai_generation=False), MSrc.AI)

    def test_ai_pixels_land_as_ai_even_if_the_agent_says_otherwise(self):
        """agent 说"这是实拍"也没用:落在 02-AI生成/ 的像素**强制** AI生成(就低不就高)。"""
        from orchestrator import feishu_io, ingest
        cap = {}
        with mock.patch.object(feishu_io, "create_record", lambda t, f: cap.update(f) or "rec1"):
            ingest.register("XX-260714-001", "形象图", "baidupan:/巧荷素材/02-AI生成/x.jpg",
                            source=MSrc.REAL)      # ← agent 硬说实拍
        self.assertEqual(cap["来源"], MSrc.AI, "AI 目录的像素被登记成了实拍 —— 会漏勾 AI 声明")


class R5_控量门且不许有旋钮(unittest.TestCase):
    """单号 ≤3 篇/天(平台风控)。**红线不许有旋钮** —— env 关得掉的不是红线,是建议。"""

    def test_quota_gate_refuses_at_limit(self):
        with self.assertRaises(guard.GuardError):
            guard.assert_publish_quota(config.PER_ACCOUNT_DAILY_PUBLISH)

    def test_quota_cannot_be_disabled_by_env(self):
        """实测过:`GY_ACCOUNT_DAILY_PUB=999` 曾让控量门放行 50 篇,**且不留任何痕迹**。"""
        old = os.environ.get("GY_ACCOUNT_DAILY_PUB")
        os.environ["GY_ACCOUNT_DAILY_PUB"] = "999"
        try:
            importlib.reload(config)
            self.assertEqual(config.PER_ACCOUNT_DAILY_PUBLISH, 3, "红线阈值被 env 改掉了")
        finally:
            os.environ.pop("GY_ACCOUNT_DAILY_PUB", None) if old is None else \
                os.environ.__setitem__("GY_ACCOUNT_DAILY_PUB", old)
            importlib.reload(config)

    def test_source_never_reads_env_for_the_quota(self):
        """连源码里都不许出现那个 env 读法 —— 否则下次有人"顺手"又给红线接回旋钮。"""
        src = (ROOT / "orchestrator" / "config.py").read_text(encoding="utf-8")
        self.assertNotIn("PER_ACCOUNT_DAILY_PUBLISH = int(os.environ", src)


class R6_防搬运门(unittest.TestCase):
    """爆款/真实帖只当情报,**只学结构、绝不抄原句**。

    ⚠️ 技能里写这句话**不够** —— 真跑实证:模型照样把爆款标题原封搬走。
    ⚠️ 拆导轨之后这道门换了形状,**新的失效方式**:
       harness 不再组 prompt,**它不知道 agent 看过什么**。
       要是让 agent 自己申报("我这条用了 writing-ootd-caption"),它打错一个字门就瞎了。
       **门必须自己去捞比对源。**
    """

    def test_verbatim_lift_is_refused(self):
        skill = (ROOT / "skills" / "writing-ootd-caption" / "SKILL.md").read_text(encoding="utf-8")
        stolen = re.sub(r"[\s\W_]+", "", skill)[200:225]        # 逐字搬技能里的真实帖
        with self.assertRaises(guard.GuardError):
            guard.assert_no_source_leak([skill], stolen)

    def test_original_output_passes(self):
        """**不误伤** —— 喊三次狼来了,这道门就没人看了。"""
        guard.assert_no_source_leak(["某爆款正文", "某爆款标题", "某技能 few-shot"],
                                    "OOTD｜粉罗载光\n\n光落在衣上，风把影子摇醒。\n\n#汉服")

    def test_gate_fetches_its_own_sources_never_asks_the_agent(self):
        """**结构不变式:比对源不许来自调用方(agent)的入参。**

        `write_draft` 交给门的那个参数,必须是 `_leak_sources(...)` 的返回值 ——
        harness 自己去捞的。**只要它变成一个函数入参(哪怕叫 `sources=`),这道门就有了
        一个"被监管者自己填的申报表"入口,当场作废。**
        """
        tree = ast.parse((ROOT / "orchestrator" / "notes.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "write_draft")
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "assert_no_source_leak"]
        self.assertTrue(calls, "write_draft 没有过防搬运门")
        for c in calls:
            src_arg = c.args[0]
            self.assertIsInstance(src_arg, ast.Call, "比对源不是 harness 自己捞的(应是 _leak_sources(...))")
            self.assertEqual(getattr(src_arg.func, "id", ""), "_leak_sources")
            for n in ast.walk(src_arg):
                if isinstance(n, ast.Name):
                    self.assertNotIn(n.id, params - {"account", "content_type", "brand"},
                                     f"比对源掺进了 agent 能自由填的入参「{n.id}」—— 门可以被它糊弄")

    def test_skill_declared_but_missing_explodes(self):
        """声明了 gen_skill 却装不上 → **炸**。静默跳过 = 门拿不到真实帖 = 门瞎了还假装在守。"""
        from orchestrator import feishu_io
        with mock.patch.object(feishu_io, "list_records", lambda t, **k: []), \
                mock.patch.object(notes, "_gen_skill_of", lambda *a, **k: "不存在的技能xyz"):
            with self.assertRaises(notes.SkillMissing):
                notes._leak_sources("ootd号", "视频唯美OOTD")

    def test_every_real_playbook_resolves_its_skill(self):
        """真账号声明里每个模式的 gen_skill 都装得上(否则那个模式的防搬运门是瞎的)。"""
        from orchestrator import accounts
        for name, acc in accounts.load_all("巧荷").items():
            if not acc or acc.error:
                continue
            for pb in acc.playbooks():
                gs = accounts.gen_skill_of(pb)
                if gs:
                    self.assertTrue((ROOT / "skills" / gs / "SKILL.md").exists(),
                                    f"{name} 的技能「{gs}」装不上 —— 它的防搬运门会瞎")


class R7_零素材门(unittest.TestCase):
    """一张图/视频都没挂的稿,**小红书物理上发不出去** —— 拦在待发布门外,
    别放进去再让运营到最后一步扑空。"""

    def test_zero_material_is_refused(self):
        with self.assertRaises(guard.GuardError):
            guard.assert_has_material(0, "空稿")

    def test_with_material_passes(self):
        guard.assert_has_material(3, "正常稿")


class R8_绝不覆盖运营待审的稿(unittest.TestCase):
    """『待出文案』= 派活占位(还没内容)→ 可推进;
    『草稿待发』= **人正等着审** → 再写一条 update 上去 = **把他等着审的稿悄悄换掉**。
    覆盖别人正在等的东西,任何时候都不叫"复用"。"""

    def _base(self, status):
        return {"笔记表": [{"record_id": "recOld", "fields": {
                    NF.STATUS: status, NF.TITLE: "运营正在审的那条",
                    NF.ACCOUNT: [{"record_ids": ["recA"]}],
                    NF.CONTENT_TYPE: [{"record_ids": ["recC"]}]}}],
                "账号表": [{"record_id": "recA", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recC", "fields": {"内容类型名": "视频唯美OOTD"}}],
                "灵感库": []}

    def _run(self, status):
        from orchestrator import feishu_io
        base = self._base(status)
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_in", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "update_record", lambda t, rid, f: cap.update(updated=rid)), \
                mock.patch.object(feishu_io, "create_record", lambda t, f: cap.update(created=True) or "recNew"):
            return notes.write_draft("ootd号", "视频唯美OOTD", "新标题", "全新的正文内容"), cap

    def test_pending_review_draft_is_never_overwritten(self):
        with self.assertRaises(notes.DraftPending):
            self._run(NS.DRAFT_PENDING)

    def test_placeholder_is_still_promoted(self):
        """别把防覆盖修成"什么都不敢做":占位(没内容)照旧推进,不新建重复行。"""
        r, cap = self._run(NS.NEED_COPY)
        self.assertEqual(r["note_id"], "recOld")
        self.assertNotIn("created", cap)


class R9_定时器的手只碰自己的行(unittest.TestCase):
    """crontab 是**用户机器上的公共设施**,不是 agent 的私产。
    它只许碰自己写的(带 `# gy-agent` 标记的)行 —— 别人的 cron 一个字都不许动。"""

    def test_foreign_cron_lines_survive(self):
        from orchestrator import schedule
        别人的 = ["0 3 * * * /usr/local/bin/backup-my-photos.sh",
                  "*/5 * * * * ping -c1 example.com"]
        写出去的: list = []
        with mock.patch.object(schedule, "_read_raw",
                               lambda: 别人的 + ["0 8 * * * wake-agent # gy-agent:早班:每天看看有没有活"]), \
                mock.patch.object(schedule, "_write_raw", lambda ls: 写出去的.extend(ls)):
            schedule.remove("早班")
        for ln in 别人的:
            self.assertIn(ln, 写出去的, "撤自己的班时,把用户自己的 cron 行也删了")
        self.assertFalse([x for x in 写出去的 if "gy-agent:早班" in x], "自己的班没撤掉")


if __name__ == "__main__":
    unittest.main()
