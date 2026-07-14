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
        self.assertIn("蓝罗裁夏", text)   # ootd号 真实帖 few-shot,证明确实读到了技能正文
        self.assertIn("逐字稿", text)     # 合并后:技能含逐字稿配方(不只短标题)

    def test_declared_but_missing_skill_raises_not_silently_empty(self):
        """**报了名字却装不上 = 炸**(2026-07-14 人眼审)。

        这条测试的上一版是 `assertEqual(load_gen_skill('不存在的技能xyz'), "")` ——
        它**把 bug 焊死在了绿门里**:文件不存在就静默给 "",于是 compose_prompt(skill_text="")
        → **LLM 零技能、零 few-shot 裸写**,而整条链路一声不吭,产出照样有,只是悄悄退化成通用口水文。
        "每个模式都有专门技能写文案"这句话会当场变成谎话,且没有任何人会发现。
        测试该锁**正确行为**,不是锁我当初图省事的那个假设。"""
        with self.assertRaises(draft.SkillMissing):
            draft.load_gen_skill("不存在的技能xyz")

    def test_no_skill_declared_is_legal(self):
        """没声明 gen_skill(空名)→ 合法,返 ""(该模式本就不挂技能)。别把"没声明"和"装不上"混为一谈。"""
        self.assertEqual(draft.load_gen_skill(""), "")

    # 「全号×全模式的 gen_skill 都装得上」已由 test_skills_lock.test_every_gen_skill_resolves_from_single_source
    # 守着(真读 accounts/,非 mock)。**不在这儿再写一条重复的**——重复的测试和死码一样,是负债。


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


class ComposePromptDefersFormatToSkill(unittest.TestCase):
    """回归锁(逐字稿丢失 bug):薄执行器不得硬编码『视频配文就短』这类模式格式假设——
    篇幅/结构一律由 gen_skill 的 SKILL.md 说了算(ootd 视频要 25-30s 逐字稿,不是一句意境)。
    引擎零模式假设,格式让位给技能。"""

    def test_no_hardcoded_short_video_assumption(self):
        p = draft.generate_draft("ootd号", llm_mode="stub")["prompt"]  # 视频唯美OOTD
        self.assertNotIn("视频配文就短", p)      # 元凶短语不得再出现
        self.assertNotIn("一句到几句意境", p)
        self.assertIn("gen_skill 的规定为准", p)  # 明确让位给技能
        self.assertIn("逐字稿", p)               # 技能的逐字稿要求(few-shot段)确实进了 prompt

    def test_full_skill_recipe_in_prompt(self):
        """截断放宽:gen_skill 末段(交出什么/边界)也进 prompt,逐字稿配方不被截尾。"""
        p = draft.generate_draft("ootd号", llm_mode="stub")["prompt"]
        self.assertIn("25-30s", p)     # 逐字稿时长约束进了 prompt
        self.assertIn("交出什么", p)    # 技能末段也在,证明没被截断


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


class NeverOverwriteAPendingReview(unittest.TestCase):
    """**不许覆盖运营正在等着审的稿**(2026-07-14 以 agent 身份上班,我差点亲手干出来)。

    `_find_inflight_note` 原来把『待出文案』和『草稿待发』一视同仁,找到就 update 上去。
    可这俩是两回事:
      · 待出文案 = 派活占位,**里面还没有内容** → 出稿推进它,天经地义;
      · 草稿待发 = **已经有稿子,人正等着审** → 再出一条 update 上去,
        就是**把运营待审的稿悄无声息地换掉**。他在卡片上看到 A,点进 base 变成了 B。
    "复用在途、不新建重复"当初是为了修重复堆稿 —— **可对已成稿的正解是"跳过",不是"覆盖"**。
    覆盖别人正在等的东西,任何时候都不叫"复用"。
    """

    def _base(self, status):
        return {"笔记表": [{"record_id": "recOld", "fields": {
                    NF.STATUS: status, NF.TITLE: "运营正在审的那条",
                    NF.ACCOUNT: [{"record_ids": ["recA"]}],
                    NF.CONTENT_TYPE: [{"record_ids": ["recC"]}]}}],
                "账号表": [{"record_id": "recA", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recC", "fields": {"内容类型名": "视频唯美OOTD"}}]}

    def _run(self, status):
        from unittest import mock
        from orchestrator import feishu_io
        base = self._base(status)
        r = draft.generate_draft("ootd号", llm_mode="stub", content_type="视频唯美OOTD")
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_in", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "update_record",
                                  lambda t, rid, f: cap.update(updated=rid)), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda t, f: cap.update(created=True) or "recNew"):
            return draft.create_draft_note(r), cap

    def test_pending_review_draft_is_never_overwritten(self):
        with self.assertRaises(draft.DraftPending):
            self._run(NS.DRAFT_PENDING)

    def test_placeholder_is_still_promoted(self):
        """『待出文案』占位(没内容)照旧推进 —— 别把去重修成"什么都不敢做"。"""
        rid, cap = self._run(NS.NEED_COPY)
        self.assertEqual(rid, "recOld")
        self.assertEqual(cap.get("updated"), "recOld")   # 推进占位,不新建
        self.assertNotIn("created", cap)


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
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: fake.get(t, [])), \
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
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: []), \
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
        with mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: mats):
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
        with mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: mats):
            ids = draft.select_materials(["上身视频"], account_rec_id="recOOTD")
        self.assertIn("recOwn", ids)
        self.assertIn("recUntagged", ids)
        self.assertNotIn("recOther", ids)

    def test_create_draft_note_attaches_materials(self):
        """出稿时选定的那批素材,**原样挂进关联素材**(不重选)——文案就是配它们写的,重选会货不对板。"""
        from unittest import mock
        from orchestrator import feishu_io
        matV = {"record_id": "recV", "fields": {"类型": "上身视频", "拍摄状态": "已拍"}}
        # material_rows 注入 → generate_draft 零 IO(不打真库);这批就是文案的事实底座
        r = draft.generate_draft("ootd号", llm_mode="stub", material_rows=[matV])
        self.assertEqual(r["material_ids"], ["recV"])
        fake = {"账号表": [{"record_id": "recACC", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recCT", "fields": {"内容类型名": "视频唯美OOTD"}}],
                "素材表": [matV]}
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t: fake.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: fake.get(t, [])), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: cap.update(fields=fields) or "recN"):
            draft.create_draft_note(r)
        self.assertEqual(cap["fields"][NF.LINKED_MATERIALS], ["recV"])  # 素材挂进关联素材

    def test_no_candidate_no_crash(self):
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("ootd号", llm_mode="stub", material_rows=[])   # 无候选
        self.assertEqual(r["material_ids"], [])
        self.assertFalse(r["material_grounded"])          # 眼前无画面 → prompt 该走"禁编造"分支
        cap = {}
        with mock.patch.object(feishu_io, "list_records",
                               lambda t: {"账号表": [{"record_id": "recA", "fields": {"账号名": "ootd号"}}]}.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: []), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: cap.update(fields=fields) or "recN"):
            draft.create_draft_note(r)
        self.assertNotIn(NF.LINKED_MATERIALS, cap["fields"])  # 无候选不挂,不炸

    def test_prefers_least_cited_to_spread(self):
        """#36 去重:同类型多候选,按被引用次数升序『少用优先』→ 素材分散,减少跨号/跨条撞图。
        **真被引用次数 = 数反向链接**(『被引用次数』formula 恒返 0、已从库里删除)。"""
        from unittest import mock
        from orchestrator import feishu_io
        mats = [  # 表序上 recHot 在前,但它已被 5 篇笔记引用;应让没用过的 recCold 先
            {"record_id": "recHot", "fields": {"类型": "上身图", "拍摄状态": "已拍",
                                               "笔记表-关联素材": [{"record_ids": ["n1", "n2", "n3", "n4", "n5"]}]}},
            {"record_id": "recCold", "fields": {"类型": "上身图", "拍摄状态": "已拍"}},   # 无反向链接=没用过
        ]
        with mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: mats):
            self.assertEqual(draft.select_materials(["上身图"], limit=1), ["recCold"])  # 少用的先
            self.assertEqual(draft.select_materials(["上身图"], limit=2), ["recCold", "recHot"])


class MaterialHitsPure(unittest.TestCase):
    """#32 过滤谓词 `_material_hits` 直测:records 作参数注入,**零 mock**(IO 与选择已分离)。
    真正会错的 6 条过滤 + 排序在纯函数里直接喂字面 records 断言,不必 patch list_records。"""

    def test_type_shot_and_least_cited_order(self):
        mats = [   # 真形态:被引用次数 = 反向链接『笔记表-关联素材』的条数(那个 formula 字段已删)
            {"record_id": "recHot", "fields": {"类型": "上身图", "拍摄状态": "已拍",
                                               "笔记表-关联素材": [{"record_ids": ["n1", "n2", "n3", "n4", "n5"]}]}},
            {"record_id": "recCold", "fields": {"类型": "上身图", "拍摄状态": "已拍"}},        # 没用过
            {"record_id": "recTodo", "fields": {"类型": "上身图", "拍摄状态": "待拍"}},        # 未拍→排除
            {"record_id": "recWrong", "fields": {"类型": "上身视频", "拍摄状态": "已拍"}},     # 类型不符→排除
        ]
        self.assertEqual(draft._material_hits(mats, ["上身图"]), ["recCold", "recHot"])   # 已拍+类型符,少用优先
        self.assertEqual(draft._material_hits(mats, ["上身图"], limit=1), ["recCold"])
        self.assertEqual(draft._material_hits([], ["上身图"]), [])                          # 无候选
        self.assertEqual(draft._material_hits(mats, []), [])                                # 空 needs

    def test_track_projection(self):
        mats = [
            {"record_id": "recOwn", "fields": {"类型": "上身图", "拍摄状态": "已拍", "适用账号": [{"record_ids": ["recOOTD"]}]}},
            {"record_id": "recOther", "fields": {"类型": "上身图", "拍摄状态": "已拍", "适用账号": [{"record_ids": ["recX"]}]}},
            {"record_id": "recUntagged", "fields": {"类型": "上身图", "拍摄状态": "已拍"}},
        ]
        ids = draft._material_hits(mats, ["上身图"], account_rec_id="recOOTD")
        self.assertIn("recOwn", ids); self.assertIn("recUntagged", ids); self.assertNotIn("recOther", ids)

    def test_clothes_matchboard_and_content_addressing(self):
        mats = [   # 货对板/内容寻址匹配 素材编号 或 备注(与线上一致)
            {"record_id": "recA", "fields": {"类型": "形象图", "拍摄状态": "已拍", "素材编号": "SC-GY-001-05", "备注": "月影蓝"}},
            {"record_id": "recB", "fields": {"类型": "形象图", "拍摄状态": "已拍", "素材编号": "SC-紫藤-01", "备注": "逆光 GY-003"}},
        ]
        self.assertEqual(draft._material_hits(mats, ["形象图"], clothes="GY-001"), ["recA"])   # #36 只货对板(编号标)
        self.assertEqual(draft._material_hits(mats, ["形象图"], clothes="GY-999"), [])          # 无匹配→0,不挂错
        self.assertEqual(draft._material_hits(mats, ["形象图"], content="逆光"), ["recB"])       # #38 内容寻址(备注标)


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
        with mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: [mat_rec]):
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


class ClothesConsistentMaterials(unittest.TestCase):
    """#36 品牌新作货对板闸:绑衣服时只选『编号/备注标了该衣服』的素材,标不上宁可 0 条,不挂错图。
    实测发现:官号文案绑 GY-003、素材却是孔府蓝罗(GY-001)→货不对板=对读者等于编造。"""

    def test_clothes_filters_to_matching_materials(self):
        from unittest import mock
        from orchestrator import feishu_io
        mats = [
            {"record_id": "recA", "fields": {"类型": "形象图", "拍摄状态": "已拍",
                                             "素材编号": "SC-GY-001-05", "备注": "月影蓝形象图"}},
            {"record_id": "recB", "fields": {"类型": "形象图", "拍摄状态": "已拍",
                                             "素材编号": "SC-紫藤-01", "备注": "GY-003 紫藤形象图"}},
        ]
        with mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: mats):
            self.assertEqual(draft.select_materials(["形象图"], clothes="GY-001"), ["recA"])  # 只 GY-001
            self.assertEqual(draft.select_materials(["形象图"], clothes="GY-003"), ["recB"])  # 只 GY-003(备注标)
            self.assertEqual(draft.select_materials(["形象图"], clothes="GY-999"), [])          # 无匹配→0,不挂错

    def test_empty_clothes_keeps_track_behavior(self):
        """非品牌新作(clothes 空)不按衣服过滤,#32 赛道选素材行为不变。"""
        from unittest import mock
        from orchestrator import feishu_io
        mats = [{"record_id": "recX", "fields": {"类型": "上身图", "拍摄状态": "已拍", "素材编号": "SC-x"}}]
        with mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: mats):
            self.assertEqual(draft.select_materials(["上身图"]), ["recX"])

    def test_create_note_brand_mismatch_attaches_no_materials(self):
        """官号绑 GY-003、库里素材只有 GY-001 → 一条都不挂(宁缺毋滥,货对板),不炸。"""
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("官号@巧荷·东方美学", llm_mode="stub", clothes="GY-003")
        fake = {"账号表": [{"record_id": "recACC", "fields": {"账号名": "官号@巧荷·东方美学"}}],
                "内容类型表": [{"record_id": "recCT", "fields": {"内容类型名": "品牌新作展示"}}],
                "素材表": [{"record_id": "recV", "fields": {"类型": "上身视频", "拍摄状态": "已拍",
                                                          "素材编号": "SC-GY-001-01"}}]}
        cap = {}
        with mock.patch.object(feishu_io, "list_records", lambda t: fake.get(t, [])), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: cap.update(fields=fields) or "recN"):
            draft.create_draft_note(r)
        self.assertNotIn(NF.LINKED_MATERIALS, cap["fields"])  # GY-003 无匹配素材→不挂错图


class MultiMode(unittest.TestCase):
    """一号多模式(scalable):content_type 选对应 playbook(默认第一套);选不存在的模式报错不静默。
    ootd号 声明了 视频唯美OOTD + 图文唯美OOTD 两模式,共用 writing-ootd-caption,素材需求不同。"""

    def test_content_type_selects_playbook(self):
        a = draft.generate_draft("ootd号", llm_mode="stub")                              # 默认第一套
        b = draft.generate_draft("ootd号", llm_mode="stub", content_type="图文唯美OOTD")  # 选第二模式
        self.assertEqual(a["playbook_id"], "视频唯美OOTD")
        self.assertEqual(a["material_needs"], ["上身视频"])
        self.assertEqual(b["playbook_id"], "图文唯美OOTD")
        self.assertEqual(b["material_needs"], ["上身图"])        # 不同模式→不同素材需求
        self.assertEqual(a["gen_skill"], b["gen_skill"])          # 同号共用生成技能

    def test_unknown_content_type_raises(self):
        with self.assertRaises(ValueError):
            draft.generate_draft("ootd号", llm_mode="stub", content_type="不存在的模式xyz")


class ContentAddressing(unittest.TestCase):
    """#38 内容寻址:select_materials 按备注里的内容标签(场景/调性/衣服)选,不只类型∩赛道。"""

    def test_select_by_content_tag(self):
        from unittest import mock
        from orchestrator import feishu_io
        mats = [
            {"record_id": "rFront", "fields": {"类型": "上身图", "拍摄状态": "已拍",
                                               "素材编号": "SC-01", "备注": "正面站姿"}},
            {"record_id": "rBacklit", "fields": {"类型": "上身图", "拍摄状态": "已拍",
                                                 "素材编号": "SC-02", "备注": "侧身逆光·意境"}},
        ]
        with mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: mats):
            self.assertEqual(draft.select_materials(["上身图"], content="逆光"), ["rBacklit"])  # 按内容寻址
            self.assertEqual(draft.select_materials(["上身图"], content="没有的场景"), [])         # 无匹配→空


class DraftAdvancesInflightNote(unittest.TestCase):
    """iter9:出稿推进派活的『待出文案』为『草稿待发』(状态机一条内容一行),不新建重复行;
    反回归:曾经 create_draft_note 永远 create_record → 派活占位成孤儿、一条内容变两行。"""

    def test_advances_need_copy_instead_of_new(self):
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("ootd号", llm_mode="stub")   # 视频唯美OOTD
        # **真形态**:search API 回的 link 字段是 {'link_record_ids': [...]}(没有 text)。
        # 原来这里写的是裸字符串 "ootd号" —— 一个**真实世界不存在的形态**。假 mock 让测试常绿,
        # 而生产里 _find_inflight_note 用 text() 读永远读出空串 → 在途永远找不到 → 每次出稿新建一行 →
        # 运营卡片待审区堆了 5 条同号同模式的重复稿。mock 比真数据"干净",bug 就是这么活下来的。
        base = {"账号表": [{"record_id": "recACC", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recCT", "fields": {"内容类型名": "视频唯美OOTD"}}],
                "笔记表": [{"record_id": "recPH", "fields": {
                    NF.STATUS: NS.NEED_COPY,
                    NF.ACCOUNT: {"link_record_ids": ["recACC"]},
                    NF.CONTENT_TYPE: {"link_record_ids": ["recCT"]}}}]}   # 派活占位在途
        upd, created = {}, []
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "update_record", lambda table, rid, f: upd.update(rid=rid, fields=f)), \
                mock.patch.object(feishu_io, "create_record", lambda table, f: created.append(f) or "recNEW"):
            rid = draft.create_draft_note(r)
        self.assertEqual(rid, "recPH")                       # 推进那一行,不新建
        self.assertEqual(upd["fields"][NF.STATUS], NS.DRAFT_PENDING)  # 待出文案→草稿待发
        self.assertEqual(created, [])                        # 无重复新建

    def test_new_when_no_inflight(self):
        from unittest import mock
        from orchestrator import feishu_io
        r = draft.generate_draft("ootd号", llm_mode="stub")
        base = {"账号表": [{"record_id": "recACC", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recCT", "fields": {"内容类型名": "视频唯美OOTD"}}]}  # 笔记表空
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "create_record", lambda table, f: "recNEW"):
            self.assertEqual(draft.create_draft_note(r), "recNEW")   # 无在途→新建


class NoSourceLeakGate(unittest.TestCase):
    """防搬运出口闸(红线):出稿不得逐字搬对标/灵感 seed。反回归:曾经出稿路径零调用 skill_gate/no_source_leak。"""

    def test_guard_blocks_verbatim_leak(self):
        from orchestrator import guard
        with self.assertRaises(guard.GuardError):
            guard.assert_no_source_leak("原来500年前我们就有polo衫了", "抄:原来500年前我们就有polo衫了！")
        guard.assert_no_source_leak("原来500年前我们就有polo衫了", "夏色入衿，风过成凉")  # 无重叠→放行
        guard.assert_no_source_leak("短句", "任何输出")      # 源太短不产生保护,也不误伤

    def test_guards_every_text_the_llm_actually_saw(self):
        """**门必须守"LLM 真正看得见的东西"**(2026-07-14 真跑抓到的方向性错误)。

        LLM 在 prompt 里**真正看到**的只有:① title_seed(标题线索)
        ② **gen_skill 的 few-shot 真实帖** —— 技能白纸黑字写着「只学结构、绝不抄原句」
        「出口过防搬运闸」,**而那句话从来没人执行**。
        LLM **从来没看到**的:source_text(对标源正文)—— `compose_prompt` 根本不收它。

        于是老实现犯了双重错误:
          · **守着 LLM 没见过的东西**(source_text):正文没进 prompt,逐字搬它物理上不可能,
            这份"保护"是空的;
          · **真能搬的东西不看**(few-shot 真实帖就在 prompt 里)——真跑实证:把 few-shot 的
            真实帖逐字搬进产出 → **直接过门,一个字都没查**。
        (我还一度加过"声称蹭爆款却拿不出正文→拒绝出稿",在防一个不存在的风险,
         同时把整条爆款模仿链路焊死 —— 而正文在非登录下**根本抓不到**。已撤。)

        真契约:调用方把**所有进了 prompt 的文本**都传进来,门逐个比。
        """
        from orchestrator import accounts, draft, guard
        acc = accounts.load("ootd号", "巧荷")
        pb = draft.pick_playbook(acc, "视频唯美OOTD")
        skill = draft.load_gen_skill(accounts.gen_skill_of(pb))
        self.assertIn("OOTD｜宋代风雅，粉蝶入绢", skill)     # 技能里有真实帖(它在 prompt 里)

        # ① 逐字搬 few-shot 的真实帖 → **必须拒**(以前直接过门)
        with self.assertRaises(guard.GuardError):
            guard.assert_no_source_leak(["", "", skill],
                                        "OOTD｜宋代风雅，粉蝶入绢\n\n夏色入衿。\n\n#汉服")
        # ② 逐字搬灵感标题 → 必须拒
        with self.assertRaises(guard.GuardError):
            guard.assert_no_source_leak(["", "小个子怎么穿汉服显高显瘦", skill],
                                        "小个子怎么穿汉服显高显瘦\n\n正文。\n\n#汉服")
        # ③ 真原创 → 放行,不误伤(否则天天狼来了,门就废了)
        guard.assert_no_source_leak(["", "小个子怎么穿汉服显高显瘦", skill],
                                    "OOTD｜粉罗载光\n\n光落在衣上，风把影子摇醒。\n\n#汉服")

    def test_over_spec_body_gets_trimmed_not_dumped_on_the_operator(self):
        """**超规格 → 回炉改一次,别把锅甩给运营**(2026-07-14 探针真跑抓到:出稿148字,规格100-140)。

        病根是那个熟悉的形状:prompt 里已经写了「【篇幅硬要求】必须100-140字」、quality_flags 也已经
        会插旗 —— 于是系统觉得自己"做完了"。**可没人去修它**:LLM 不听,稿子照样落库,QC 一插旗,
        让运营自己去删那 8 个字。**把 prompt 里的一句话当成了执行。**
        锁行为:超了→带着字数回炉删减→压回规格内。改完仍超才插旗给人看(诚实兜底,不假装修好)。"""
        from orchestrator import draft
        pb = {"body_len": [100, 140]}
        long_body = "光" * 148
        calls = []

        def fake_run(prompt):
            calls.append(prompt)
            return f"标题行\n\n{'光' * 130}\n\n#汉服", 0.01

        from unittest import mock as _m
        with _m.patch.object(draft.llm, "run_prompt", fake_run):
            out, cost = draft._fit_to_spec(f"标题行\n\n{long_body}\n\n#汉服", pb, "原prompt")
        self.assertEqual(len(draft.body_text(out)), 130)          # 真被压回规格内
        self.assertIn("148", calls[0])                            # 告诉它超了多少(不是空喊"太长了")
        self.assertIn("只做删减", calls[0])                        # 只许删,不许换主题/新编画面
        self.assertGreater(cost, 0)                               # 回炉的钱算进成本,不藏账

    def test_in_spec_body_costs_nothing(self):
        """没超规格 → **一次 LLM 都不多调**(别为了"稳"平白烧钱,那也是"想起来方便")。"""
        from orchestrator import draft
        def boom(_):  # noqa: ANN001
            raise AssertionError("没超规格却回炉了")
        from unittest import mock as _m
        with _m.patch.object(draft.llm, "run_prompt", boom):
            out, cost = draft._fit_to_spec("标题\n\n" + "光" * 120 + "\n\n#汉服", {"body_len": [100, 140]}, "p")
        self.assertEqual(cost, 0.0)
        self.assertIn("光" * 120, out)

    def test_harvest_trends_reports_missing_body(self):
        """源头堵:落灵感时没原帖正文 → 必须喊出来(从它出的稿会被红线直接拒)。"""
        from orchestrator import trends
        res = trends.harvest_trends(
            [{"标题": "无正文的灵感", "可借鉴": "钩子强"},
             {"标题": "有正文的灵感", "文案": "这是原帖正文,防搬运门要拿它比对逐字搬运"}],
            write=False)
        self.assertEqual(res["无正文"], ["无正文的灵感"])

    def test_guard_whitespace_punctuation_cannot_evade(self):
        """红线 robust:加空格/改标点/换全半角不能绕过防搬运(归一化后仍是原文)。
        反回归:曾用裸子串滑窗,搬运者插一个空格即漏——现归一化后再比对。"""
        from orchestrator import guard
        src = "原来500年前我们就有polo衫了"
        with self.assertRaises(guard.GuardError):   # 复制原文但加空格改标点,裸子串会漏、归一化必拦
            guard.assert_no_source_leak(src, "抄袭： 原来 500 年前，我们 就有 polo 衫了 ！！")

    def test_draft_real_blocks_leaking_output(self):
        from unittest import mock
        from orchestrator import llm, guard
        seed = "对标爆款原文这是一句很长的对标原句不该被逐字搬运进我方产出"
        with mock.patch.object(llm, "run_prompt", lambda p: (f"我的稿承接{seed}", 0.0)):
            with self.assertRaises(guard.GuardError):
                draft.generate_draft("ootd号", llm_mode="real", title_seed=seed)   # 逐字搬→拦
        with mock.patch.object(llm, "run_prompt", lambda p: ("OOTD｜夏色入衿，风过成凉\n原创短文", 0.0)):
            r = draft.generate_draft("ootd号", llm_mode="real", title_seed=seed)     # 原创→放行
            self.assertTrue(r["draft_text"].strip())

    def test_draft_real_blocks_leaking_source_body(self):
        """防搬运门比对 source_text(对标源完整正文),不再只看标题(ADR-0009 修"红线名不副实")。"""
        from unittest import mock
        from orchestrator import llm, guard
        body = "爆款正文里一段独特的长句子必须超过十个连续实义字符才会触发防搬运门判定"
        with mock.patch.object(llm, "run_prompt", lambda p: (f"我方稿开头{body}结尾", 0.0)):
            with self.assertRaises(guard.GuardError):
                draft.generate_draft("ootd号", llm_mode="real", source_text=body)   # 逐字搬正文→拦


class KeywordInjection(unittest.TestCase):
    """iter27:关键词库接进出稿(选题/SEO,曾是哑数据没喂回生成)。软注入、调性优先;real 才注入(stub 离线)。"""

    def test_compose_prompt_includes_keyword_hint(self):
        from orchestrator import accounts
        acc = accounts.load("ootd号")
        p = draft.compose_prompt(acc, acc.playbooks()[0], "skill", keywords=["新中式", "女性力量"])
        self.assertIn("关键词池", p)
        self.assertIn("新中式", p)
        self.assertIn("别硬堆", p)          # 调性优先、不强制堆砌

    def test_load_keywords_skips_disabled(self):
        from unittest import mock
        from orchestrator import feishu_io
        kws = [{"fields": {"关键词": "新中式", "启用状态": "启用"}},
               {"fields": {"关键词": "停用词", "启用状态": "停用"}},   # 飞书实际枚举=启用/停用(非"禁用")
               {"fields": {"关键词": "女性力量"}}]        # 无状态=按启用
        with mock.patch.object(feishu_io, "list_records", lambda t: kws):
            out = draft.load_keywords("巧荷")
        self.assertEqual(set(out), {"新中式", "女性力量"})   # 停用跳过

    def test_stub_stays_offline_no_keyword(self):
        p = draft.generate_draft("ootd号", llm_mode="stub")["prompt"]
        self.assertNotIn("关键词池", p)      # stub 不加载关键词(不触网),prompt 无关键词池


class FieldValueHelpers(unittest.TestCase):
    """codify 反复踩的 link/url 字段格式坑:link→record_id列表、url→{link,text}dict。"""


    def test_url_value_wraps_to_dict(self):
        from orchestrator import bitable
        self.assertEqual(bitable.url_value("https://x", "描述"), {"link": "https://x", "text": "描述"})
        self.assertEqual(bitable.url_value("https://x"), {"link": "https://x", "text": "https://x"})

    def test_known_link_url_fields_documented(self):
        from orchestrator import bitable
        self.assertIn("转化为笔记", bitable.LINK_FIELDS)   # 实测炸过的
        self.assertIn("关联关键词", bitable.LINK_FIELDS)
        self.assertIn("发布链接", bitable.URL_FIELDS)
        self.assertIn("链接", bitable.URL_FIELDS)          # 灵感库.链接/素材.链接
        self.assertIn("主页链接", bitable.URL_FIELDS)      # 账号表.主页链接=URL(实测URLFieldConvFail)


class TestQualityFlags(unittest.TestCase):
    """#42 出稿即评轻量闸:客观质检标记(不阻塞,顶给人审)。"""
    def test_flags_common_problems(self):
        from orchestrator.draft import quality_flags
        self.assertEqual(quality_flags(""), ["空稿"])
        self.assertIn("无#标签", quality_flags("标题\n\n正文没标签"))
        self.assertTrue(any("标题" in f for f in quality_flags("这标题非常非常非常非常非常非常长超过二十字了\n\n正文 #x")))
        self.assertTrue(any("占位" in f for f in quality_flags("stub 占位草稿 #x")))

    def test_clean_draft_no_flags(self):
        from orchestrator.draft import quality_flags
        good = "藕荷色对襟上衣\n\n今天穿这套去园林拍照超好看,面料是真丝提花...\n\n#新中式 #汉服 #ootd"
        self.assertEqual(quality_flags(good), [])


# ── 真形态回归锁:固件是 2026-07-14 dogfood **真跑产出的真稿**(一个字没改),不是编的 mock ──
# 这四条稿把两个真缺陷钉在这:①豆包 lite 把【视频剪辑要点】混进要发的文案(运营复制就发出去=事故);
# ②豆包 mini 正文才 56 字(技能 writing-ootd-caption 要求 100-140 字逐字稿)。
# 而**修复前的 quality_flags 对这四条一条 flag 都不响**——它守的是小红书平台上限(标题20/全文1000),
# 真稿标题最长 14 字、全文最长 195 字,5 倍余量,永远撞不到。这些测试就是防它退回去。
REAL_DRAFT_LITE_WITH_PRODUCTION_NOTES = (  # 豆包 seed-2-0-lite 真跑:老老实实执行了技能『交出什么』
    "OOTD｜粉罗裁光，碎香浸影\n\n（27s逐字稿）\n"
    "风擦过衣料的瞬间，连周遭的光线都软了下来。\n"
    "衣身浮着细碎闪绒，像把半春的粉樱落絮都织进了布里。\n"
    "贴肤是凉滑的软，完全没有沉坠的厚重感。\n"
    "靠在老木边站着发呆，整个人的情绪都慢下来了。\n\n"
    "【视频剪辑要点】前4s定格浅粉衣身细闪随柔光晃动的局部特写，中间10s慢移镜头扫过裸露的小臂，"
    "后半段13s切对镜轻晃衣摆的画面，全程柔焦，配轻缓筝音BGM。"
)
REAL_DRAFT_MINI_TOO_SHORT = (  # 豆包 mini 真跑:正文仅 56 字,技能要 100-140
    "OOTD｜粉纱衔光\n\n光落粉纱时，细闪衔着星子的碎光。软得像揉过的春云，指尖一触便漾开。"
    "凭栏处，风蹭过衣袂，轻得像没留下痕迹。\n\n#新中式 #东方美学 #ootd #传统文化"
)
REAL_DRAFT_SONNET_OK = (  # claude sonnet + 素材事实 真跑:四层齐、正文约 110 字、无制作说明 → 应零 flag
    "OOTD｜藕粉栖光，木荫染暖\n\n"
    "风还没热透，粉色倒先醒了。袖口那点细闪，像揉碎的光沾在腕间，若隐若现，不喧哗。"
    "贴着手臂的地方很轻，风一过，浮光跟着轻轻晃，不显厚重，也不压人。"
    "身后木色晕成一片暖褐，光是软的，人站在里头，连呼吸都慢了半拍。\n\n"
    "#汉服穿搭 #新中式 #OOTD #东方美学"
)
PB_VIDEO = {"id": "视频唯美OOTD", "content_type": "视频唯美OOTD", "body_len": [100, 140]}


class TestQualityFlagsRealDrafts(unittest.TestCase):
    """真跑稿回归锁:修复前这四条『一条 flag 都不响』,是"检查表演"。"""

    def test_production_notes_must_be_flagged(self):
        """【视频剪辑要点】混进要发的文案 = 真事故(运营从 base 复制就发到小红书)。必须报。"""
        from orchestrator.draft import quality_flags
        flags = quality_flags(REAL_DRAFT_LITE_WITH_PRODUCTION_NOTES, PB_VIDEO)
        self.assertTrue(any("制作说明" in f for f in flags), f"制作说明混入没报: {flags}")

    def test_too_short_body_must_be_flagged(self):
        """正文 56 字 < 技能要求 100-140 字(逐字稿念不满 25-30s)。必须报。"""
        from orchestrator.draft import quality_flags
        flags = quality_flags(REAL_DRAFT_MINI_TOO_SHORT, PB_VIDEO)
        self.assertTrue(any("技能要求" in f for f in flags), f"篇幅不足没报: {flags}")

    def test_good_real_draft_stays_clean(self):
        """四层齐、篇幅达标、无制作说明的真稿 → 不该误报(否则天天狼来了,人就不看了)。"""
        from orchestrator.draft import quality_flags
        self.assertEqual(quality_flags(REAL_DRAFT_SONNET_OK, PB_VIDEO), [])

    def test_old_thresholds_were_unreachable(self):
        """钉住"为什么原来的检查是死的":真稿离平台上限有 5 倍余量,那两条永远不响。"""
        for d in (REAL_DRAFT_LITE_WITH_PRODUCTION_NOTES, REAL_DRAFT_MINI_TOO_SHORT, REAL_DRAFT_SONNET_OK):
            title = [ln for ln in d.splitlines() if ln.strip()][0]
            self.assertLess(len(title), 20, "真稿标题从没撞到小红书 20 字上限")
            self.assertLess(len(d), 1000, "真稿全文从没撞到小红书 1000 字上限")

    def test_no_body_len_spec_means_no_length_check(self):
        """技能没写字数规格的模式(素人种草/品牌新作),不替它编数字瞎检。"""
        from orchestrator.draft import quality_flags
        flags = quality_flags(REAL_DRAFT_MINI_TOO_SHORT, {"id": "素人图文种草"})   # 无 body_len
        self.assertFalse(any("技能要求" in f for f in flags), f"没规格却检了篇幅: {flags}")


class TestZeroMaterialAndSpread(unittest.TestCase):
    """全真实测(2026-07-14,5 个号×模式全 --llm real 真落库)炸出的两个真 bug。"""

    def test_zero_material_draft_must_be_flagged(self):
        """官号绑 --clothes GY-001,货对板规则筛掉全部素材 → **0 张图的稿**落进草稿待发,
        而当时质检说「✅ 无问题」。小红书没图发不了帖,运营拿到手是废稿。必须喊出来。"""
        from orchestrator.draft import quality_flags
        good_text = REAL_DRAFT_SONNET_OK
        self.assertEqual(quality_flags(good_text, PB_VIDEO, material_count=1), [])   # 有图=没事
        flags = quality_flags(good_text, PB_VIDEO, material_count=0)
        self.assertTrue(any("零素材" in f for f in flags), f"零素材没报: {flags}")

    def test_cited_count_reads_backlink_not_broken_formula(self):
        """『被引用次数』是 formula 字段,但**活库里 COUNTA/COUNT 对 DuplexLink 都算不出来,恒返回 0**
        (真库实证:ST-260702-001 反向链接挂了 4 篇笔记,formula 仍报 0)。
        后果:所有素材 cited 全 0 → 排序 stable → **永远返回表序前 3 条** → 133 条上身图只用前 3 条,
        3 个号同一天出稿全撞同一批图。真被引用次数必须**数反向链接**,别信那个 formula。"""
        from orchestrator.draft import _cited_count
        # 真库形态(get_record 返回的 DuplexLink):4 篇笔记引用了它,formula 却报 0。
        # 该 formula 字段已从库里删除;这里仍留着它,是回归锁——**哪天它以任何形式回来,也不许信它**。
        real_fields = {
            "素材编号": "ST-260702-001",
            "被引用次数": 0,                      # ← 坏 formula,真库当时就是这么返回的
            "笔记表-关联素材": [{"record_ids": ["recA", "recB", "recC", "recD"],
                                 "table_id": "tblsiceNwWpidwAG", "text": ""}],
        }
        self.assertEqual(_cited_count(real_fields), 4, "被引用次数必须数反向链接,不能信坏 formula")

        never_used = {"素材编号": "ST-260702-004"}   # 没反向链接 = 真没被用过
        self.assertEqual(_cited_count(never_used), 0)

    def test_least_cited_wins_so_materials_spread(self):
        """少用优先必须真生效:被引用多的沉底,没用过的先出 → 素材分散,不撞图。"""
        from orchestrator import draft
        used4 = {"record_id": "recHot", "fields": {
            "类型": "上身图", "拍摄状态": "已拍",
            "笔记表-关联素材": [{"record_ids": ["n1", "n2", "n3", "n4"]}]}}
        fresh = {"record_id": "recCold", "fields": {"类型": "上身图", "拍摄状态": "已拍"}}
        got = draft._material_hits([used4, fresh], ["上身图"], limit=1)
        self.assertEqual(got, ["recCold"], "被引用 4 次的还排在没用过的前面 → 撞图会复发")


class TestSceneSpread(unittest.TestCase):
    """一条稿里的几张图,画面别重样(2026-07-14 运营视角实测:真跑出的图文稿挂了 3 张同组连拍,
    vision 标逐字雷同——运营一眼看出"3 张图长得一样,发出去像凑数")。"""

    def test_same_scene_burst_is_spread_out(self):
        from orchestrator import draft
        burst = "真人穿着粉色新中式上衣、白色纱裙，坐在酒店黑色大理石楼梯旁地面，室内暖光"
        other = "真人穿着浅蓝色带刺绣的新中式上衣、白色阔腿裤，站在铺有花纹地毯的弧形楼梯上"
        mats = [   # 表序上连拍在前,应该被打散:先给不同场景的
            {"record_id": "b1", "fields": {"类型": "上身图", "拍摄状态": "已拍", "备注": burst}},
            {"record_id": "b2", "fields": {"类型": "上身图", "拍摄状态": "已拍", "备注": burst}},
            {"record_id": "o1", "fields": {"类型": "上身图", "拍摄状态": "已拍", "备注": other}},
        ]
        got = draft._material_hits(mats, ["上身图"], limit=2)
        self.assertEqual(got, ["b1", "o1"], "同组连拍应打散,先铺开不同场景")

    def test_falls_back_to_same_scene_when_stock_thin(self):
        """库存不够时宁可重样也别少给图——少给图 = 零素材 = 根本发不出去,那是更硬的伤。"""
        from orchestrator import draft
        burst = "同一组连拍的画面描述"
        mats = [{"record_id": f"b{i}", "fields": {"类型": "上身图", "拍摄状态": "已拍", "备注": burst}}
                for i in range(3)]
        self.assertEqual(len(draft._material_hits(mats, ["上身图"], limit=3)), 3)


class TestMaterialFacts(unittest.TestCase):
    """出稿的**事实底座**:选中素材的 vision 标(『备注』)进 prompt,文案才是『配』画面写的不是编的。"""

    def test_vision_note_becomes_prompt_fact(self):
        from orchestrator import draft
        # 真库真形态(素材表 recvpex6XzTP9H,豆包看图打的备注)
        rows = [{"record_id": "recvpex6XzTP9H", "fields": {
            "类型": "上身视频", "素材编号": "SV-000000-001",
            "备注": "浅粉色带细闪的汉服衣身局部特写，画面下方有裸露的手臂局部，"
                    "背景为模糊的红棕色木质场景，光线柔和自然"}}]
        facts = draft.material_facts(rows)
        self.assertIn("浅粉色带细闪", facts)
        self.assertIn("上身视频", facts)

    def test_prompt_carries_the_picture(self):
        """回归锁:素材事实必须真进 prompt(原来 compose_prompt 里根本没有素材 → LLM 瞎编面料手感)。"""
        from orchestrator import draft

        class _Acc:
            name, profile_text, error = "ootd号", "设计师人设", ""
        p = draft.compose_prompt(_Acc(), PB_VIDEO, "技能正文",
                                 material_text="· [上身视频] 浅粉色带细闪，红棕色木质场景，光线柔和")
        self.assertIn("细闪", p)
        self.assertIn("木质", p)
        self.assertIn("只写画面里看得出的", p)

    def test_no_material_no_clothes_falls_back_to_ban(self):
        """既无素材也无衣服 = 没有任何事实来源 → 必须禁编造(别再写'料子很轻')。"""
        from orchestrator import draft

        class _Acc:
            name, profile_text, error = "ootd号", "", ""
        p = draft.compose_prompt(_Acc(), PB_VIDEO, "技能正文")
        self.assertIn("严禁编造", p)


if __name__ == "__main__":
    unittest.main()
