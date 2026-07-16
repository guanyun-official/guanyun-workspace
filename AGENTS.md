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

- 表:笔记表(状态机脊柱)· 素材表 · 账号表 · 内容类型表 · 灵感库 · 关键词库 · 运行日志表 · 目标客户 · 素人推广案例 · Issue 表。
  (**活库以 `python3 scripts/dump_schema.py` 的产出为准** —— 别在文档里手抄表数,一改必漏。)
- **素材表『类型』= 纯内容,『形态』= 图/视频**(2026-07-14 分开的两维)。
  类型 11 值:上身 · 商品 · 形象 · 搭配 · 细节 · 面料·纹理 · 工艺 · 制作过程 · 空镜·场景 · 文物原件 · 文物对照。
  **名字里不带"图"/"视频"** —— 那是形态,由文件本身推。(混在一起时代码里长出过钳制,见 `docs/踩坑账.md`。)
- ⚠️ **改 select 选项会清空所有单元格**(飞书按 option_id 认)。要保留就把旧选项**连 id 一起回传**。
  真栽过:280 行的『类型』被一次 PUT 抹空,靠 `backups/` 救回来的。
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

## 媒体(网盘 = 媒体唯一真身仓,「媒体唯一真身仓=网盘」)

`/巧荷素材/` 下:`待入库`(摄影师直接传,不用管文件名)· `01-原始素材` · `02-AI生成` · `03-成片`
**Bitable 不当媒体库** —— 表里只存网盘指针 + 小缩略图(附件字段,给人在 base 里瞄一眼)。

## 工具

| 工具 | 注意 |
|---|---|
| `lark-cli` | 飞书读写走它。**一律 `--as bot`**(凭证从 hermes 来,**不要 `config init`**,见下)**+ `LARK_CLI_NO_PROXY=1`**(宿主机代理会弄挂它)。新机器/新 profile 必须先跑 `bash scripts/install_lark.sh`(幂等,做 `lark-cli config bind --source hermes` + 自证);不绑会静默 `not configured`,`board` 整个哑火。gotcha:`+record-get` 字段挂 `data.record` 下;删除类要 `--yes`;建带 property 字段走 bitable v1、公式走 base v3;报错在 **stderr**,成功在 **stdout**(`feishu_io._call` 两个都看) |
| `hermes` | 飞书消息网关(告警/日报投递到人眼前)。**发消息到群/私信 = 运行时的手**:`hermes send -t feishu:<chat_id> "文本"`(工作群 `oc_f10ff6debcf31a30d96d61231aabaf3b` · 用户私信 `oc_152a1160d240789391546e0a831e9798`)。cron job 配了 `"deliver":"feishu:<chat_id>"` 会**自动把 agent 输出路由到群**,不用手动发;只有临时 `hermes -z` 派活没配 deliver 时,才需自己 `hermes send`。⚠️ **别在 orchestrator 里造发消息动词** —— 那是重新实现运行时已有的 `hermes send`(两份真源,同已删的 `schedule.py` 病)。 |
| `ARK`(火山方舟) | **只剩生图**(AI 封面;agent 画不了图,这是它真缺的一只手)。key 从 env `ARK_API_KEY` 读。<br>**出稿/看图的 ARK 调用已删** —— agent 自己就是模型:它自己看图、自己写稿,不需要 harness 替它去问另一个模型 |
| `BaiduPCS-Go` | 网盘 CLI。装:`bash scripts/install_netpan.sh`。**真跑需人工一次** `BaiduPCS-Go login -bduss=<BDUSS>`。**没有 stub 模式** —— 没登录就炸,绝不静默返回空。BDUSS 会过期 |
| `ffmpeg` / `sips` | 转码、抽关键帧、缩略图(`orchestrator/media.py`;Linux 换 heif-convert/ImageMagick)。**Linux 首次上手机器跑 `bash scripts/install_sysdeps.sh`**(幂等装 ffmpeg / libheif-examples / imagemagick);mac `brew install ffmpeg`,sips 自带。<br>**装完再跑 `bash scripts/install_lark.sh`**(把 hermes 凭证绑进 lark-cli,幂等;跳过会让 `board` 整只眼睁不开)。 |
| `xhs-extract-master` | 小红书非登录抓取(技能)。**`note` 原子取正文必须带 `xsec_token`**,正文在 `note.desc` |

## 仓库结构

```
guanyun-workspace/            ← harness(领域那一半)
├── CLAUDE.md                 心智 · 唯一判据 · 红线 · 纪律  ← **每轮都进上下文**
├── AGENTS.md                 本文件:环境事实
├── CONTEXT.md                领域词汇(给 seam 起名)
├── docs/架构.md              全景图 · 技能是 Knowledge · **欠账(唯一一份)**
├── docs/踩坑账.md            病例(形态陷阱 / 人面缺陷 / 检查器自己得病)
├── docs/踩坑账.md                 已定的决策,别翻案
│
├── orchestrator/             **Action Interface + Tools + Observation + Permissions**
│   ├── cli.py __main__.py    ← **Action Interface**:`python3 -m orchestrator <动词>`
│   │                            一个动词=一件事,零判断。**故意没有** approve/publish/tag/draft
│   ├── guard.py              ← Permissions:五道红线门 + provenance
│   ├── board.py              ← **它的眼睛**:世界现在什么样(只有事实,没有建议)
│   ├── feishu_io netpan media ark   ← Tools:它的手
│   ├── materials notes ingest compose   ← Tools:看/写/登记/加工
│   │                             ⚠️ **没有 schedule** —— 心跳是运行时的活(架构.md 4.3b)
│   ├── cockpit shotlist report      ← Observation:给人看的(运营/摄影师/老板)
│   ├── bitable                      ← 常驻 Knowledge:schema 常量
│   └── accounts config publish metrics trends alerts …
│
├── scripts/                  **只剩开发期的门**(review_gate.sh / backup_tables /
│                             dump_schema / check_schema_drift / install_skills.sh)。
│                             **运营侧一个脚本都没有** —— 导轨已拆完(2026-07-14)。
│                             ⚠️ **审查不在这里** —— 审查是**每轮派子 agent**(见 docs/架构.md 六)
├── skills/                   **Knowledge(按需加载)**;install_skills.sh 按 skills.lock.json 装出的符号链接
│                             **两个真源**(lock 的 `sources` 是数组):
│                               · `qiaohe-skill`  出稿 / 打标 / 选材 / 采集 / 需求
│                               · `video-engine`  分镜 / AI参考片 / **可审计精剪**(cutlist + 剪映草稿)
│                             **技能跟着它的引擎走,绝不拷贝**(拷过一次,把引擎弄丢了)。**不入库**
├── brands/巧荷/              账号声明(画像 + playbooks)· formulas(标题/正文/视觉公式)
├── schema/test/              Bitable 字段契约 dump(漂移用 git diff 兜底)
└── tests/                    回归锁。**只测法律/手/眼睛,不测判断**(见 CLAUDE.md「测试测什么」)
```

## 加东西的流程

- **加账号 / 加模式**:写 `brands/巧荷/accounts/{号}.md` 的 playbook 声明 + 建对应 gen_skill。**不改 schema、不改代码。**
- **加 base 字段**:`lark-cli base +field-create`(读回自证)→ `dump_schema.py --base test` → 登记 `bitable.py` 常量。
- **加技能**:进它**自己的真源仓**(`qiaohe-skill` 或 `video-engine`)→ `skills.lock.json` 锁 sha → `install_skills.sh`。
  **workspace 不藏技能,也绝不把别的仓的技能拷贝进来**(拷过一次,拷的时候把引擎弄丢了,
  于是技能指着不存在的脚本 —— 我据此把它删了,还挂账说"这个能力没接线"。见 `docs/架构.md` 4.3c)。

## 门

`bash scripts/review_gate.sh --full` ——
① **红线测试**(`tests/`,只测红线,不测判断)
② schema 契约(代码消费的字段 ⊆ 活库)
③ **技能真源同步**(`skills.lock.json` 的 sha == **GitHub 上的 main**,直接问 GitHub)
④ **真跑冒烟**(零 mock,真测试库:`python3 -m orchestrator board` 必须真跑得通)
⑤ **备份**(schema 操作抹掉过 280 行,是 `backups/` 救回来的)
末尾跑 `ask.sh` 架构自问

★门里**只有对账和真跑**,一个"预测系统会怎么错"的检查器都没有。★

老的门(`ar_check` / `verify_usable` / `dogfood_smoke` / `check_p1-6` / 机器审)**全删了**:
它们断言的正是拆掉的导轨,而且**测的是措辞不是正确性**;机器审自己三个核心检查都是空壳
(加一句**注释**就能骗过去),它还 import 过已删的模块 —— 那一刻它根本不设防。

**审查 = 每轮派子 agent**(见 `docs/架构.md` 第六节)。
机械匹配永远查不出「这段 if 是不是在替模型做决策」「这句话是不是在骗人」—— **只有模型答得了。**

**全绿才提交。红=不留,别拿"部分绿"充数。**
