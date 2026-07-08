"""orchestrator 配置:环境、Base 守卫常量、表名解析、阈值。零 LLM 零网络(纯读本地)。"""
from __future__ import annotations

import json
import os
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]

# 已知 Base(守卫用):生产绝不默认可写
PROD_BASE = "N9IVbi6pTatJG5sqyTTcc0vSn4g"
TEST_BASE = "ZhzJbfkOsafwevsWkW8cfoILnfb"


def _load_env() -> None:
    p = WORKSPACE / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

BASE_TOKEN = os.environ.get("LARK_APP_TOKEN", "")
TEST_MODE = os.environ.get("TEST_MODE", "1") == "1"
ENV_NAME = "test" if BASE_TOKEN == TEST_BASE else ("prod" if BASE_TOKEN == PROD_BASE else "unknown")

# 阈值(可 env 覆盖)
PER_RUN_COPY_LIMIT = int(os.environ.get("GY_PER_RUN_COPY_LIMIT",
                                        os.environ.get("GY_DAILY_COPY_LIMIT", "2")))  # 每轮生成上限(审查 M3 更名)
PER_ACCOUNT_DAILY_PUBLISH = int(os.environ.get("GY_ACCOUNT_DAILY_PUB", "3"))  # 单号每日发布上限(红线)
REVIEW_OVERDUE_HOURS = int(os.environ.get("GY_REVIEW_OVERDUE_H", "24"))     # 待审超时催审
METRICS_CLOSE_DAYS = int(os.environ.get("GY_METRICS_CLOSE_DAYS", "7"))      # 已发 N 天后回流收口
BUDGET_MONTHLY_CNY = float(os.environ.get("GY_BUDGET_MONTHLY_CNY", "300"))  # 月度 LLM 成本告警阈值
PER_RUN_BUDGET_USD = float(os.environ.get("GY_PER_RUN_BUDGET_USD", "1.2"))  # 单次 claude -p 预算帽(P6实测:长文0.5不够)


TENANT_HOST = os.environ.get("GY_TENANT_HOST", "ccn925h7lg9d.feishu.cn")


def record_url(table_name: str, record_id: str) -> str:
    """记录深链:飞书卡片/消息里一点直达该行(P5)。"""
    return f"https://{TENANT_HOST}/base/{BASE_TOKEN}?table={tables()[table_name]}&record={record_id}"


def tables(env: str | None = None) -> dict[str, str]:
    """表名→table_id(按名注入,唯一取表入口)。"""
    e = env or ENV_NAME
    p = WORKSPACE / "schema" / e / "_tables.json"
    return json.loads(p.read_text(encoding="utf-8"))["tables"]
