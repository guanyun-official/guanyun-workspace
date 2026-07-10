"""薄执行器(第一目标 A 的 walking skeleton)契约:
声明 → 该号 gen_skill 的 SKILL.md(真实帖 few-shot)→ 组稿 → 红线闸 → 一条「草稿待发」待审笔记。

全离线(stub、不触网、零成本):只证明管道成形与红线不可绕,不证明 LLM 文案质量。
真链(--llm real 写测试库)是里程碑手工验证,不进 keep 门。"""
from __future__ import annotations

import unittest

from orchestrator import config, draft
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS
from orchestrator.guard import GuardError


class LoadGenSkill(unittest.TestCase):
    def test_reads_local_skill_fewshot(self):
        """补缺口:gen_skill 不再只是标签——其 SKILL.md(含该号真实历史帖 few-shot)被真加载。"""
        text = draft.load_gen_skill("writing-ootd-caption")
        self.assertIn("OOTD｜蓝罗裁夏", text)  # ootd号 真实帖 few-shot,证明确实读到了技能正文

    def test_missing_skill_returns_empty(self):
        self.assertEqual(draft.load_gen_skill("不存在的技能xyz"), "")

    def test_empty_name_returns_empty(self):
        self.assertEqual(draft.load_gen_skill(""), "")


class GenerateDraft(unittest.TestCase):
    def test_composes_declaration_and_fewshot(self):
        """ootd号:账号画像 + 其 gen_skill few-shot 都进 prompt;gen_skill/playbook 正确解析。"""
        r = draft.generate_draft("ootd号", llm_mode="stub")
        self.assertEqual(r["account"], "ootd号")
        self.assertEqual(r["gen_skill"], "writing-ootd-caption")
        self.assertEqual(r["playbook_id"], "视频唯美OOTD")
        self.assertTrue(r["skill_loaded"])
        self.assertIn("OOTD｜蓝罗裁夏", r["prompt"])   # few-shot 进稿
        self.assertIn("服装设计师", r["prompt"])         # 画像 profile 进稿
        self.assertTrue(r["draft_text"].strip())

    def test_note_fields_are_review_pending_row(self):
        """产出的笔记字段 = 一条『草稿待发』待人审行,账号/内容类型/方法论/草稿/标题齐备。"""
        f = draft.generate_draft("ootd号", llm_mode="stub")["note_fields"]
        self.assertEqual(f[NF.ACCOUNT], "ootd号")
        self.assertEqual(f[NF.STATUS], NS.DRAFT_PENDING)  # 草稿待发=人审卡点,不越过
        self.assertEqual(f[NF.CONTENT_TYPE], "视频唯美OOTD")
        self.assertEqual(f[NF.PLAYBOOK], "视频唯美OOTD")
        self.assertTrue(f[NF.DRAFT].strip())
        self.assertTrue(f[NF.TITLE].strip())
        self.assertNotIn(NF.AI_DECLARED, f)  # AI 声明是人手勾,执行器绝不代置

    def test_unknown_account_raises(self):
        with self.assertRaises(ValueError):
            draft.generate_draft("不存在的号", llm_mode="stub")


class CreateDraftNoteRedline(unittest.TestCase):
    def test_blocks_prod_base_under_test_mode(self):
        """红线:TEST_MODE 下写库闸拒生产 Base(闸先抛,根本触不到网络)。"""
        r = draft.generate_draft("ootd号", llm_mode="stub")
        orig_token, orig_mode = config.BASE_TOKEN, config.TEST_MODE
        try:
            config.BASE_TOKEN = config.PROD_BASE
            config.TEST_MODE = True
            with self.assertRaises(GuardError):
                draft.create_draft_note(r)
        finally:
            config.BASE_TOKEN, config.TEST_MODE = orig_token, orig_mode


if __name__ == "__main__":
    unittest.main()
