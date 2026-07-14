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

# ★★ 红线阈值:**焊死,不读 env** ★★(2026-07-14 开关过堂实测抓到)
#
#   老实现是 `int(os.environ.get("GY_ACCOUNT_DAILY_PUB", "3"))`。真跑一测:
#       GY_ACCOUNT_DAILY_PUB=999 → 今天已发 50 篇,**控量门照样放行**。
#   **一个环境变量就能把红线关掉。** 那它就不是红线,是个建议。
#
#   而且这条特别毒:env 关红线**不留任何痕迹** —— git 里看不到、日志里看不到、人也看不到。
#   哪天 cron 的环境里多了一行,或者谁 export 了一下,风控上限就没了,而没有任何人会知道。
#   "阈值可 env 覆盖"写的时候觉得灵活,落实下来是**给红线装了个静音开关**。
#
#   平台规则真变了怎么办?**改这一行,提交,让人看见。** 改红线必须留痕 —— 这是它和普通配置的分界。
PER_ACCOUNT_DAILY_PUBLISH = 3          # 单号每日发布上限(平台风控红线;要改就改这里并 commit,不许 env 覆盖)

# ══════════════════════════════════════════════════════════════════════════════
# 开关过堂(2026-07-14):每一个 GY_* 都得回答一句 ——
#   **「这是不是我不敢把判断交给 agent?」** 是 → 删掉,把判断交出去;不是 → 在这写明它凭什么留。
#
# 背景:.env 里**一个 GY_* 都没设过**,17 个旋钮全跑在默认值上。旋钮不是免费的:
# 每一个都是一次"我(开发)替 agent 想好了",而 agent 本该现场看一眼就决定。
#
# 判决:
#   【删/焊死】GY_ACCOUNT_DAILY_PUB —— **它是红线阈值**。实测 `=999` 就能让控量门放行 50 篇。
#              红线有旋钮 = 不是红线。已焊死成常量(见上),改它必须改代码 + commit + 留痕。
#
#   【留 · 环境事实,不是判断】—— 换台机器/换个区域/供应商改价,这些**不由 agent 决定**:
#     · GY_TENANT_HOST / GY_ARK_IMAGE_ENDPOINT   部署环境(区域、域名)
#     · GY_IMAGE_MODEL                            供应商模型名(会改名、会下线)
#
#   【留 · 人的决策,不是 agent 的】
#     · GY_BUDGET_MONTHLY_CNY  花多少钱是**老板定**,不是 agent 定
#       (⚠️ 默认 300 元/月是我拍的,不是你定的 —— 该由你确认)
#
# ── 2026-07-14 拆导轨这一轮**删掉的**(它们服务的那段代码没了,留着就是死配置)──────
#   【删】GY_DRAFT_BACKEND / GY_DRAFT_MODEL / GY_DRAFT_COST_PER_1K_CNY / GY_PER_RUN_BUDGET_USD
#         —— 它们是"harness 调另一个 LLM 替 agent 写稿"的参数。**agent 自己就是模型**,
#            它读画像、读技能、读素材备注,**自己把稿写出来**。那条路整条删了(`llm.py` 已删)。
#   【删】GY_VISION_BACKEND / GY_VISION_MODEL / GY_VISION_COST_PER_1K_CNY / GY_TAG_CONCURRENCY
#         —— 它们是"harness 拿着一份分类法去问另一个模型这张图是什么"的参数。
#            **agent 自己有眼睛**:harness 把网盘的东西转成它能看的(`materials.viewable`),
#            它自己看、自己判、自己写备注。(`vision.py` 已删。)
#   【删】GY_PROCESSING_ENABLED —— 它关的是"加工环放不放出去"。而加工环里那个 `ai_decide`
#         (harness 拿着判断准则 prompt 去问另一个模型"该不该加封面")本身就是导轨,已删。
#         现在 **agent 自己看素材、自己判断要不要加工**,判好了调 `compose.execute` 那只手。
#         要不要加工没有开关 —— 它是判断;而 AI 像素的 provenance 和 AI 声明**是法律**(guard 焊死)。
#

#   【留 · 规模护栏,不是判断】(2026-07-14 重新判过:我之前把它记成"欠账",判错了)
#     · GY_COLLECT_REFRESH_DAYS=30    它拦的是"别把累积态整张表全拉回来"(API/成本约束)。
#       **这是 Tools 的护栏,不是内容判断。** 留。
#   【已删】GY_METRICS_MODE —— 它存在的唯一理由是"让离线单测不触网"。**单测已全删**(只剩红线),
#           这个理由没了。有真链接就真采(零凭证、几乎免费)。
# ══════════════════════════════════════════════════════════════════════════════

# 阈值(可 env 覆盖)
COLLECT_REFRESH_DAYS = int(os.environ.get("GY_COLLECT_REFRESH_DAYS", "30"))  # 回流刷新窗(规模护栏:别把累积态整张表全拉回来)
# 删了两个**死配置**(2026-07-14 全体系对齐审查):它们承诺了数据根本支撑不了的功能,和 base 里那几个
# 空壳视图(「按颜色分组」——素材表没有颜色字段)是同一个病:**人想起来方便,就先把名字写上,功能从没做**。
#   · GY_REVIEW_OVERDUE_H(待审超时催审):要算"躺了多久"需要**进入待审的时间戳**,
#     而笔记表没有这个字段,飞书 records API 也不返回 created_time → **永远算不出来**。
#     要做:先给笔记表加「创建时间」自动字段(飞书原生 type,零维护),再据此催审。
#   · GY_METRICS_CLOSE_DAYS(已发 N 天后回流收口):从没实现,且与 COLLECT_REFRESH_DAYS 语义重复
#     (后者已在 collect.py 真用:超窗的已回流帖热度已定,不再重刷)。
BUDGET_MONTHLY_CNY = float(os.environ.get("GY_BUDGET_MONTHLY_CNY", "300"))  # 月度成本告警阈值(老板定)

# 加工环生图(AI 封面)。**agent 画不了图,这是它真正缺的一只手。**
# Seedream 4.0 在方舟**存在但需账号开通**(控制台一次点击,人做)。
# 未开通时 ark.image 抛 ModelNotOpen —— **绝不静默退回原图**:判了"该加封面"却悄悄没加,
# 人会以为加上了,那正是最贵的那种 bug。
ARK_IMAGE_ENDPOINT = os.environ.get("GY_ARK_IMAGE_ENDPOINT",
                                    "https://ark.cn-beijing.volces.com/api/v3/images/generations")
IMAGE_MODEL = os.environ.get("GY_IMAGE_MODEL", "doubao-seedream-4-0-250828")

TENANT_HOST = os.environ.get("GY_TENANT_HOST", "ccn925h7lg9d.feishu.cn")


def record_url(table_name: str, record_id: str) -> str:
    """记录深链:飞书卡片/消息里一点直达该行(P5)。"""
    return f"https://{TENANT_HOST}/base/{BASE_TOKEN}?table={tables()[table_name]}&record={record_id}"


def tables(env: str | None = None) -> dict[str, str]:
    """表名→table_id(按名注入,唯一取表入口)。"""
    e = env or ENV_NAME
    p = WORKSPACE / "schema" / e / "_tables.json"
    return json.loads(p.read_text(encoding="utf-8"))["tables"]
