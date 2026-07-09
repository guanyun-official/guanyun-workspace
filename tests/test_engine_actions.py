"""引擎各动作 handler 的特征化测试:锁住每个 Action 的副作用(写回/日报/告警)。

why:此前只有 route()(决定动作)和 ASSEMBLE 红线路径被测,GEN_COPY/MARK_PUBLISHED/
CLOSE_LOOP/COLLECT_METRICS/LIST_IDEA/REMIND_* 这些 handler 的实际副作用没有单测护住——
engine.run 的调度块一重构就可能静默改变行为而无人察觉。这里端到端跑 engine.run(隔离
LOCK/STATE、stub 飞书读写、捕获 alerts),把每个动作"该写什么状态/该进哪个日报清单"钉死,
作为 dispatch 表重构(M2)的安全网。零网络零成本。
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import alerts, engine, feishu_io, metrics, reminders  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402
from orchestrator.bitable import NoteStatus as NS  # noqa: E402
from orchestrator.bitable import RunLogFields as RLF  # noqa: E402
from lib import material_view as mv  # noqa: E402

MS = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731
NOW = datetime.now()


def run_one(note_fields: dict, llm_mode: str = "stub", mode: str = "heartbeat"):
    """跑一轮,只喂一条笔记;返回 (summary, updates, sent)。全隔离,可重复,不抢真实 cron 锁。"""
    note = {"record_id": "recA", "fields": note_fields}
    updates, sent = [], []
    box = Path(tempfile.mkdtemp())
    with mock.patch.object(feishu_io, "list_records", lambda t: [note] if t == "笔记表" else []), \
            mock.patch.object(feishu_io, "update_record",
                              lambda t, rid, patch: updates.append((t, rid, patch))), \
            mock.patch.object(feishu_io, "log_run", lambda *_a, **_k: None), \
            mock.patch.object(engine, "LOCK_FILE", box / "t.lock"), \
            mock.patch.object(reminders, "STATE_FILE", box / "reminder_state.json"), \
            mock.patch.object(alerts, "send",
                              lambda text, *, title="观云推进器": sent.append((title, text)) or True):
        summary = engine.run(mode=mode, llm_mode=llm_mode)
    return summary, updates, sent


def run_records(records: list, llm_mode: str = "stub", mode: str = "heartbeat"):
    """跑一轮,喂多条原始记录(feishu 形态:{record_id, fields});返回 (summary, updates, sent)。"""
    updates, sent = [], []
    box = Path(tempfile.mkdtemp())
    with mock.patch.object(feishu_io, "list_records", lambda t: records if t == "笔记表" else []), \
            mock.patch.object(feishu_io, "update_record",
                              lambda t, rid, patch: updates.append((t, rid, patch))), \
            mock.patch.object(feishu_io, "log_run", lambda *_a, **_k: None), \
            mock.patch.object(engine, "LOCK_FILE", box / "t.lock"), \
            mock.patch.object(reminders, "STATE_FILE", box / "reminder_state.json"), \
            mock.patch.object(alerts, "send",
                              lambda text, *, title="观云推进器": sent.append((title, text)) or True):
        summary = engine.run(mode=mode, llm_mode=llm_mode)
    return summary, updates, sent


def only_patch(updates: list) -> dict:
    """断言恰好一次写回,返回其 fields patch。"""
    assert len(updates) == 1, f"期望恰好一次写回,实际 {len(updates)}: {updates}"
    return updates[0][2]


class TestActionHandlers(unittest.TestCase):
    def test_list_idea_collects_no_write(self):
        summary, updates, _ = run_one({NF.STATUS: NS.IDEA, NF.CODE: "PQ-IDEA"})
        self.assertIn("PQ-IDEA", summary["ideas"])
        self.assertEqual(updates, [], "列想法储备不应写回任何状态")

    def test_remind_shoot_lists_with_hint_no_write(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.NEED_SHOOT, NF.CODE: "PQ-SHOOT", NF.STORYBOARD: "汉服马面裙特写"})
        self.assertEqual(len(summary["shoot"]), 1)
        self.assertIn("PQ-SHOOT", summary["shoot"][0])
        self.assertIn("汉服马面裙特写", summary["shoot"][0], "催拍应带上要拍什么(F2)")
        self.assertEqual(updates, [], "催拍只提醒不写回")

    def test_gen_copy_writes_draft_and_declares_ai(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.NEED_COPY, NF.CODE: "PQ-COPY", NF.CONTENT_TYPE: "考据"})
        patch = only_patch(updates)
        self.assertEqual(patch[NF.STATUS], NS.DRAFT_PENDING, "生成文案后应置『草稿待发』")
        self.assertTrue(patch[NF.AI_DECLARED], "生成的稿必须置 AI 声明位")
        self.assertTrue(patch[NF.DRAFT], "文案草稿不应为空")
        self.assertIn("next_产物", summary, "生成后应给出下一步产物提示(格式感知)")

    def test_mark_published_on_backfilled_link(self):
        _, updates, _ = run_one(
            {NF.STATUS: NS.TO_PUBLISH, NF.CODE: "PQ-PUB", NF.PUBLISH_LINK: {"link": "https://xhs/x"}})
        patch = only_patch(updates)
        self.assertEqual(patch[NF.STATUS], NS.PUBLISHED, "检测到发布链接回填应置『已发』")
        self.assertIn(NF.PUBLISHED_AT, patch, "置已发应记实际发布日")

    def test_collect_metrics_recent_no_write(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.PUBLISHED, NF.CODE: "PQ-M", NF.PUBLISHED_AT: MS(NOW - timedelta(days=1))})
        self.assertIn("PQ-M", summary.get("metrics_todo", []), "近期已发应进待回流采集清单")
        self.assertEqual(updates, [], "采集阶段不改状态")

    def test_close_loop_when_metrics_window_passed(self):
        _, updates, _ = run_one(
            {NF.STATUS: NS.PUBLISHED, NF.CODE: "PQ-CL", NF.PUBLISHED_AT: MS(NOW - timedelta(days=10))})
        patch = only_patch(updates)
        self.assertEqual(patch[NF.STATUS], NS.LOOPED_BACK, "过了回流窗口应收口置『已回流』")

    def test_remind_review_when_overdue(self):
        summary, updates, _ = run_one(
            {NF.STATUS: NS.DRAFT_PENDING, NF.CODE: "PQ-REV",
             "_state_changed_at": MS(NOW - timedelta(days=2))})
        self.assertEqual(len(summary["review"]), 1, "超时未审应催审")
        self.assertIn("PQ-REV", summary["review"][0])
        self.assertEqual(updates, [], "催审只提醒不写回")


class TestUnknownStatusDrift(unittest.TestCase):
    """状态漂移告警:笔记出现引擎不认识的状态(疑似有人在飞书 UI 加了新 select 选项)→
    显性告警,绝不静默 NOOP。

    why:route 对未知状态返回 NOOP,引擎原样跳过。若运营在飞书加了个「待复审」状态并把笔记
    拖过去,这些笔记会静默卡死——日报里查无此人、无人知道推进器不认识这个状态。这里把
    「未识别状态」钉成一条告警,让状态机 UI 漂移当场显形(呼应本仓库反漂移主线)。"""

    def test_unknown_status_surfaces_and_alerts(self):
        summary, updates, sent = run_one({NF.STATUS: "待复审", NF.CODE: "PQ-UNK"})
        self.assertTrue(any("PQ-UNK" in u for u in summary.get("unknown_status", [])),
                        "未识别状态应进 unknown_status 清单")
        self.assertEqual(updates, [], "未识别状态不应触发任何写回(不猜、不推进)")
        self.assertTrue(any("漂移" in t for t, _txt in sent), "未识别状态应触发状态漂移告警")

    def test_known_status_no_drift_alert(self):
        summary, _, sent = run_one({NF.STATUS: NS.IDEA, NF.CODE: "PQ-OK"})
        self.assertEqual(summary.get("unknown_status", []), [], "已知状态不应误报状态漂移")
        self.assertFalse(any("漂移" in t for t, _txt in sent), "已知状态不应触发漂移告警")


class TestPerNoteResilience(unittest.TestCase):
    """单条坏记录不炸整轮(P6 演练确立的原则)。

    why:heartbeat 挂 cron 无人值守。一条畸形记录(飞书偶发返回缺 fields、或某字段形态诡异
    让 route 抛错)若能掀翻整轮,当天所有笔记都停摆、还刷异常告警。此前 f=r['fields'] 与
    route() 在 per-note try 之外——坏记录直接 KeyError 掉整轮。本测试锁死:坏记录被跳过,
    同轮的好记录照常处理,run 正常返回不抛。"""

    def test_malformed_record_does_not_abort_run(self):
        bad = {"record_id": "recBad"}  # 缺 fields 键(畸形)
        good = {"record_id": "recGood", "fields": {NF.STATUS: NS.IDEA, NF.CODE: "PQ-GOOD"}}
        summary, updates, _ = run_records([bad, good])  # 坏的在前
        self.assertIn("PQ-GOOD", summary["ideas"], "坏记录不应阻断同轮好记录的处理")
        self.assertEqual(updates, [], "本例无写回动作")

    def test_none_fields_record_tolerated(self):
        weird = {"record_id": "recNone", "fields": None}  # fields 为 None
        good = {"record_id": "recG2", "fields": {NF.STATUS: NS.IDEA, NF.CODE: "PQ-G2"}}
        summary, _, _ = run_records([weird, good])
        self.assertIn("PQ-G2", summary["ideas"], "fields=None 不应炸整轮")


class TestMetricsCollection(unittest.TestCase):
    """G7:已发到窗口→COLLECT_METRICS。取到数据写回笔记表;取不到(stub)记待办、不写回。"""

    def test_writes_back_when_collected(self):
        note = {NF.STATUS: NS.PUBLISHED, NF.CODE: "PQ-M", NF.PUBLISHED_AT: MS(NOW - timedelta(days=1)),
                NF.PUBLISH_LINK: {"link": "https://xiaohongshu.com/note/x"}}
        with mock.patch.object(engine.metrics, "collect", return_value={NF.LIKED: 120, NF.COLLECTED: 30}):
            summary, updates, _ = run_one(note)
        self.assertTrue(any(p.get(NF.LIKED) == 120 for _, _, p in updates), "应写回点赞")
        self.assertIn("PQ-M", summary.get("metrics_collected", []))

    def test_todo_when_stub_no_writeback(self):
        note = {NF.STATUS: NS.PUBLISHED, NF.CODE: "PQ-M2", NF.PUBLISHED_AT: MS(NOW - timedelta(days=1)),
                NF.PUBLISH_LINK: {"link": "https://x"}}
        summary, updates, _ = run_one(note)  # 默认 metrics_mode=stub → collect 返 {}
        self.assertIn("PQ-M2", summary.get("metrics_todo", []))
        self.assertEqual(updates, [], "stub 不写回")


class TestUsageBackfillOnPublish(unittest.TestCase):
    """闭环:检测到发布回填→置已发 时,把笔记「关联子素材」的 clip_ids 记进 usage 账本。
    这一步让 G5 回溯 / G6 视图余量 / G3 使用率 从**真实已发笔记**灌数,而非只有测试数据。"""

    def test_publish_records_usage_from_clips(self):
        root = Path(tempfile.mkdtemp())
        orig = engine.mv.ASSET_ROOT
        engine.mv.ASSET_ROOT = root
        try:
            note = {NF.STATUS: NS.TO_PUBLISH, NF.CODE: "PQ-PUB",
                    NF.PUBLISH_LINK: {"link": "https://xhs/x"},
                    NF.CLIPS: "clip_a, clip_b", NF.PLAYBOOK: "考据"}
            summary, updates, _ = run_one(note)
            self.assertTrue(any(p.get(NF.STATUS) == NS.PUBLISHED for _, _, p in updates), "应置已发")
            self.assertEqual(set(mv.note_clips("PQ-PUB", root=root)), {"clip_a", "clip_b"},
                             "发布应把两个 clip 记进 usage 账本")
            self.assertEqual(summary["errors"], [])
        finally:
            engine.mv.ASSET_ROOT = orig

    def test_publish_without_clips_no_usage(self):
        root = Path(tempfile.mkdtemp())
        orig = engine.mv.ASSET_ROOT
        engine.mv.ASSET_ROOT = root
        try:
            note = {NF.STATUS: NS.TO_PUBLISH, NF.CODE: "PQ-NOCLIP",
                    NF.PUBLISH_LINK: {"link": "https://xhs/y"}}
            _, updates, _ = run_one(note)
            self.assertTrue(any(p.get(NF.STATUS) == NS.PUBLISHED for _, _, p in updates), "仍应置已发")
            self.assertEqual(mv.note_clips("PQ-NOCLIP", root=root), [], "没挂子素材则不记 usage")
        finally:
            engine.mv.ASSET_ROOT = orig


class TestE2EChain(unittest.TestCase):
    """端到端集成 smoke:curate(编入视图)→ engine 发布回填 → trace 回溯 → 使用率 → 反馈,
    一条链真跑通(连起盘上视图/账本 + 引擎真实 MARK_PUBLISHED handler + 聚合),catch 各件单测漏的接缝。"""

    def test_curate_publish_trace_usage_feedback(self):
        root = Path(tempfile.mkdtemp())
        orig = engine.mv.ASSET_ROOT
        engine.mv.ASSET_ROOT = root
        try:
            # 1) curate:把一个子素材编入「科普号/考据」视图(不挂 SKU)
            cid = mv.add_select("科普号", "考据", "GY-1", "/raw/v.mp4", "video:0-6", linked=6.0, root=root)
            self.assertEqual(len(mv.view_selects("科普号", "考据", root=root)), 1)

            # 2) publish:一条待发布笔记(关联该 clip)走引擎真实 MARK_PUBLISHED → 回填 usage
            note = {NF.STATUS: NS.TO_PUBLISH, NF.CODE: "PQ-1", NF.PUBLISH_LINK: {"link": "https://xhs/x"},
                    NF.CLIPS: cid, NF.PLAYBOOK: "考据"}
            _, updates, _ = run_one(note)
            self.assertTrue(any(p.get(NF.STATUS) == NS.PUBLISHED for _, _, p in updates))

            # 3) trace:笔记 → clip → 原始素材(回溯贯通)
            tr = mv.trace_note("PQ-1", root=root)
            self.assertEqual(tr[0]["material"], "GY-1")
            self.assertEqual(tr[0]["playbook"], "考据")

            # 4) 使用率:该素材被用掉(used_clips=1)
            self.assertEqual(mv.material_usage("GY-1", total=60, root=root)["used_clips"], 1)

            # 5) 反馈:该方法论一条已发笔记(带点赞)→ 均赞进反馈信号
            agg = metrics.aggregate_by_playbook([{NF.PLAYBOOK: "考据", NF.LIKED: 300}])
            self.assertEqual(agg["考据"]["均赞"], 300.0)
        finally:
            engine.mv.ASSET_ROOT = orig


class TestCostAccounting(unittest.TestCase):
    """成本核算契约(M3):_cost_of_log 优先结构化数值字段,回退解析 详情 里的 cost_cny=。

    why:月成本核算是预算熔断(防 real 模式 LLM 烧穿)的基准。这段字符串 split 一漂
    (详情格式变了/取不到),核算静默归零 → 熔断永不触发 → 跑量烧钱无人察觉。把契约钉死:
    结构化字段在则用它、否则从 详情 稳健取、取不到算 0 绝不炸。纯函数,零网络。"""

    def test_prefers_structured_cost_field(self):
        self.assertEqual(engine._cost_of_log({engine.COST_FIELD: 1.25, RLF.DETAIL: "cost_cny=9.9"}), 1.25,
                         "结构化 成本_元 字段在时应优先于 详情 解析")

    def test_falls_back_to_detail_parse(self):
        self.assertEqual(engine._cost_of_log({RLF.DETAIL: "cost_cny=0.35 llm=real 格式=图文"}), 0.35)

    def test_missing_cost_is_zero(self):
        self.assertEqual(engine._cost_of_log({RLF.DETAIL: "无成本信息"}), 0.0)
        self.assertEqual(engine._cost_of_log({}), 0.0)

    def test_malformed_detail_is_zero_not_crash(self):
        self.assertEqual(engine._cost_of_log({RLF.DETAIL: "cost_cny=abc"}), 0.0)
        self.assertEqual(engine._cost_of_log({RLF.DETAIL: "cost_cny="}), 0.0)

    def test_bool_not_miscounted(self):
        # bool 是 int 子类,不挡掉的话 True 会被当成 ¥1.0 误算
        self.assertEqual(engine._cost_of_log({engine.COST_FIELD: True, RLF.DETAIL: "cost_cny=2.0"}), 2.0)


class TestCostLogging(unittest.TestCase):
    """M3 落库侧:log_run 给了 cost 就写结构化 成本_元 数值字段;没给则不写(向后兼容)。"""

    def _capture_log(self, **kw):
        captured = {}
        with mock.patch.object(feishu_io, "create_record",
                               lambda t, fields: captured.update({"table": t, **fields}) or "rec"):
            feishu_io.log_run("摘要", "生成文案", **kw)
        return captured

    def test_writes_structured_cost_when_given(self):
        cap = self._capture_log(cost=0.35)
        self.assertEqual(cap.get(RLF.COST), 0.35, "给了 cost 应写 成本_元 数值字段")
        self.assertEqual(cap.get("table"), "运行日志表")

    def test_omits_cost_when_none(self):
        self.assertNotIn(RLF.COST, self._capture_log(), "没给 cost 不写该字段(旧日志向后兼容)")


if __name__ == "__main__":
    unittest.main()
