"""月度成本核算 + 告警(ADR-0009:BUDGET_MONTHLY_CNY 曾是零消费的纸面数字)。

读运行日志表『成本_元』求和(当月),超 config.BUDGET_MONTHLY_CNY → 返回告警文案,
由 daily_dispatch 推 alerts.send(把"设了没执行"的告警阈值真正接上)。纯读,不写库。
成本来源已齐:出稿 LLM(draft_one log_run cost)+ 豆包看图(tag_materials.run 汇总 log_run(action=看图打标));
豆包费率是 config.VISION_COST_PER_1K_CNY 的保守估值,待第一份 ARK 账单校准(env 覆盖)。残留:改写去重/模型分档未做。
"""
from __future__ import annotations

from datetime import date

from . import bitable, config, feishu_io
from .bitable import RunLogFields as RLF


def _cost(v) -> float:
    """成本_元 字段值 → float(容错 int/str/list/dict/None,坏值当 0)。"""
    if isinstance(v, list):
        v = v[0] if v else 0
    if isinstance(v, dict):
        v = v.get("value") or v.get("text") or 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def monthly_cost_cny(records: list | None = None, today: date | None = None) -> float:
    """当月已花『成本_元』合计(读运行日志表)。records/today 注入 → 直测。"""
    ym = today or date.today()
    rows = records if records is not None else feishu_io.list_records(RLF.TABLE)
    total = 0.0
    for r in rows:
        ts = bitable.parse_ts(r["fields"].get(RLF.TIME))
        if ts and ts.year == ym.year and ts.month == ym.month:
            total += _cost(r["fields"].get(RLF.COST))
    return round(total, 3)


def budget_alert(records: list | None = None, today: date | None = None) -> str:
    """超月度预算 → 告警文案(供 alerts.send);没超 → ''。"""
    spent = monthly_cost_cny(records, today)
    if spent >= config.BUDGET_MONTHLY_CNY:
        return (f"⚠️ 月度 LLM 成本 {spent} 元 已达/超阈值 {config.BUDGET_MONTHLY_CNY} 元"
                f"——请检查用量(停派活 / 调 GY_BUDGET_MONTHLY_CNY)")
    return ""
