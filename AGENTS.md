# AGENTS.md · 环境事实

> 任何 agent(Claude Code / Codex / headless / 服务器 agent)进本仓库先读这份。
> **这份只讲"这里有什么"(环境事实)。** 心智和判据在 `CLAUDE.md`;全景架构在 `docs/架构.md`;病例在 `docs/踩坑账.md`。

本仓 = **harness 的领域那一半**(Tools / Observation / Permissions / 常驻 Knowledge)。
Agent 是模型;Base、网盘、小红书是**世界**,不是 harness。

---

## Base(世界 · 唯一真源)

| | token | 用途 |
|---|---|---|
| **测试 Base(= 运营库)** | `ZhzJbfkOsafwevsWkW8cfoILnfb` | **一切写操作只进这里。** `TEST_MODE=1` **本身就是上线态** |
| 生产 Base | `N9IVbi6pTatJG5sqyTTcc0vSn4g` | **焊死不碰**(读也不行)。红线守卫在任何 IO 之前拦住 |

- 表:笔记表(状态机脊柱)· 素材表 · 账号表 · 内容类型表 · 灵感库 · 关键词库 · 运行日志表 · 目标客户 · 素人推广案例 · Issue 表(共 13 表)。
- 字段契约 dump 在 `schema/test/`(`scripts/dump_schema.py` 产出);**取表一律按表名经 schema 解析,不硬编码 table_id**(测试库 table_id 与生产不同)。
- **Base 同时是人的驾驶舱** —— 人和 agent 看同一张表,不搞两套真源。
- 旧 Base `ITz4bsLSWaKuSqsuUaocmEC0nXe` 已废弃,不管理。

## 账号(3 个;**以账号表为准**,此处仅快照)

`ootd号`(视频唯美OOTD / 图文唯美OOTD)· `图文号1`(素人图文种草)· `图文号2`(素人图文种草)

**官号已下线**(2026-07-14 删除:账号声明 + base 记录 + 『品牌新作展示』模式 + 衣服知识库整条支线)。
**日常不注册衣服** —— 就是拍素材、打标、配文案发。

账号声明(画像 + strategy/playbooks)在 `brands/巧荷/accounts/{号}.md` —— **它是常驻 Knowledge**,agent 读它。

## 红线(Permissions · `orchestrator/guard.py`)

- **只写测试库 `ZhzJbf`**;生产库读也不碰。
- **绝不自动发布** —— 一律止于『草稿待发』。发布是人的动作。
- **绝不代勾 AI 声明**(《AI 生成合成内容标识办法》2025-09 生效)。AI 像素 → 素材『来源=AI生成』→ 门要求声明 → **人勾**。
- **单号 ≤3 篇/天**(平台风控)。**这个阈值焊成常量,不许 env 覆盖** —— 红线不许有旋钮。
- **防搬运**:爆款只当情报,产出不得含任何进过 prompt 的外来文本的 ≥10 连续实义字符片段(`guard.assert_no_source_leak`;抄了会自动回炉重写,再抄真拒)。
- **零素材门**:一张图/视频都没挂的稿,小红书发不出去 → 拦在待发布门外。
- 明文凭证只从 env 读,绝不入代码/库。

## 媒体(网盘 = 媒体唯一真身仓,ADR-0004)

`/巧荷素材/` 下:`待入库`(摄影师直接传,不用管文件名)· `01-原始素材` · `02-AI生成` · `03-成片`
**Bitable 不当媒体库** —— 表里只存网盘指针 + 小缩略图(附件字段,给人在 base 里瞄一眼)。

## 工具

| 工具 | 注意 |
|---|---|
| `lark-cli` | 飞书读写走它。**一律 `--as bot`**(app `cli_a965851065381ccb`)**+ `LARK_CLI_NO_PROXY=1`**(宿主机代理会弄挂它)。gotcha:`+record-get` 字段挂 `data.record` 下;删除类要 `--yes`;建带 property 字段走 bitable v1、公式走 base v3 |
| `hermes` | 飞书消息网关(告警/日报投递到人眼前) |
| `ARK`(火山方舟) | 出稿 + 看图 + 生图。key 从 env `ARK_API_KEY` 读。**`claude -p` 实测贵 577 倍**(每次吞 33K 系统提示),已弃 |
| `BaiduPCS-Go` | 网盘 CLI。装:`bash scripts/install_netpan.sh`。**真跑需人工一次** `BaiduPCS-Go login -bduss=<BDUSS>` + `.env` 设 `GY_NETPAN_MODE=real`。BDUSS 会过期 |
| `ffmpeg` / `sips` | 转码、抽关键帧、缩略图(`orchestrator/media.py`;Linux 换 heif-convert/ImageMagick) |
| `xhs-extract-master` | 小红书非登录抓取(技能)。**`note` 原子取正文必须带 `xsec_token`**,正文在 `note.desc` |

## 仓库结构

```
guanyun-workspace/            ← harness(领域那一半)
├── CLAUDE.md                 心智 · 唯一判据 · 红线 · 纪律  ← **每轮都进上下文**
├── AGENTS.md                 本文件:环境事实
├── CONTEXT.md                领域词汇(给 seam 起名)
├── docs/架构.md              全景图 · 技能是 Knowledge · **欠账(唯一一份)**
├── docs/踩坑账.md            病例(形态陷阱 / 人面缺陷 / 检查器自己得病)
├── docs/adr/                 已定的决策,别翻案
│
├── orchestrator/             **Tools + Observation + Permissions**
│   ├── guard.py              ← Permissions:五道红线门
│   ├── feishu_io netpan ark media   ← Tools:它的手
│   ├── cockpit shotlist report      ← Observation:它的眼睛
│   ├── bitable                      ← 常驻 Knowledge:schema 常量
│   └── accounts config draft dispatch publish collect compose processing …
│
├── scripts/                  CLI + 门(check_p*.sh / review_gate.sh / alignment_audit.py)
│                             ⚠️ tag_materials / daily_dispatch / draft_one 是**三条导轨**
│                                (替模型做了决策,该拆 —— 见 docs/架构.md 第四节)
├── skills/                   **Knowledge(按需加载)**;install_skills.sh 按 skills.lock.json 装出的符号链接
│                             唯一真源 = qiaohe-skill 仓。**不入库**
├── lib/                      ⚠️**技能层共享运行库,非死码**。qiaohe-skill 的 Python 技能 import 它
│                             (feishu_workbench / xhs_fetch / skill_gate / brand_kb)。
│                             orchestrator 不 import 它(两个独立子系统)。删了会断技能层
├── brands/巧荷/              账号声明(画像 + playbooks)· formulas(标题/正文/视觉公式)
├── schema/test/              Bitable 字段契约 dump(漂移用 git diff 兜底)
└── tests/                    回归锁。**只测法律/手/眼睛,不测判断**(见 CLAUDE.md「测试测什么」)
```

## 加东西的流程

- **加账号 / 加模式**:写 `brands/巧荷/accounts/{号}.md` 的 playbook 声明 + 建对应 gen_skill。**不改 schema、不改代码。**
- **加 base 字段**:`lark-cli base +field-create`(读回自证)→ `dump_schema.py --base test` → 登记 `bitable.py` 常量。
- **加技能**:进 `qiaohe-skill` 仓 → `skills.lock.json` 锁 sha → `install_skills.sh`。**技能唯一真源,workspace 不藏技能。**

## 门

`bash scripts/review_gate.sh --full` —— 单测 + ar_check(=100)+ dogfood 真库冒烟 + check_p1-6 + verify_usable + **机器审 `alignment_audit.py`** + **17 条链路真跑(真库/真ARK/真网盘)**。

**全绿才提交。红=不留,别拿"部分绿"充数。**
