"""engine:读表 → runbook 路由 → 执行 → 写回 + 运行日志。单实例(flock),顶层异常即时告警。
确定性骨架:engine 自身零 LLM;LLM 只在 GEN_COPY 动作内经 llm.gen_copy 调用(预算帽)。
"""
from __future__ import annotations

import fcntl
import traceback
from datetime import datetime
from pathlib import Path

from . import alerts, config, feishu_io, guard, llm
from .runbook import Action, route
from .runbook import _ts as _rb_ts

LOCK_FILE = config.WORKSPACE / "locks" / "orchestrator.lock"


def _account_of(fields: dict) -> str:
    v = fields.get("账号(自动)")
    if isinstance(v, list) and v:
        v0 = v[0]
        return v0.get("text", "") if isinstance(v0, dict) else str(v0)
    return str(v or "未知账号")


def _title_of(fields: dict) -> str:
    t = fields.get("排期编号")
    if isinstance(t, list):
        t = "".join(x.get("text", "") for x in t if isinstance(x, dict))
    return str(t or "?")


def run(mode: str = "heartbeat", llm_mode: str = "stub", limit: int = 20) -> dict:
    """一轮推进。返回 summary dict(供日报/测试断言)。"""
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
                     "review": [], "packages": [], "errors": [], "copy_cost_cny": 0.0}
    try:
        notes = feishu_io.list_records("笔记表")
        generated = 0
        # 月度成本熔断(审查 M1):real 模式先核算,超限本轮拒绝生成
        monthly_cost = _monthly_cost_cny() if llm_mode == "real" else 0.0
        budget_blown = monthly_cost > config.BUDGET_MONTHLY_CNY
        if budget_blown:
            alerts.send(f"⚠️ 月成本 ¥{monthly_cost:.1f} 超阈 ¥{config.BUDGET_MONTHLY_CNY:.0f},本轮停止文案生成",
                        title="成本熔断")
        pending_pub_by_account: dict[str, int] = {}
        for r in notes:
            f = r["fields"]
            if counts_toward_publish_quota(f, now):
                acc = _account_of(f)
                pending_pub_by_account[acc] = pending_pub_by_account.get(acc, 0) + 1

        for r in notes[: max(limit, 0) or len(notes)]:
            f, rid = r["fields"], r["record_id"]
            name = _title_of(f)
            act = route(f, now, config.REVIEW_OVERDUE_HOURS, config.METRICS_CLOSE_DAYS)
            if act is Action.NOOP:
                continue
            summary["actions"].append((name, act.value))
            try:
                if act is Action.LIST_IDEA:
                    summary["ideas"].append(name)
                elif act is Action.REMIND_SHOOT:
                    summary["shoot"].append(f"{name} {config.record_url('笔记表', rid)}")
                elif act is Action.REMIND_REVIEW:
                    summary["review"].append(f"{name} {config.record_url('笔记表', rid)}")
                elif act is Action.GEN_COPY:
                    if not guard.copy_quota_left(generated):
                        continue
                    if budget_blown:
                        summary["errors"].append(f"{name}: 月度预算熔断,跳过生成")
                        continue
                    text, cost = llm.gen_copy(f, llm_mode)
                    feishu_io.update_record("笔记表", rid, {
                        "文案草稿": text, "状态": "草稿待发", "AI声明": True,
                    })
                    generated += 1
                    summary["copy_cost_cny"] += cost
                    feishu_io.log_run(f"文案草稿生成:{name}", "生成文案", skill="write-xiaohongshu",
                                      note_ref=name, detail=f"cost_cny={cost} llm={llm_mode}")
                elif act is Action.ASSEMBLE_PACKAGE:
                    # AI声明门动真格(审查 H2):不代填。GEN_COPY 会置位;人工路径必须人在表里勾。
                    guard.assert_ai_declared(f)
                    acc = _account_of(f)
                    guard.assert_publish_quota(pending_pub_by_account.get(acc, 0))
                    feishu_io.update_record("笔记表", rid, {"状态": "待发布"})
                    pending_pub_by_account[acc] = pending_pub_by_account.get(acc, 0) + 1
                    pkg = _package_text(f, name, config.record_url("笔记表", rid))
                    summary["packages"].append(pkg)
                    feishu_io.log_run(f"发布包就绪:{name}", "组装发布包", result="待人审",
                                      note_ref=name, detail=pkg[:300])
                elif act is Action.MARK_PUBLISHED:
                    feishu_io.update_record("笔记表", rid, {
                        "实际发布日": int(now.timestamp() * 1000), "状态": "已发",
                    })
                    feishu_io.log_run(f"检测到发布回填:{name}", "置已发", note_ref=name)
                elif act is Action.COLLECT_METRICS:
                    # 效果取数走零封号链(P6 接线 xhs_fetch);当前记待办不阻塞
                    summary.setdefault("metrics_todo", []).append(name)
                elif act is Action.CLOSE_LOOP:
                    feishu_io.update_record("笔记表", rid, {"状态": "已回流"})
                    feishu_io.log_run(f"回流收口:{name}", "置已回流", note_ref=name)
            except guard.GuardError as ge:
                summary["errors"].append(f"{name}: {ge}")
                feishu_io.log_run(f"硬闸拒绝:{name}", act.value, result="失败", note_ref=name, detail=str(ge))
                alerts.send(f"硬闸拒绝 {name}: {ge}")
            except Exception as e:  # noqa: BLE001  单条失败不炸整轮(P6演练发现):记错继续,下轮自然重试
                summary["errors"].append(f"{name}: {type(e).__name__}: {e}")
                feishu_io.log_run(f"动作失败:{name}", act.value, result="失败", note_ref=name,
                                  detail=f"{type(e).__name__}: {e}"[:600])

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
    st = fields.get("状态")
    if st == "待发布":
        return True
    return st == "已发" and _is_today(fields.get("实际发布日"), now)


def _monthly_cost_cny() -> float:
    """月度 LLM 成本累计:扫运行日志表本月 cost_cny= 明细(运维三件套之二)。"""
    total = 0.0
    month = datetime.now().strftime("%Y-%m")
    try:
        for r in feishu_io.list_records("运行日志表"):
            f = r["fields"]
            t = _rb_ts(f.get("时间"))
            if not t or t.strftime("%Y-%m") != month:
                continue
            detail = str(f.get("详情") or "")
            if "cost_cny=" in detail:
                try:
                    total += float(detail.split("cost_cny=")[1].split()[0])
                except (ValueError, IndexError):
                    pass
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
    draft = str(f.get("文案草稿") or "")[:120]
    return (f"发布包|{name}|{_account_of(f)}\n文案:{draft}…\n记录:{url}\n"
            f"⚠️ 发布时必须在小红书 App 勾选「AI 生成」声明;发完把链接回填「发布链接」。")


def _digest(s: dict, now: datetime) -> str:
    lines = [f"{now:%m-%d %H:%M} 环境:{s['env']}"]
    if s["ideas"]:
        lines.append(f"想法储备 {len(s['ideas'])}:{'、'.join(s['ideas'][:5])}")
    if s["shoot"]:
        lines.append(f"催拍 {len(s['shoot'])}:{'、'.join(s['shoot'][:5])}")
    if s["review"]:
        lines.append(f"催审(>{config.REVIEW_OVERDUE_HOURS}h) {len(s['review'])}:{'、'.join(s['review'][:5])}")
    if s["packages"]:
        lines.append(f"发布包 {len(s['packages'])} 个已推送")
    if s["errors"]:
        lines.append(f"⚠️ 错误 {len(s['errors'])}:{s['errors'][:2]}")
    if s["copy_cost_cny"]:
        lines.append(f"本轮 LLM 成本 ¥{s['copy_cost_cny']:.2f}")
    return "\n".join(lines) if len(lines) > 1 else lines[0] + "\n无事可做,一切正常"
