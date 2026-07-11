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


class CreateDraftNoteLinkResolution(unittest.TestCase):
    """回归锁:账号/内容类型是 link 字段,写库前名字→record_id,不再把字符串塞进 link 字段炸写。"""

    def test_resolves_account_and_content_type_to_record_ids(self):
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("ootd号", llm_mode="stub")
        fake = {"账号表": [{"record_id": "recACC", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recCT", "fields": {"内容类型名": "视频唯美OOTD"}}]}
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t: fake.get(t, [])), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: cap.update(fields=fields) or "recNEW"):
            rid = draft.create_draft_note(r)
        self.assertEqual(rid, "recNEW")
        self.assertEqual(cap["fields"][NF.ACCOUNT], ["recACC"])       # link 收 record_id 列表,非字符串
        self.assertEqual(cap["fields"][NF.CONTENT_TYPE], ["recCT"])
        self.assertEqual(cap["fields"][NF.STATUS], NS.DRAFT_PENDING)

    def test_drops_unresolvable_link_instead_of_crashing(self):
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("ootd号", llm_mode="stub")
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t: []), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: cap.update(fields=fields) or "recNEW"):
            draft.create_draft_note(r)
        self.assertNotIn(NF.ACCOUNT, cap["fields"])      # 孤儿名挂不上就不写 link,不炸写
        self.assertNotIn(NF.CONTENT_TYPE, cap["fields"])


class SelectAndAttachMaterials(unittest.TestCase):
    """#32:薄执行器选素材(类型 ∈ material_needs + 已拍 + 赛道)挂进笔记表·关联素材。"""

    def test_select_by_type_and_shot_status(self):
        from unittest import mock
        from orchestrator import feishu_io
        mats = [
            {"record_id": "recV", "fields": {"类型": "上身视频", "拍摄状态": "已拍"}},
            {"record_id": "recImg", "fields": {"类型": "上身图", "拍摄状态": "已拍"}},
            {"record_id": "recTodo", "fields": {"类型": "上身视频", "拍摄状态": "待拍"}},
        ]
        with mock.patch.object(feishu_io, "list_records", lambda t: mats):
            ids = draft.select_materials(["上身视频"])
        self.assertEqual(ids, ["recV"])  # 只 上身视频 且 已拍

    def test_select_respects_track_tag(self):
        """适用账号显式标了别号→排除;没标→可用(赛道投影)。"""
        from unittest import mock
        from orchestrator import feishu_io
        mats = [
            {"record_id": "recOwn", "fields": {"类型": "上身视频", "拍摄状态": "已拍",
                                               "适用账号": [{"record_ids": ["recOOTD"]}]}},
            {"record_id": "recOther", "fields": {"类型": "上身视频", "拍摄状态": "已拍",
                                                 "适用账号": [{"record_ids": ["recX"]}]}},
            {"record_id": "recUntagged", "fields": {"类型": "上身视频", "拍摄状态": "已拍"}},
        ]
        with mock.patch.object(feishu_io, "list_records", lambda t: mats):
            ids = draft.select_materials(["上身视频"], account_rec_id="recOOTD")
        self.assertIn("recOwn", ids)
        self.assertIn("recUntagged", ids)
        self.assertNotIn("recOther", ids)

    def test_create_draft_note_attaches_materials(self):
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("ootd号", llm_mode="stub")  # material_needs=[上身视频]
        fake = {"账号表": [{"record_id": "recACC", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recCT", "fields": {"内容类型名": "视频唯美OOTD"}}],
                "素材表": [{"record_id": "recV", "fields": {"类型": "上身视频", "拍摄状态": "已拍"}}]}
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t: fake.get(t, [])), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: cap.update(fields=fields) or "recN"):
            draft.create_draft_note(r)
        self.assertEqual(cap["fields"][NF.LINKED_MATERIALS], ["recV"])  # 素材挂进关联素材

    def test_no_candidate_no_crash(self):
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("ootd号", llm_mode="stub")
        cap = {}
        with mock.patch.object(feishu_io, "list_records",
                               lambda t: {"账号表": [{"record_id": "recA", "fields": {"账号名": "ootd号"}}]}.get(t, [])), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: cap.update(fields=fields) or "recN"):
            draft.create_draft_note(r)
        self.assertNotIn(NF.LINKED_MATERIALS, cap["fields"])  # 无候选不挂,不炸


class IngestToSelectRoundtrip(unittest.TestCase):
    """摄入→选 端到端契约:ingest.register 登记的素材(类型+适用账号+已拍)能被 draft.select_materials 选到。"""

    def test_registered_material_is_selectable(self):
        from unittest import mock
        from orchestrator import feishu_io
        import scripts.ingest as ing
        captured = {}
        with mock.patch.object(feishu_io, "create_record", lambda t, f: captured.update(f) or "recNEW"):
            ing.register("SC-测试", "上身视频", "/x/v.mp4", accounts=["recOOTD"])
        self.assertEqual(captured["类型"], "上身视频")       # register 写的选素材 key
        self.assertEqual(captured["拍摄状态"], "已拍")        # 摄入即已拍→可选
        self.assertEqual(captured["适用账号"], ["recOOTD"])   # 赛道投影,不挂衣服
        self.assertNotIn("关联衣服", captured)                # §4:素材不挂衣服
        # 这条素材喂给 select_materials 应被 ootd号 选中
        mat_rec = {"record_id": "recNEW", "fields": captured}
        with mock.patch.object(feishu_io, "list_records", lambda t: [mat_rec]):
            ids = draft.select_materials(["上身视频"], account_rec_id="recOOTD")
        self.assertEqual(ids, ["recNEW"])


class ClothesGrounding(unittest.TestCase):
    """#35 防编造:绑定真实衣服→注入其 know-how;没绑→prompt 含禁编造指令(实测发现官号凭空编产品)。"""

    def test_bound_clothes_injected(self):
        r = draft.generate_draft("官号@巧荷·东方美学", llm_mode="stub", clothes="GY-003")
        self.assertTrue(r["clothes_grounded"])
        self.assertIn("紫藤", r["prompt"])            # GY-003 紫藤烟雨真实 know-how 进 prompt
        self.assertIn("严格以此为准", r["prompt"])     # 防编造强约束

    def test_unbound_forbids_fabrication(self):
        r = draft.generate_draft("官号@巧荷·东方美学", llm_mode="stub")  # 没绑衣服
        self.assertFalse(r["clothes_grounded"])
        self.assertIn("严禁编造", r["prompt"])         # 没绑就禁编造具体产品/朝代

    def test_missing_clothes_code_not_grounded(self):
        r = draft.generate_draft("ootd号", llm_mode="stub", clothes="GY-不存在")
        self.assertFalse(r["clothes_grounded"])        # 编号不存在=没绑,不炸


if __name__ == "__main__":
    unittest.main()
