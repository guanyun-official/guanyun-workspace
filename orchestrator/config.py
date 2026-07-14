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
#     · GY_TENANT_HOST / GY_ARK_ENDPOINT / GY_ARK_IMAGE_ENDPOINT   部署环境(区域、域名)
#     · GY_DRAFT_MODEL / GY_VISION_MODEL / GY_IMAGE_MODEL          供应商模型名(会改名、会下线)
#     · GY_DRAFT_COST_PER_1K_CNY / GY_VISION_COST_PER_1K_CNY       供应商定价(算成本用的**事实**)
#     · GY_TAG_CONCURRENCY                                          本机负载(笔记本 4 / 服务器可调高)
#
#   【留 · 人的决策,不是 agent 的】
#     · GY_BUDGET_MONTHLY_CNY / GY_PER_RUN_BUDGET_USD  花多少钱是**老板定**,不是 agent 定
#       (⚠️ 默认 300 元/月是我拍的,不是你定的 —— 该由你确认)
#
#   【留 · 逃生舱,不是常规路径】
#     · GY_DRAFT_BACKEND=claude_cli   实测贵 577 倍,只留作质量对比。**别拿它当常规底座**
#     · GY_VISION_BACKEND=claude      ARK key 缺失时的零凭证兜底
#
#   【留 · 放量闸,不是判断】
#     · GY_PROCESSING_ENABLED         加工环默认关。**关的不是"要不要加工"这个判断**(那归 ai_decide),
#       关的是"这条能力放不放出去" —— 它会生成 AI 像素、连带触发 AI 声明手续。验证通过再开。
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
# 加工环生图(AI 封面 / AI 画面)。Seedream 4.0 在方舟**存在但需账号开通**(控制台一次点击,人做)。
# 未开通时 ark.image 抛 ModelNotOpen —— **绝不静默退回原图**:判了"该加封面"却悄悄没加,
# 人会以为加上了,那正是最贵的那种 bug。
ARK_IMAGE_ENDPOINT = os.environ.get("GY_ARK_IMAGE_ENDPOINT",
                                    "https://ark.cn-beijing.volces.com/api/v3/images/generations")
IMAGE_MODEL = os.environ.get("GY_IMAGE_MODEL", "doubao-seedream-4-0-250828")
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
