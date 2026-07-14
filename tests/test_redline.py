"""红线锁(精简骨架版):替代随重引擎删除的 test_redline_no_autopublish。

大刀阔斧后不再有 heartbeat 引擎自动组装发布包——薄执行器 draft.py 只把笔记推到「草稿待发」,
物理上没有自动发布/自动置 AI 声明的代码路径,红线比端到端引擎时代更强。本测试锁死这些不变量(零网络零成本)。
依据《AI 生成合成内容标识办法》2025-09 + 巧荷红线:绝不自动发布、AI 声明人勾、只写测试库。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, draft, guard  # noqa: E402
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS  # noqa: E402
from orchestrator.guard import GuardError  # noqa: E402


class RedlineAiDeclarationGate(unittest.TestCase):
    def test_assert_ai_declared_blocks_when_unset(self):
        """AI声明门:未勾 AI 声明的内容进不了待发布(硬闸抛 GuardError,不静默)。"""
        with self.assertRaises(GuardError):
            guard.assert_ai_declared({NF.CODE: "X", NF.AI_DECLARED: False})

    def test_assert_ai_declared_passes_when_set(self):
        """对照:勾了 AI 声明才放行——证明硬闸精确拦『未声明』而非全拦。"""
        guard.assert_ai_declared({NF.CODE: "X", NF.AI_DECLARED: True})  # 不抛即通过


class RedlineThinExecutorNeverAutoPublishes(unittest.TestCase):
    def test_draft_only_reaches_review_pending(self):
        """薄执行器产出止于『草稿待发』——不越审核门、不置已批准/待发布/已发。"""
        f = draft.generate_draft("ootd号", llm_mode="stub")["note_fields"]
        self.assertEqual(f[NF.STATUS], NS.DRAFT_PENDING)
        self.assertNotIn(f[NF.STATUS], {NS.APPROVED, NS.TO_PUBLISH, NS.PUBLISHED})

    def test_draft_never_sets_ai_declaration(self):
        """AI 声明是人手勾——薄执行器绝不代置 AI声明 字段。"""
        f = draft.generate_draft("ootd号", llm_mode="stub")["note_fields"]
        self.assertNotIn(NF.AI_DECLARED, f)

    def test_no_autopublish_code_path_in_executor(self):
        """薄执行器源码里没有把状态推到待发布/已发的自动路径(绝不自动发布)。"""
        src = (Path(__file__).resolve().parents[1] / "orchestrator" / "draft.py").read_text(encoding="utf-8")
        self.assertNotIn(NS.TO_PUBLISH, src)
        self.assertNotIn(NS.PUBLISHED, src)


class RedlineWriteOnlyTestBase(unittest.TestCase):
    def test_create_draft_note_blocks_prod_under_test_mode(self):
        """写库红线:TEST_MODE 下 create_draft_note 过 base 闸拒生产 Base(闸先抛,触不到网络)。"""
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

class RedlinesHaveNoKnobs(unittest.TestCase):
    """**红线不许有旋钮**(2026-07-14 开关过堂,真跑实测抓到)。

    `PER_ACCOUNT_DAILY_PUBLISH` 原来写的是 `int(os.environ.get("GY_ACCOUNT_DAILY_PUB", "3"))`。
    真测:`GY_ACCOUNT_DAILY_PUB=999` → 今天已发 50 篇,**控量门照样放行**。
    **一个环境变量就能把红线关掉** —— 那它就不是红线,是个建议。
    更毒的是:env 关红线**不留任何痕迹**(git 看不到、日志看不到、人也看不到)。
    平台规则真变了 → **改 config.py 那一行并 commit,让人看见**。这是红线和普通配置的分界。
    """

    def test_publish_quota_cannot_be_disabled_by_env(self):
        import importlib
        import os
        from orchestrator import config as _c
        old = os.environ.get("GY_ACCOUNT_DAILY_PUB")
        os.environ["GY_ACCOUNT_DAILY_PUB"] = "999"
        try:
            importlib.reload(_c)
            self.assertEqual(_c.PER_ACCOUNT_DAILY_PUBLISH, 3, "红线阈值被 env 改掉了 —— 它不该有旋钮")
        finally:
            if old is None:
                os.environ.pop("GY_ACCOUNT_DAILY_PUB", None)
            else:
                os.environ["GY_ACCOUNT_DAILY_PUB"] = old
            importlib.reload(_c)

    def test_source_has_no_env_read_for_the_quota_redline(self):
        """连**源码里都不许出现**那个 env 读法 —— 否则下次有人"顺手"又给红线接回旋钮。"""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "orchestrator" / "config.py").read_text(encoding="utf-8")
        self.assertNotIn('PER_ACCOUNT_DAILY_PUBLISH = int(os.environ', src,
                         "控量红线又被接上 env 了 —— 红线不许有静音开关")
