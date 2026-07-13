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
# 删了两个**死配置**(2026-07-14 全体系对齐审查):它们承诺了数据根本支撑不了的功能,和 base 里那几个
# 空壳视图(「按颜色分组」——素材表没有颜色字段)是同一个病:**人想起来方便,就先把名字写上,功能从没做**。
#   · GY_REVIEW_OVERDUE_H(待审超时催审):要算"躺了多久"需要**进入待审的时间戳**,
#     而笔记表没有这个字段,飞书 records API 也不返回 created_time → **永远算不出来**。
#     要做:先给笔记表加「创建时间」自动字段(飞书原生 type,零维护),再据此催审。
#   · GY_METRICS_CLOSE_DAYS(已发 N 天后回流收口):从没实现,且与 COLLECT_REFRESH_DAYS 语义重复
#     (后者已在 collect.py 真用:超窗的已回流帖热度已定,不再重刷)。
BUDGET_MONTHLY_CNY = float(os.environ.get("GY_BUDGET_MONTHLY_CNY", "300"))  # 月度 LLM 成本告警阈值
PER_RUN_BUDGET_USD = float(os.environ.get("GY_PER_RUN_BUDGET_USD", "1.2"))  # 单次 claude -p 预算帽(P6实测:长文0.5不够)
# 出稿底座(dogfood 2026-07-14 真跑改的):原走 `claude -p`,**每次吞 ~33K token 的 Claude Code 系统提示**
# (实测:只让它回"测试成本"四个字,cache_creation=32766 tokens,花 1.48 元)→ 一条 200 字文案 2~3 元,
# 95% 的钱付给 CLI 的系统提示,与文案长短/模型档次几乎无关。切 ARK 直连(豆包,vision 同一把 key):
# prompt 就是 prompt,同样的稿便宜两个数量级。要回退对比质量:GY_DRAFT_BACKEND=claude_cli。
DRAFT_BACKEND = os.environ.get("GY_DRAFT_BACKEND", "ark")            # ark(直连,默认) | claude_cli(旧,贵)
# 真跑对比(2026-07-14,同一条 ootd 稿):mini=0.0052元但只3句丢场景层;seed-1-6=0.0055元四层齐;
# **lite=0.0057元,四层最齐、标题吃进粉+木、细闪场景都中**(用户拍板)。三者成本一个量级,取质量最好的。
DRAFT_MODEL = os.environ.get("GY_DRAFT_MODEL", "doubao-seed-2-0-lite-260428")
DRAFT_COST_PER_1K_CNY = float(os.environ.get("GY_DRAFT_COST_PER_1K_CNY", "0.002"))  # 出稿成本估:元/1K token
METRICS_MODE = os.environ.get("GY_METRICS_MODE", "stub")  # 效果采集:stub 零成本 / real 走 metrics 直连 xhs-extract-master 非登录取数(G7)

# 看图打标(多模态)后端(vision.py seam):doubao(ARK,便宜,默认)/ claude(claude -p 兜底,零 key)。
# ARK_API_KEY 从 env 读——明文凭证绝不入代码/库;doubao 后端缺 key 时 vision 报错(不静默)。
# 打标并发度(护本机负载的旋钮):看图打标并发跑几批。转码=本机CPU大头,本地默认低(护笔记本),
# 上线服务器可 GY_TAG_CONCURRENCY 调高。"串行不并发"红线=别把高负载压用户本机,不是禁打标并发。
TAG_CONCURRENCY = int(os.environ.get("GY_TAG_CONCURRENCY", "4"))

# 视频入库开关(护本机):baidu 网盘无 range/直链外部被拒(实测403/503),视频只能下整包;
# 视频底片=GB级raw剪辑原料(实测 median 511MB/条),下载=带宽+磁盘重活。**默认关(0)**——本机不碰视频入库
# (raw 走 video-editing 出成片,成片才入库打标);服务器/确需时 GY_INGEST_VIDEO=1(下载一次→多帧→缓存帧→删)。
# GY_INGEST_VIDEO 已删(2026-07-14 全体系对齐审查:它在视频改成"一律收+串行"之后就没人读了=死配置)。
# 曾经它 =0 时一刀切跳过所有视频,造成死循环:补拍单催「上身视频×3」→ 摄影师拍了传网盘 →
# 系统跳过不收 → 补拍单继续催(**人拍了,系统不收,然后继续催他拍**)。
# 护本机的正确手段是**视频串行处理**(tag_materials:每批 1 个、并发度 1 —— 拉一个→抽帧→打标→删缓存),
# **不是"拒收"**。视频现在一律收、中点抽关键帧打标。开关没了,因为不需要开关。
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
