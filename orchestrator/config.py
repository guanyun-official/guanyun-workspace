"""orchestrator 配置:环境、Base 守卫常量、表名解析、阈值。零 LLM 零网络(纯读本地)。"""
from __future__ import annotations

import json
import os
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]

# 已知 Base(守卫用):生产绝不默认可写
PROD_BASE = "N9IVbi6pTatJG5sqyTTcc0vSn4g"
TEST_BASE = "ZhzJbfkOsafwevsWkW8cfoILnfb"

# 多品牌接口留出(目前仅巧荷):brand → 各环境 Base token 注册表。
# 短期决策"一品牌一 Base 一进程"(进程起时 LARK_APP_TOKEN 选 Base、--brand 选 brands/<brand>/ 数据),
# 故此处只需登记合法 Base,供 guard.assert_base_allowed 的白名单;**加第 2 品牌 = 加一行**(建好其 Base 后填 token)。
BRAND_BASES: dict[str, dict[str, str]] = {
    "巧荷": {"prod": PROD_BASE, "test": TEST_BASE},
}


def known_bases(env: str) -> set[str]:
    """某环境(test/prod)所有已登记品牌的 Base token 集合(guard 白名单据此;多品牌唯一扩展点)。"""
    return {b[env] for b in BRAND_BASES.values() if b.get(env)}


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
PER_ACCOUNT_DAILY_PUBLISH = int(os.environ.get("GY_ACCOUNT_DAILY_PUB", "3"))  # 单号每日发布上限(红线)
COLLECT_REFRESH_DAYS = int(os.environ.get("GY_COLLECT_REFRESH_DAYS", "30"))  # 回流刷新窗:超此天数的已回流帖热度已定,不再重刷(冷热分离,防累积态全拉)
REVIEW_OVERDUE_HOURS = int(os.environ.get("GY_REVIEW_OVERDUE_H", "24"))     # 待审超时催审
METRICS_CLOSE_DAYS = int(os.environ.get("GY_METRICS_CLOSE_DAYS", "7"))      # 已发 N 天后回流收口
BUDGET_MONTHLY_CNY = float(os.environ.get("GY_BUDGET_MONTHLY_CNY", "300"))  # 月度 LLM 成本告警阈值
PER_RUN_BUDGET_USD = float(os.environ.get("GY_PER_RUN_BUDGET_USD", "1.2"))  # 单次 claude -p 预算帽(P6实测:长文0.5不够)
METRICS_MODE = os.environ.get("GY_METRICS_MODE", "stub")  # 效果采集:stub 零成本 / real 走 metrics 直连 xhs-extract-master 非登录取数(G7)

# 看图打标(多模态)后端(vision.py seam):doubao(ARK,便宜,默认)/ claude(claude -p 兜底,零 key)。
# ARK_API_KEY 从 env 读——明文凭证绝不入代码/库;doubao 后端缺 key 时 vision 报错(不静默)。
# 打标并发度(护本机负载的旋钮):看图打标并发跑几批。转码=本机CPU大头,本地默认低(护笔记本),
# 上线服务器可 GY_TAG_CONCURRENCY 调高。"串行不并发"红线=别把高负载压用户本机,不是禁打标并发。
TAG_CONCURRENCY = int(os.environ.get("GY_TAG_CONCURRENCY", "4"))

# 视频入库开关(护本机):baidu 网盘无 range/直链外部被拒(实测403/503),视频只能下整包;
# 视频底片=GB级raw剪辑原料(实测 median 511MB/条),下载=带宽+磁盘重活。**默认关(0)**——本机不碰视频入库
# (raw 走 video-editing 出成片,成片才入库打标);服务器/确需时 GY_INGEST_VIDEO=1(下载一次→多帧→缓存帧→删)。
INGEST_VIDEO = os.environ.get("GY_INGEST_VIDEO", "0") == "1"
VISION_BACKEND = os.environ.get("GY_VISION_BACKEND", "doubao")
VISION_MODEL = os.environ.get("GY_VISION_MODEL", "doubao-seed-2-0-mini-260428")
ARK_ENDPOINT = os.environ.get("GY_ARK_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
# 看图成本估算费率(元/1K tokens):打标成本=实测 usage.total_tokens/1000×此率,记进运行日志→纳入月度成本硬闸。
# 默认 0.002 是 doubao-seed-mini 量级的保守估值,按真实 ARK 账单校准用 env 覆盖(宁高估不漏计,免成本盲区)。
VISION_COST_PER_1K_CNY = float(os.environ.get("GY_VISION_COST_PER_1K_CNY", "0.002"))

# 加工环开关(M3,ADR-0006):默认关(OFF)——真需求(某模式非拼图/AI图不可)到再开。
# 开=select_materials 后挂笔记前插 gated 加工步(决策/执行=技能,provenance/AI声明=代码焊死)。
PROCESSING_ENABLED = os.environ.get("GY_PROCESSING_ENABLED", "0") == "1"


TENANT_HOST = os.environ.get("GY_TENANT_HOST", "ccn925h7lg9d.feishu.cn")


def record_url(table_name: str, record_id: str) -> str:
    """记录深链:飞书卡片/消息里一点直达该行(P5)。"""
    return f"https://{TENANT_HOST}/base/{BASE_TOKEN}?table={tables()[table_name]}&record={record_id}"


def tables(env: str | None = None) -> dict[str, str]:
    """表名→table_id(按名注入,唯一取表入口)。"""
    e = env or ENV_NAME
    p = WORKSPACE / "schema" / e / "_tables.json"
    return json.loads(p.read_text(encoding="utf-8"))["tables"]
