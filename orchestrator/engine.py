"""engine:读表 → runbook 路由 → 执行 → 写回 + 运行日志。单实例(flock),顶层异常即时告警。
确定性骨架:engine 自身零 LLM;LLM 只在 GEN_COPY 动作内经 llm.gen_copy 调用(预算帽)。
"""
from __future__ import annotations

import fcntl
import traceback
from datetime import datetime
from typing import Callable

from . import alerts, bitable, config, feishu_io, guard, llm, metrics, reminders
from .bitable import ContentTypeFields as CTF
from .bitable import NoteFields as NF
from .bitable import NoteStatus as NS
from .bitable import RunLogFields as RLF
from .bitable import parse_ts as _rb_ts
from .runbook import Action, route
from lib import material_view as mv  # 盘上使用账本(纯叶子,无反向依赖)

LOCK_FILE = config.WORKSPACE / "locks" / "orchestrator.lock"

# 引擎认识的状态全集(=状态机 NoteStatus 的 9 个取值)。笔记状态落在此集之外 = UI 加了
# 推进器不认识的状态,应显性告警而非静默 NOOP(反漂移主线;runbook 注释承诺的"记告警"在此兑现)。
_KNOWN_STATUSES = frozenset(bitable.declared_field_names(bitable.NoteStatus))


def _account_of(fields: dict) -> str:
    return bitable.text(fields.get(NF.ACCOUNT)) or "未知账号"  # 委托 adapter(候选A:去重)


def _ctype_format_map() -> dict:
    """内容类型名 → 格式(图文/视频)。引擎格式感知的查表(呼应'有些是图文')。"""
    m = {}
    try:
        for r in feishu_io.list_records("内容类型表"):
            name = bitable.text(r["fields"].get(CTF.NAME))
            fmt = r["fields"].get(CTF.FORMAT)
            if name and fmt:
                m[name] = fmt
    except Exception:  # noqa: BLE001
        pass
    return m


def _format_of(fields: dict, fmt_map: dict) -> str:
    ctn = bitable.text(fields.get(NF.CONTENT_TYPE))
    return fmt_map.get(ctn.split(",")[0], "")


def _next_step(fmt: str) -> str:
    """按格式提示下一步产物。"""
    if fmt == "视频":
        return "需走视频链(storyboard→previz→editing)"
    if fmt == "图文":
        return "需配图(cover/images)"
    return "格式未定"


def _shoot_hint(fields: dict) -> str:
    """F2:催拍带上要拍什么。优先 脚本·分镜,退回 内容类型/关联衣服。"""
    for key in (NF.STORYBOARD, NF.CONTENT_TYPE, NF.LINKED_CLOTHES):
        txt = bitable.text(fields.get(key)).strip()
        if txt:
            return f"拍:{txt[:40]}"
    return "拍:见记录"


def _title_of(fields: dict) -> str:
    return bitable.text(fields.get(NF.CODE)) or "?"  # 委托 adapter


def _usage_projection_drift(notes: list[dict]) -> list[dict]:
    """对账:已发布笔记的 Bitable「关联子素材」投影 vs 盘上 usage 账本。

    usage 账本是唯一真值；Bitable 字段是只写投影。若发布后有人改了字段，或账本写入失败，
    这里显性报漂移，避免两套状态长期不一致。
    """
    out = []
    for r in notes:
        fields = r.get("fields") or {}
        status = bitable.text(fields.get(NF.STATUS)).strip()
        if status not in {NS.PUBLISHED, NS.LOOPED_BACK}:
            continue
        note = _title_of(fields)
        if note == "?":
            continue
        projected = {c.strip() for c in bitable.text(fields.get(NF.CLIPS)).split(",") if c.strip()}
        ledger = set(mv.note_clips(note, root=mv.ASSET_ROOT))
        if projected != ledger:
            out.append({
                "note": note,
                "missing_in_ledger": sorted(projected - ledger),
                "extra_in_ledger": sorted(ledger - projected),
            })
    return out


class _Ctx:
    """一轮推进的可变上下文:run 级共享(计数器/汇总/配置)+ 每条笔记切换的 f/rid/name。
    handler 只碰 ctx——把'选哪个动作'(runbook.route)和'动作干什么'(下面的 _h_*)解耦。"""

    def __init__(self, *, now: datetime, fmt_map: dict, budget_blown: bool, llm_mode: str,
                 summary: dict, pending_pub_by_account: dict, metrics_mode: str = "stub"):
        self.now = now
        self.fmt_map = fmt_map
        self.budget_blown = budget_blown
        self.llm_mode = llm_mode
        self.metrics_mode = metrics_mode
        self.summary = summary
        self.pending_pub_by_account = pending_pub_by_account
        self.generated = 0            # run 级:本轮已生成文案数(成本闸计数)
        self.f: dict = {}             # 以下每条笔记切换
        self.rid = ""
        self.name = ""


def _h_list_idea(ctx: _Ctx) -> None:
    ctx.summary["ideas"].append(ctx.name)


def _h_remind_shoot(ctx: _Ctx) -> None:
    if reminders.should_remind(ctx.rid, "shoot", ctx.now):  # F1 节流:每日最多一次
        ctx.summary["shoot"].append(f"{ctx.name}({_shoot_hint(ctx.f)}) {config.record_url('笔记表', ctx.rid)}")
        reminders.mark(ctx.rid, "shoot", ctx.now)


def _h_remind_review(ctx: _Ctx) -> None:
    if reminders.should_remind(ctx.rid, "review", ctx.now):
        ctx.summary["review"].append(f"{ctx.name} {config.record_url('笔记表', ctx.rid)}")
        reminders.mark(ctx.rid, "review", ctx.now)


def _h_gen_copy(ctx: _Ctx) -> None:
    if not guard.copy_quota_left(ctx.generated):
        return
    if ctx.budget_blown:
        ctx.summary["errors"].append(f"{ctx.name}: 月度预算熔断,跳过生成")
        return
    text, cost, gen_skill = llm.gen_copy(ctx.f, ctx.llm_mode)  # G13:gen_skill=该方法论的生成技能
    feishu_io.update_record("笔记表", ctx.rid, {
        NF.DRAFT: text, NF.STATUS: NS.DRAFT_PENDING, NF.AI_DECLARED: True,
    })
    ctx.generated += 1
    ctx.summary["copy_cost_cny"] += cost
    fmt = _format_of(ctx.f, ctx.fmt_map)
    ctx.summary.setdefault("next_产物", []).append(f"{ctx.name}[{fmt or '?'}]:{_next_step(fmt)}")
    feishu_io.log_run(f"文案草稿生成:{ctx.name}({fmt})", "生成文案", skill=gen_skill,
                      note_ref=ctx.name, cost=cost,
                      detail=f"cost_cny={cost} llm={ctx.llm_mode} 格式={fmt} 下一步={_next_step(fmt)}")


def _h_assemble_package(ctx: _Ctx) -> None:
    # AI声明门动真格(审查 H2):不代填。GEN_COPY 会置位;人工路径必须人在表里勾。
    guard.assert_ai_declared(ctx.f)
    acc = _account_of(ctx.f)
    guard.assert_publish_quota(ctx.pending_pub_by_account.get(acc, 0))
    feishu_io.update_record("笔记表", ctx.rid, {NF.STATUS: NS.TO_PUBLISH})
    ctx.pending_pub_by_account[acc] = ctx.pending_pub_by_account.get(acc, 0) + 1
    pkg = _package_text(ctx.f, ctx.name, config.record_url("笔记表", ctx.rid))
    ctx.summary["packages"].append(pkg)
    feishu_io.log_run(f"发布包就绪:{ctx.name}", "组装发布包", result="待人审",
                      note_ref=ctx.name, detail=pkg[:300])


def _record_note_usage(ctx: _Ctx) -> int:
    """发布即回填使用账本:该笔记「关联子素材」里的 clip_ids → mv.record_usage(note, playbook)。
    让 G5 回溯 / G6 视图余量 / G3 使用率从真实已发笔记灌数。盘上账本,失败不阻断置已发主流程。"""
    clips = [c.strip() for c in bitable.text(ctx.f.get(NF.CLIPS)).split(",") if c.strip()]
    if not clips:
        return 0
    pb = bitable.text(ctx.f.get(NF.PLAYBOOK))
    ts = int(ctx.now.timestamp() * 1000)
    try:
        for cid in clips:
            mv.record_usage(cid, ctx.name, pb, ts=ts, root=mv.ASSET_ROOT)
        return len(clips)
    except Exception as e:  # noqa: BLE001  账本是降噪账本,记不上不该拦住"置已发"
        ctx.summary["errors"].append(f"{ctx.name}: usage回填失败 {type(e).__name__}: {e}")
        return 0


def _h_mark_published(ctx: _Ctx) -> None:
    feishu_io.update_record("笔记表", ctx.rid, {
        NF.PUBLISHED_AT: int(ctx.now.timestamp() * 1000), NF.STATUS: NS.PUBLISHED,
    })
    n = _record_note_usage(ctx)  # 发布回填 usage
    feishu_io.log_run(f"检测到发布回填:{ctx.name}(记 {n} 子素材使用)", "置已发", note_ref=ctx.name)


def _h_collect_metrics(ctx: _Ctx) -> None:
    # 效果取数走零封号非登录链(G7:metrics.collect→xhs_fetch)。默认 stub 零成本;real 才真取。
    url = bitable.text(ctx.f.get(NF.PUBLISH_LINK))
    got = metrics.collect(url, ctx.metrics_mode)
    if got:
        feishu_io.update_record("笔记表", ctx.rid, got)   # 写回点赞/收藏/评论/转发(热度分 Bitable 自算)
        ctx.summary.setdefault("metrics_collected", []).append(ctx.name)
    else:
        ctx.summary.setdefault("metrics_todo", []).append(ctx.name)  # 未取到:记待办,下轮重试


def _h_close_loop(ctx: _Ctx) -> None:
    feishu_io.update_record("笔记表", ctx.rid, {NF.STATUS: NS.LOOPED_BACK})
    feishu_io.log_run(f"回流收口:{ctx.name}", "置已回流", note_ref=ctx.name)


# 动作分发表:新增动作 = 加一个 _h_*(ctx) + 在此登记一行(不再动 run() 的循环体)
DISPATCH = {
    Action.LIST_IDEA: _h_list_idea,
    Action.REMIND_SHOOT: _h_remind_shoot,
    Action.REMIND_REVIEW: _h_remind_review,
    Action.GEN_COPY: _h_gen_copy,
    Action.ASSEMBLE_PACKAGE: _h_assemble_package,
    Action.MARK_PUBLISHED: _h_mark_published,
    Action.COLLECT_METRICS: _h_collect_metrics,
    Action.CLOSE_LOOP: _h_close_loop,
}


def run(mode: str = "heartbeat", llm_mode: str = "stub", limit: int = 20,
        preflight: Callable[[], dict] | None = None) -> dict:
    """一轮推进。preflight 在取得单 writer 锁后、读取 Note 前执行。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    LOCK_FILE.parent.mkdir(exist_ok=True)
    lf = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("另一实例运行中,退出")
        return {"skipped": "locked"}

    now = datetime.now()
    summary: dict = {"mode": mode, "env": config.ENV_NAME, "actions": [], "ideas": [], "shoot": [],
                     "review": [], "packages": [], "errors": [], "unknown_status": [], "usage_drift": [],
                     "copy_cost_cny": 0.0}
    try:
        if preflight is not None:
            planning = preflight()
            summary["planning"] = planning
            summary["errors"].extend(f"排产:{e}" for e in planning.get("errors", []))
        notes = feishu_io.list_records("笔记表")
        summary["usage_drift"] = _usage_projection_drift(notes)
        if summary["usage_drift"]:
            alerts.send(
                "\n".join(
                    f"{d['note']}: ledger缺{d['missing_in_ledger'] or '[]'} / ledger多{d['extra_in_ledger'] or '[]'}"
                    for d in summary["usage_drift"][:5]
                ),
                title="usage账本漂移",
            )
        # 月度成本熔断(审查 M1):real 模式先核算,超限本轮拒绝生成
        monthly_cost = _monthly_cost_cny() if llm_mode == "real" else 0.0
        budget_blown = monthly_cost > config.BUDGET_MONTHLY_CNY
        if budget_blown:
            alerts.send(f"⚠️ 月成本 ¥{monthly_cost:.1f} 超阈 ¥{config.BUDGET_MONTHLY_CNY:.0f},本轮停止文案生成",
                        title="成本熔断")
        fmt_map = _ctype_format_map()  # 格式感知(图文/视频)
        pending_pub_by_account: dict[str, int] = {}
        for r in notes:
            f = r.get("fields") or {}  # 畸形记录(缺 fields/None)不炸预扫描
            if counts_toward_publish_quota(f, now):
                acc = _account_of(f)
                pending_pub_by_account[acc] = pending_pub_by_account.get(acc, 0) + 1
            st = bitable.text(f.get(NF.STATUS)).strip()
            if st and st not in _KNOWN_STATUSES:  # UI 加了引擎不认识的状态:显性记录不静默
                summary["unknown_status"].append(f"{_title_of(f)}: 未识别状态「{st}」")

        ctx = _Ctx(now=now, fmt_map=fmt_map, budget_blown=budget_blown, llm_mode=llm_mode,
                   summary=summary, pending_pub_by_account=pending_pub_by_account,
                   metrics_mode=config.METRICS_MODE)
        for r in notes[: max(limit, 0) or len(notes)]:
            act = None
            ctx.f = r.get("fields") or {}   # 畸形记录不炸整轮:降级为空 fields → route 判 NOOP 跳过
            ctx.rid = r.get("record_id", "")
            ctx.name = _title_of(ctx.f)
            try:
                # route/解析也纳入 per-note 兜底:某条状态形态诡异不该掀翻整轮(单条失败不炸整轮)
                act = route(ctx.f, now, config.REVIEW_OVERDUE_HOURS, config.METRICS_CLOSE_DAYS)
                handler = DISPATCH.get(act)
                if handler is None:  # NOOP 或未登记动作:不动
                    continue
                summary["actions"].append((ctx.name, act.value))
                handler(ctx)
            except guard.GuardError as ge:
                summary["errors"].append(f"{ctx.name}: {ge}")
                feishu_io.log_run(f"硬闸拒绝:{ctx.name}", act.value if act else "路由", result="失败",
                                  note_ref=ctx.name, detail=str(ge))
                alerts.send(f"硬闸拒绝 {ctx.name}: {ge}")
            except Exception as e:  # noqa: BLE001  单条失败不炸整轮(P6演练发现):记错继续,下轮自然重试
                summary["errors"].append(f"{ctx.name}: {type(e).__name__}: {e}")
                feishu_io.log_run(f"动作失败:{ctx.name}", act.value if act else "路由/解析", result="失败",
                                  note_ref=ctx.name, detail=f"{type(e).__name__}: {e}"[:600])
        generated = ctx.generated

        if summary["unknown_status"]:  # 状态漂移:UI 出现引擎不认识的状态,显性告警不静默卡死
            alerts.send(
                f"⚠️ {len(summary['unknown_status'])} 条笔记状态推进器不认识(疑似飞书 UI 加了新状态,"
                f"这些笔记会静默卡死):\n" + "\n".join(f"· {x}" for x in summary["unknown_status"][:8]),
                title="状态漂移告警")
        if mode == "daily":
            mc = _monthly_cost_cny()
            summary["monthly_cost_cny"] = mc
            if mc > config.BUDGET_MONTHLY_CNY:
                alerts.send(f"⚠️ 本月 LLM 成本 ¥{mc:.1f} 已超阈值 ¥{config.BUDGET_MONTHLY_CNY:.0f}",
                            title="成本告警")
            alerts.send(_digest(summary, now) + f"\n本月累计 LLM 成本 ¥{mc:.2f}", title="观云日报(推进器)")
        elif summary["review"] or summary["shoot"]:
            alerts.send(_digest(summary, now), title="观云巡检提醒")
        for pkg in summary["packages"]:
            alerts.send(pkg, title="待发布|人工确认")
        feishu_io.log_run(
            f"{mode} 一轮完成:动作{len(summary['actions'])} 生成{generated} 错误{len(summary['errors'])}",
            f"{mode}轮询", result="成功" if not summary["errors"] else "失败",
            detail=f"cost_cny={summary['copy_cost_cny']}")
        return summary
    except Exception:
        tb = traceback.format_exc()
        alerts.send(f"推进器异常退出({mode}):\n{tb[-500:]}", title="⚠️告警")
        try:
            feishu_io.log_run(f"{mode} 异常退出", f"{mode}轮询", result="失败", detail=tb[-800:])
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()


def counts_toward_publish_quota(fields: dict, now: datetime) -> bool:
    """控量口径(审查 H1):待发布=已排队占额(无论有没有实际发布日);已发只算今天的。纯函数可测。"""
    st = fields.get(NF.STATUS)
    if st == NS.TO_PUBLISH:
        return True
    return st == NS.PUBLISHED and _is_today(fields.get(NF.PUBLISHED_AT), now)


# 运行日志表数值成本字段(元)——已在测试库落字段(issue#10 M3)。
# _cost_of_log 优先读它;历史日志(无此字段)继续走 详情 里 cost_cny= 的回退解析。
COST_FIELD = RLF.COST


def _cost_of_log(fields: dict) -> float:
    """一条运行日志的 LLM 成本(元)。优先结构化数值字段,回退解析 详情 里的 cost_cny=。
    把脆弱的字符串 split 隔离进这一处纯函数——可单测、契约可锁,不再散在核算循环里(审查 M3)。"""
    v = fields.get(COST_FIELD)
    if isinstance(v, bool):  # Bitable 不会给 bool,但 bool 是 int 子类,先挡掉防误算
        v = None
    if isinstance(v, (int, float)):
        return float(v)
    detail = str(fields.get(RLF.DETAIL) or "")
    if "cost_cny=" in detail:
        try:
            return float(detail.split("cost_cny=")[1].split()[0])
        except (ValueError, IndexError):
            return 0.0
    return 0.0


def _monthly_cost_cny() -> float:
    """月度 LLM 成本累计:扫运行日志表本月成本(运维三件套之二)。"""
    total = 0.0
    month = datetime.now().strftime("%Y-%m")
    try:
        for r in feishu_io.list_records("运行日志表"):
            f = r["fields"]
            t = _rb_ts(f.get(RLF.TIME))
            if not t or t.strftime("%Y-%m") != month:
                continue
            total += _cost_of_log(f)
    except Exception as e:  # noqa: BLE001
        print(f"[月成本核算降级] {e}")
    return round(total, 2)


def _is_today(ms, now: datetime) -> bool:
    if not ms:
        return False
    try:
        return datetime.fromtimestamp(int(ms) / 1000).date() == now.date()
    except (ValueError, TypeError, OSError):
        return False


def _package_text(f: dict, name: str, url: str = "") -> str:
    draft = str(f.get(NF.DRAFT) or "")[:120]
    mats = [m for m in bitable.text(f.get(NF.LINKED_MATERIALS)).split(",") if m.strip()]
    mat_line = (f"配套素材({len(mats)}):{'、'.join(mats)}" if mats
                else "⚠️ 未挂配套素材——发布前请在「关联素材」挂图/视频(小红书没图发不出)")
    return (f"发布包|{name}|{_account_of(f)}\n文案:{draft}…\n{mat_line}\n记录:{url}\n"
            f"⚠️ 发布时必须在小红书 App 勾选「AI 生成」声明;发完把链接回填「发布链接」。")


def _digest(s: dict, now: datetime) -> str:
    lines = [f"{now:%m-%d %H:%M} 环境:{s['env']}"]
    if s["ideas"]:
        lines.append(f"想法储备 {len(s['ideas'])}:{'、'.join(s['ideas'][:5])}")
    if s["shoot"]:
        lines.append(f"催拍 {len(s['shoot'])}:")
        lines += [f"· {x}" for x in s["shoot"][:5]]  # F4:每条一行,手机可扫
    if s["review"]:
        lines.append(f"催审(>{config.REVIEW_OVERDUE_HOURS}h) {len(s['review'])}:")
        lines += [f"· {x}" for x in s["review"][:5]]
    if s["packages"]:
        lines.append(f"发布包 {len(s['packages'])} 个已推送")
    if s.get("metrics_todo"):  # F3:幽灵动作显形
        lines.append(f"待回流采集 {len(s['metrics_todo'])}:{'、'.join(s['metrics_todo'][:5])}")
    if s.get("next_产物"):  # 格式感知:图文需配图/视频走视频链
        lines.append(f"待产物 {len(s['next_产物'])}:")
        lines += [f"· {x}" for x in s["next_产物"][:5]]
    if s.get("unknown_status"):  # 状态漂移显形
        lines.append(f"⚠️ 未识别状态 {len(s['unknown_status'])}:{'、'.join(s['unknown_status'][:5])}")
    if s["errors"]:
        lines.append(f"⚠️ 错误 {len(s['errors'])}:{s['errors'][:2]}")
    if s["copy_cost_cny"]:
        lines.append(f"本轮 LLM 成本 ¥{s['copy_cost_cny']:.2f}")
    return "\n".join(lines) if len(lines) > 1 else lines[0] + "\n无事可做,一切正常"
