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

  **红线是唯一的例外**:它是"绝不能发生的事",**没法靠"用出来"验证**
  (你不能等 AI 内容漏标真发出去了才知道)。所以它必须有机器门守着。

  其余一切:**派子 agent 真跑**(真库 / 真 ARK / 真网盘),人当外部观察者验收。零 mock 零 stub。
"""
from __future__ import annotations

import importlib
import os
import re
import unittest
from pathlib import Path

from orchestrator import config, draft, guard, processing
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

    def test_dispatch_guards_before_touching_any_io(self):
        """**守卫必须在任何 IO 之前**(不是"在写之前")。

        真事:`dispatch` 曾经在守卫前面先做了一次 `_open_slots()`(读库)——
        于是 BASE_TOKEN 指向生产库时,**那次读会真的打到 N9IVbi**。生产库读也不碰。
        测法:把所有 IO 换成"一碰就炸",拿生产库 token 去写 —— 必须是 GuardError,不是 IOTouched。"""
        from unittest import mock
        from orchestrator import dispatch, feishu_io

        class IOTouched(AssertionError):
            pass

        def boom(*a, **k):
            raise IOTouched("守卫还没拦住,就已经碰了 IO —— 这一下会打到生产库")

        orig = (config.BASE_TOKEN, config.TEST_MODE)
        try:
            config.BASE_TOKEN, config.TEST_MODE = PROD_BASE, True
            with mock.patch.object(feishu_io, "list_records", boom), \
                    mock.patch.object(feishu_io, "search_in", boom), \
                    mock.patch.object(feishu_io, "search_records", boom), \
                    mock.patch.object(feishu_io, "create_record", boom), \
                    mock.patch.object(feishu_io, "name_map", boom):
                with self.assertRaises(guard.GuardError):
                    dispatch.dispatch("巧荷", write=True)
        finally:
            config.BASE_TOKEN, config.TEST_MODE = orig

    def test_no_prod_writing_script_exists(self):
        """**不留往生产库写的脚本。** 曾有个 `migrate_p2_to_prod.py`(零调用者)躺在仓里等人手滑。"""
        self.assertFalse((ROOT / "scripts" / "migrate_p2_to_prod.py").exists())


class R2_绝不自动发布(unittest.TestCase):
    """出稿一律止于『草稿待发』。发布是**人的动作**。"""

    def test_generation_always_stops_at_draft_pending(self):
        from orchestrator import accounts
        for name, acc in accounts.load_all("巧荷").items():
            if not acc or acc.error:
                continue
            for pb in acc.playbooks():
                ct = pb.get("content_type") or pb.get("id")
                f = draft.generate_draft(name, llm_mode="stub", content_type=ct)["note_fields"]
                self.assertEqual(f[NF.STATUS], NS.DRAFT_PENDING, f"{name}/{ct} 越过了人审门")


class R3_绝不代勾AI声明(unittest.TestCase):
    """AI 像素 → 素材『来源=AI生成』→ 门要求声明 → **人勾**。机器绝不代勾。"""

    def test_generation_never_self_declares(self):
        from orchestrator import accounts
        for name, acc in accounts.load_all("巧荷").items():
            if not acc or acc.error:
                continue
            for pb in acc.playbooks():
                ct = pb.get("content_type") or pb.get("id")
                f = draft.generate_draft(name, llm_mode="stub", content_type=ct)["note_fields"]
                self.assertNotIn(NF.AI_DECLARED, f, f"{name}/{ct} 自带了 AI 声明")

    def test_ai_material_without_declaration_is_refused(self):
        self.assertTrue(guard.ai_declaration_required([MSrc.AI, MSrc.REAL]))
        with self.assertRaises(guard.GuardError):
            guard.assert_ai_declared({NF.CODE: "含AI素材"}, ai_required=True)

    def test_all_real_shots_need_no_declaration(self):
        """全实拍 → 免勾(**不误伤**:天天误报,人就不看了)。"""
        self.assertFalse(guard.ai_declaration_required([MSrc.REAL, MSrc.REAL]))
        guard.assert_ai_declared({NF.CODE: "全实拍"}, ai_required=False)


class R4_provenance随像素出处(unittest.TestCase):
    """成片『来源』**随像素出处**,绝不给模型判断(这是合规,不是判断)。"""

    def test_pure_composition_stays_real(self):
        self.assertEqual(processing.derive_source([MSrc.REAL, MSrc.REAL], used_ai_generation=False),
                         MSrc.REAL)

    def test_ai_generated_pixels_flip_to_ai(self):
        self.assertEqual(processing.derive_source([MSrc.REAL, MSrc.REAL], used_ai_generation=True),
                         MSrc.AI)

    def test_any_ai_input_taints_the_output(self):
        self.assertEqual(processing.derive_source([MSrc.AI, MSrc.REAL], used_ai_generation=False),
                         MSrc.AI)


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
    """爆款只当情报,**只学结构、绝不抄原句**。

    ⚠️ 技能里写这句话**不够** —— 真跑实证:模型照样把爆款标题原封搬走。
    **门必须守住 LLM 眼睛看得见的一切**:灵感标题 + 爆款正文 + 技能 few-shot 真实帖。
    """

    def test_verbatim_lift_is_refused(self):
        skill = draft.load_gen_skill("writing-ootd-caption")
        stolen = re.sub(r"[\s\W_]+", "", skill)[200:225]        # 逐字搬技能里的真实帖
        with self.assertRaises(guard.GuardError):
            guard.assert_no_source_leak([skill], stolen)

    def test_original_output_passes(self):
        """**不误伤** —— 喊三次狼来了,这道门就没人看了。"""
        guard.assert_no_source_leak(["某爆款正文", "某爆款标题", "某技能 few-shot"],
                                    "OOTD｜粉罗载光\n\n光落在衣上，风把影子摇醒。\n\n#汉服")

    def test_gate_covers_every_external_text_that_entered_the_prompt(self):
        """**结构不变式:进了 prompt 的外来文本,一个不落地交给门。**
        门被修过两次:第一次漏了 few-shot 真实帖(LLM 眼前最好抄的东西);
        第二次我误判"正文不进 prompt 所以搬不了" —— 而正文正是当情报进 prompt 的。"""
        import ast
        tree = ast.parse((ROOT / "orchestrator" / "draft.py").read_text(encoding="utf-8"))
        external = {"skill_text", "title_seed", "source_text"}
        alias: dict[str, set] = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and isinstance(n.value, (ast.List, ast.Tuple)):
                elts = {e.id for e in n.value.elts if isinstance(e, ast.Name)}
                for t in n.targets:
                    if isinstance(t, ast.Name) and elts:
                        alias.setdefault(t.id, set()).update(elts)

        def names_of(fn: str) -> set:
            got: set = set()

            def walk(node):
                if isinstance(node, ast.Name):
                    got.add(node.id)
                    got.update(alias.get(node.id, ()))
                for ch in ast.iter_child_nodes(node):
                    walk(ch)
            for n in ast.walk(tree):
                if isinstance(n, ast.Call):
                    f = n.func
                    if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) == fn:
                        for a in list(n.args) + [k.value for k in n.keywords]:
                            walk(a)
            return got

        into_prompt = names_of("compose_prompt") & external
        into_gate = names_of("assert_no_source_leak") & external
        self.assertLessEqual(into_prompt, into_gate,
                             f"这些外来文本进了 prompt 却没进防搬运门:{into_prompt - into_gate}")


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
    『草稿待发』= **人正等着审** → 再出一条 update 上去 = **把他等着审的稿悄悄换掉**。
    覆盖别人正在等的东西,任何时候都不叫"复用"。"""

    def _run(self, status):
        from unittest import mock
        from orchestrator import feishu_io
        base = {"笔记表": [{"record_id": "recOld", "fields": {
                    NF.STATUS: status, NF.TITLE: "运营正在审的那条",
                    NF.ACCOUNT: [{"record_ids": ["recA"]}],
                    NF.CONTENT_TYPE: [{"record_ids": ["recC"]}]}}],
                "账号表": [{"record_id": "recA", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recC", "fields": {"内容类型名": "视频唯美OOTD"}}]}
        r = draft.generate_draft("ootd号", llm_mode="stub", content_type="视频唯美OOTD")
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_in", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "update_record", lambda t, rid, f: cap.update(updated=rid)), \
                mock.patch.object(feishu_io, "create_record", lambda t, f: cap.update(created=True) or "recNew"):
            return draft.create_draft_note(r), cap

    def test_pending_review_draft_is_never_overwritten(self):
        with self.assertRaises(draft.DraftPending):
            self._run(NS.DRAFT_PENDING)

    def test_placeholder_is_still_promoted(self):
        """别把防覆盖修成"什么都不敢做":占位(没内容)照旧推进。"""
        rid, cap = self._run(NS.NEED_COPY)
        self.assertEqual(rid, "recOld")
        self.assertNotIn("created", cap)


class R9_技能装不上就炸(unittest.TestCase):
    """声明了 gen_skill 却装不上 → **炸在出稿前**,绝不静默返回 ""。
    静默 = LLM 零技能、零 few-shot 裸写,产出照样有,只是悄悄退化成通用口水文,**永不作声**。"""

    def test_declared_but_missing_skill_raises(self):
        with self.assertRaises(draft.SkillMissing):
            draft.load_gen_skill("不存在的技能xyz")

    def test_no_skill_declared_is_legal(self):
        self.assertEqual(draft.load_gen_skill(""), "")

    def test_every_real_playbook_resolves_its_skill(self):
        from orchestrator import accounts
        for name, acc in accounts.load_all("巧荷").items():
            if not acc or acc.error:
                continue
            for pb in acc.playbooks():
                gs = accounts.gen_skill_of(pb)
                if gs:
                    self.assertTrue(draft.load_gen_skill(gs).strip(), f"{name} 的技能「{gs}」装不上")


if __name__ == "__main__":
    unittest.main()
