# 观云 Workspace 搭建计划（v1.1，经审查修订）

> 目标：把内容运营从"人触发 AI 干活"升级为"AI 管理整个 loop，人只拍素材和确认发布"。
> 方法论定调（2026-07-08，两轮外部调研 + 现状勘察后）：**飞书当脸，CLI agent 当手，Bitable 当账本，git skills 当大脑，人当质检员和发布键。**

## 0. 概念与角色（六角色归位）

| 角色 | 承担者 | 铁律 |
|---|---|---|
| 账本（唯一真相源） | 飞书 Bitable 运营库 `ZhzJbfkOsafwevsWkW8cfoILnfb`（历史名“测试 Base”） | 一条内容一行，状态列是唯一真值；不当队列、不当媒体库 |
| 大脑（能力） | git 技能仓库（qiaohe-skill、video-engine） | 只装"怎么做"；实例配置一律外置注入 |
| 手（执行壳） | Claude Code 主力，Codex 备用 | 易耗品，双入口，换壳成本趋近零 |
| 推进器（loop） | 本仓库 `orchestrator/`：cron + webhook + heartbeat | **自身零 LLM**（纯确定性路由，LLM 只在被拉起的步骤内）；单实例串行 |
| 脸（员工界面） | 飞书原生：表单/看板/仪表盘/审批卡片 | 员工永不直接碰 agent |
| 人 | 拍素材、审内容、点发布（勾 AI 声明） | 两个人审硬门不可自动化 |

**Base 澄清（2026-07-09 用户重定义）**：`ZhzJbfkOsafwevsWkW8cfoILnfb` 虽历史名为“测试 Base”，但当前承担运营库；`.env` + `TEST_MODE=1` 即上线态。`N9IVbi…`（巧荷 Qiaohe-official-beta）保留为生产参考库，只读、焊死不碰；旧“切生产/TEST_MODE=0”路径不再作为上线方案。`ITz4bs…`（观云 Guanyun-official-beta）= 2026-06 旧版，已废弃，不纳入 schema 管理。

**本仓库（guanyun-workspace）= Workspace（空间）**；harness 不单独立项目，是本仓库的 `orchestrator/` 目录。

```
guanyun-workspace/
├── AGENTS.md            # 环境事实:Base ID/账号清单/红线/素材库约定(Codex/CC 通用)
├── CLAUDE.md            # → AGENTS.md 薄指针
├── .mcp.json            # MCP 连接器声明(密钥按名引 env)
├── .env.example
├── schema/              # Bitable 14 表字段契约 + 对齐探针 + 变更前快照
├── skills.lock.json     # 技能安装清单(见 P1 定义的 schema)
├── skills/              # 按 skills.lock 安装的技能(不入库,install 脚本产出)
├── orchestrator/        # 推进器:daily(cron)/webhook/heartbeat + runbook 状态路由(零 LLM)
├── lib/                 # seams:feishu_workbench/xhs_fetch/brand_kb/skill_gate(自 AI-marketing 迁入)
├── brands/              # 品牌静态资产(自 AI-marketing 迁入,迁时清旧引用)
└── docs/
```

**技能安装机制（审查 C1，关键）**：技能仓库经 `skills.lock.json` 安装（copy/symlink）到本仓库 `skills/` 目录，脚本的 `parents[3]/lib` 路径解析到本仓库 `lib/`——**带 lib 依赖的落库/取数脚本属于 Workspace 粘合层，不进 qiaohe-skill**；qiaohe-skill 保持纯能力（现有 14 技能零 lib 依赖，不破例）。

## 1. 已验证事实（2026-07-08 实测）

- 测试 Base 曾按生产 14 表复制；2026-07-10 起转为 SourceOwnership 新体系工作台，不再保真生产结构，允许为验证唯一源删除冗余表/字段。
- 工具链在位：lark-cli、hermes、claude headless（实测）、codex 0.136.0（已登录）、ffmpeg。
- qiaohe-skill 14 个 SKILL.md 全合规；其中 4 个硬编码表 ID 待去除。
- crontab 空；`content-skills`（竹序客户项目）不合并，借鉴其 stage→action 纯函数路由与 fail-safe noop 设计。

## 2. 阶段计划（合计 8–11 天，含 buffer；搭建期间日常运营并行、优先级让位）

### P0 决策冻结（半天）
- 主力壳 = Claude Code，Codex 备用；AI-marketing = 瘦身迁移不删除；自动化走 API key headless；OpenClaw 计划退役。
- **前置门（审查 M2）**：确认飞书租户版本与自动化月配额。若为基础版（200 次/月）：自动化只挂"待审→推卡片"一条，"已批准→推进"改由 heartbeat 轮询兜底。

### P1 基地骨架（1 天）
- AGENTS.md + CLAUDE.md 薄指针；`schema/` 从生产 Base dump 14 表契约（含 select 枚举）；定义并落 `skills.lock.json` schema（`{repo, ref/sha, skills[], install: copy|symlink}`）+ install 脚本；`.mcp.json`；`.env.example`（LARK/ARK/TIKHUB/APIFY/REDFOX 全量列出）。
- 迁入 lib seams 与 brands/；**清理 `brands/观云/lark_config.json` 旧 A1-B 表引用，app_token 的 env 变量名与 .env.example 对齐**（审查 M3）。
- **验收（脚本化）**：AGENTS.md 含全部 14 表 ID；skills.lock 可解析且 install 后技能脚本 import lib 冒烟通过；.mcp.json 语法合法。

### P2 测试 Base 改造（1 天）
- 状态机只加不删（补"已批准/待发布/已回流"）；AI 声明勾选字段；账号表补 4 个小红书号；按 P0 结论配自动化（1–2 条）。
- 改造前先 dump schema 快照存 `schema/snapshots/`（回滚依据）。产出**迁移清单**。
- **验收**：schema 对齐探针绿；手机点卡片翻状态实测。

### P3 技能整备（1 天 + 0.5 buffer）
- qiaohe-skill 4 技能去硬编码（表 ID 由 Workspace 注入）；加 `.claude-plugin/marketplace.json`（version 控版）。
- AI-marketing 纯技能迁 qiaohe-skill：**只迁 SKILL.md + 能力逻辑；persist/fetch 等 lib 依赖脚本留在 Workspace 粘合层**（C1 修订）。
- 核对 TIKHUB key 位置归位。
- **验收**：迁移后回归清单逐项跑通（每技能一次 dry-run + xhs-audience-miner 对测试 Base 真实落库一次，表 ID 来自注入）。

### P4a 推进器·路由核（1 天）
- cron 每日排产入口 + runbook（状态→技能路由表，纯函数，零 LLM）+ 单实例锁（flock）+ `--max-budget-usd` 预算帽 + 运行日志表写回。
- **TEST_MODE 硬开关**：代码级校验目标 Base，非测试 token 时拒绝写入（防测试数据进生产，审查 m5）。
- **验收**：测试 Base 模拟一天，cron 拉起推进一条笔记并留日志。

### P4b 推进器·事件与运维（1 天）
- webhook 接收器 + heartbeat 巡检（催拍/催审/失败重试）。
- **运维三件套（审查 M5）**：① orchestrator 异常经 hermes 即时告警（非日报）；② 每次运行记录 API 成本到运行日志表，heartbeat 核月度累计超阈值告警；③ heartbeat 定期 probe 各账号登录态，过期告警催扫码。
- VectCutAPI server（:9001）进程守护（launchd）。
- 每日 cron dump 关键表 JSON 备份（数据误删可恢复）。
- **验收**：kill 掉一次运行→收到即时告警；伪造登录态过期→收到催扫码提醒。

### P5 飞书的脸（1 天）
- 审批卡片（通过/打回）、催拍卡片、日报（hermes）、表单视图收灵感。
- **验收**：手机完成一次完整审批闭环（卡片→状态翻牌→推进器接住）。

### P6 端到端演练（1–2 天）
- 巧荷素材走全链：想法→分镜→（previz 可选）→剪辑→待审→已批准→"待发布包"（含 AI 声明提醒）。
- 文案/配图用 qiaohe-skill 现有技能（write-xiaohongshu / guanyun-OOTD-text / cover-generator）——旧 workspace"文案配图待重做"不阻塞演练（审查怀疑论者项）。
- **验收：至少 3 条笔记**（不同账号、不同内容类型）全生命周期走完，人只做"审+确认"；控量与差异化逻辑实测；**记录人审打回率**（>50% 则先修技能再上量）。

### P7 运营库挂 cron（半天 + 试运行一周）
- 不切 `N9IVbi`，不改 `TEST_MODE=0`。在运营库 `ZhzJbf` 上显式选择 `--llm stub|real` 安装 cron；先 1 号试运行一周再放量 4 号。
- OpenClaw 退役三步：停 gateway 进程/禁用其定时任务/移除 alias（保留配置存档一个月）。
- 周复盘飞轮排程（周日 cron：读运行日志+效果→提 SKILL.md 修改 PR→人审合入）。
- **验收**：第一周真实排产日历与日报正常；回滚预案在手（`install_cron.sh --remove`、schema 快照/每日备份可查）。

## 3. 红线与风险

- **绝不自动发布**：AI 只做到"待发布包"，人手机发布并勾 AI 声明（《AI 生成合成内容标识办法》2025-09 生效；小红书 2026-02 强化公告）。
- 单号 ≤3 篇/天、间隔 ≥2h + 随机延迟；多号内容强差异化（差异化机制：账号表调性字段 + 内容类型元模版注入，runbook 按账号路由）。
- Bitable：单 writer 串行、429 退避、业务键幂等；自动化只挂关键状态。
- 生产参考库 `N9IVbi` 只读；运营写入只进 `ZhzJbf` 且由 `TEST_MODE=1` 代码级隔离。
- 素材大文件走本地素材库 + 表存路径/链接；密钥只存 .env（不入库），泄漏即在飞书后台/各平台轮换。
- 单人 bus factor：本文档 + AGENTS.md + 运行日志表 = 可交接的全部上下文；每阶段 git 提交即回滚点。

## 4. 审查记录（v1→v1.1）

critic 审查结论"修订后开工"。已修订：C1 技能迁移 lib 断链（安装机制+粘合层拆分）、M1 双 Base 关系（澄清 N9IV 现行/ITz4 废弃）、M2 自动化配额前置门+降级、M3 lark_config 旧引用清理、M4 P4 拆两步+全程 buffer、M5 运维三件套、m1 验收脚本化、m3 演练 3 条、m5 TEST_MODE、缺失项（备份/回滚/密钥/进程守护/打回率闭环）。
