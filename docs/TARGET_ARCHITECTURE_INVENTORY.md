# 目标架构清单：workspace / 测试 Base / skills / 素材盘

本清单回答“哪些留、哪些冗余、哪些删、哪些新加”。原则是 SourceOwnership：每类事实只有一个 owner；非 owner 只能保存外键、索引、员工界面字段或可重算快照。

## 0. 总体 owner 划分

| 层 | Owner 范围 | 不该拥有 |
|---|---|---|
| workspace/git | 架构文档、schema 契约、orchestrator、测试、账号画像、strategy、playbooks、品牌全局 know-how、skill lock | 运行状态、发布状态、员工填报、实际效果数 |
| 测试/运营 Base | 员工界面、Note 状态机、账号注册表、内容 tag、商品/素材/灵感/效果/运行日志 | 账号方法论、文案公式、skill 版本、开发 issue |
| qiaohe-skill/video-engine | 可复用“怎么做”的能力 | 某账号具体怎么发、某模式公式、Base table_id |
| 素材盘 | 大文件、子素材视图、usage ledger、AI 剪辑任务中间产物 | Bitable attachment 大媒体库、Note 状态 |
| GitHub Issues | 开发 issue、架构重构、bug/验收跟踪 | 员工业务需求原始表单 |
| automation/cron | 触发频率与运行入口 | 业务配置、账号策略 |

## 1. workspace：保留、改造、删除

### 必留

| 路径 | 归属 | 说明 |
|---|---|---|
| `AGENTS.md` / `CLAUDE.md` | 环境事实 | Base 红线、表清单、工具约束；`CLAUDE.md` 只做薄指针 |
| `CONTEXT.md` | 领域语言 | SourceOwnership / AccountKernel / Playbook 等 seam 词汇 |
| `docs/` | 决策与验收 | 保留计划、运行模式、SourceOwnership、架构演进、迁移清单 |
| `orchestrator/` | 泛化引擎 | 零账号特定代码；只读声明和 Base 状态 |
| `scripts/` | 运维/验收/迁移工具 | check_p、schema dump/diff、planner、cron、audit |
| `tests/` | 行为锁 | 字段契约、唯一源审计、状态机、P4/P6 回归 |
| `schema/prod` / `schema/test` / `schema/snapshots` | Base 契约 | 生产只读、测试可重构；schema 是迁移审计输入 |
| `brands/观云/accounts/*.md` | 账号 know-how owner | frontmatter = strategy/playbooks；正文 = account-teardown 画像 |
| `brands/观云/profile.json` | 品牌全局 know-how | 品牌定位、禁用词、基础调性；生成可读，不进 Base |
| `skills.lock.json` | skill 安装唯一清单 | 来源、版本、SHA；安装产物 `skills/` 不入库 |
| `local-skills/content-loop` | 临时本地能力 | 迁移到 qiaohe-skill 前保留；迁完从 lock 移除 local source |
| `lib/material_view.py` + 素材库 | 素材视图/usage owner | usage ledger 不进 Base |

### 需要改造

| 路径 | 当前问题 | 目标 |
|---|---|---|
| `brands/README.md` | 仍有旧 pipeline/A1-A3/B 文档 | 重写为当前 SourceOwnership + accounts/playbooks 接入指南 |
| `brands/观云/lark_config.json` | 含旧观云 Base `ITz...` table_id 和 public_tables；与 `schema/` 双源 | 替换为最小说明：Base 映射以 `.env` + `schema/<env>/_tables.json` 为准；不再存 table_id |
| `brands/观云/formulas/*.json` | 旧 pipeline 公式库，与 playbook 公式有重叠 | 拆成两类：品牌全局 style guide 可保留；账号/模式公式迁入 `accounts/*.md` 的 `playbooks[]` |
| `brands/观云/knowledge_base/explosive/*.json` | 原帖数据含外部文案，生成链有 source leak 风险 | 移到 `sources/` 或 Base「灵感库」作为情报；生成只读结构化洞察，不读原文片段 |
| `autoresearch/results.tsv` | 一次性研究运行产物 | 若要留证据，迁到 `docs/archive/`；否则删除 |
| `docs/PLAN.md` | 阶段计划仍是 P0-P7 主线 | 加一节“SourceOwnership 后续路线”：SkillCatalog / BaseWorkbench / FixtureLane |

### 应删除或不入库

| 路径/类型 | 处理 |
|---|---|
| `skills/` | 安装产物，继续不入库 |
| `backups/` | 运行备份，不入库 |
| `locks/` | 本地运行锁/提醒状态，不入库 |
| `__pycache__/` / `.pytest_cache/` / `.omx/` / `.claude/*.lock` | 本地运行态，不入库 |
| 旧 pipeline 文档/字段 | 若无当前消费方，迁移后删 |

## 2. 测试 Base：表级目标

### A. 核心运营账本：必须保留

| 表 | 目标语义 | 操作 |
|---|---|---|
| 笔记表 | Note 状态机唯一源：一条内容一行 | 保留，补强账号显式 link、fixture 分层 |
| 素材表 | Material 投影账本：素材编号、相对路径、拍摄/生成状态 | 保留；Bitable 不当媒体库 |
| 衣服总表 | SKU/Product catalog | 保留 |
| 账号表 | Account registry：账号名、平台 ID、主页、上线状态、投手 | 保留；不存方法论 |
| 内容类型表 | ContentType tag index：员工可选 tag、格式、所属账号 | 保留；删除模板/切面 |
| 运行日志表 | Orchestrator run log | 保留；补 run_id / duration / error_type |

### B. 知识与情报：保留，但不进入生成双源

| 表 | 目标语义 | 操作 |
|---|---|---|
| 面料·工艺库 | 结构化工艺/面料事实 | 保留，作为商品/素材/笔记引用事实 |
| 灵感库 | 外部灵感与选题入口 | 保留；加 source leak 风险字段 |
| 关键词库 | 关键词/tag taxonomy | 保留 |
| 目标客户 | 受众/目标账号情报 | 保留为 audience intelligence；不作为账号画像 owner |
| 素人推广案例 | KOC/推广案例情报 | 保留为增长情报；若 30 天无消费方，可归档 |

### C. 员工协作：保留但改名/改边界

| 表 | 当前问题 | 目标 |
|---|---|---|
| Issue 表 | 名字容易和 GitHub Issues 混淆；用户已声明不是开发 issue | 改语义为“员工需求/问题反馈表”；开发 issue 只进 GitHub |
| 修订日志 | 没有强 link 到 Note，容易变成散文本 | 保留为“内容修订日志”；新增 `关联笔记` link，删除/废弃 `关联技能` |

### D. 应删除/废弃

| 表 | 原因 | 迁移目标 |
|---|---|---|
| 技能表 | skill owner 是 git repo + `skills.lock.json`；Base 技能表会成为版本双源 | 测试 Base 已删除；生产如需迁移只走人工迁移清单 |

## 3. 测试 Base：字段级目标

### 3.1 笔记表

保留：

- `排期编号`
- `标题`
- `状态`
- `内容类型`
- `方法论`
- `计划发布日`
- `实际发布日`
- `AI声明`
- `文案草稿`
- `脚本·分镜`
- `发布链接`
- `关联衣服`
- `关联素材`
- `关联子素材`
- `标签·关键词`
- `点赞` / `收藏` / `评论` / `转发` / `新增关注`
- `热度分`
- `是否爆款`
- `灵感库-转化为笔记`
- `投手`

废弃/删除候选：

- `token花费(元)`：成本 owner 应是 `运行日志表.成本_元`；若需要 Note ROI，改名为派生/汇总字段。
- `人工时(小时)`、`结算日期`：若是财务/外包结算，另建财务 lane；否则删除。
- `颜色`：应来自 `衣服总表.颜色·规格` 或素材 metadata，Note 不重复存。
- `账号(自动)`：旧 lookup，测试 Base 已迁移到显式 `账号` link 后删除。

新增：

- `账号`：link 到账号表，作为 Note 所属账号的显式事实。
- `数据用途`：select = `真实运营` / `演练` / `压测`，替代 `_SIM/_UAT/_STRESS` 只靠编号前缀。
- `运行批次`：text，关联 orchestrator run_id。
- `发布包路径`：text，可指向盘上待发布包。

### 3.2 素材表

保留：

- `素材编号`
- `类型`
- `链接`
- `拍摄状态`
- `来源`
- `生成参数`
- `关联衣服`
- `关联面料·工艺`
- `适用账号`
- `备注`
- `拍摄人`
- `拍摄要求`
- `被引用次数`
- `笔记表-关联素材`

废弃/删除候选：

- `文件`：大文件禁止进 Base；如保留，只允许缩略图/预览图，字段说明改名为 `预览图`。
- `颜色`：优先归衣服或素材 metadata；若用于检索可保留为索引，不做事实源。

新增：

- `相对路径`：text，明确替代把 `链接` 混用为 URL/路径。
- `素材哈希`：text，支持搬家/去重。
- `数据用途`：真实运营/演练/压测。
- `验收状态`：待验收/可用/弃用，尤其给 AI 生成素材。

### 3.3 衣服总表

保留：

- `衣服编号`
- `款式名称`
- `形制·设计理念`
- `文物出处·文化依据`
- `卖点内核`
- `纹样`
- `面料`
- `工艺`
- `颜色·规格`
- `季`
- `年份`
- `拍摄负责人`
- `启用账号`
- `素材数`
- `素材表-关联衣服`
- `灵感库-关联衣服`
- `被引用次数`
- `备注`

废弃/删除候选：

- `排期表-关联衣服`：旧命名，目标应是 `笔记表-关联衣服`。

新增：

- `内容优先级`
- `生命周期状态`：待拍/可发/暂停/归档。
- `素材缺口摘要`：可由 planner 生成投影，不人工维护。

### 3.4 账号表

保留：

- `账号名`
- `小红书号`
- `主页链接`
- `上线状态`
- `投手`
- `内容类型表-所属账号`

废弃/删除候选：

- `受众`：受众理解属于 workspace 画像正文；Base 若保留只能叫 `员工摘要`，且不得被引擎消费。

新增：

- `workspace_ref`：例如 `brands/观云/accounts/图文号1.md`，便于员工/agent 定位 owner。
- `画像状态`：占位/已拆解/需重跑。
- `画像更新时间`：account-teardown 最近更新时间。
- `自动排产`：bool 或 select；也可由 workspace `launched/cadence` 派生，若 Base 保留则只作员工开关，需明确优先级。

### 3.5 内容类型表

保留：

- `内容类型名`
- `格式`
- `所属账号`

删除：

- `取数字段·切面`
- `文案元模版`

新增：

- `slug`：稳定 key，避免中文改名导致历史断裂。
- `启用状态`
- `展示顺序`
- `workspace_playbook_ref`：只读指针，如 `图文号1.md#playbooks[文物对照]`。

### 3.6 运行日志表

保留：

- `时间`
- `执行体`
- `动作`
- `摘要`
- `结果`
- `详情`
- `涉及表`
- `涉及记录`
- `技能`
- `成本_元`

新增：

- `run_id`
- `automation_id`
- `duration_ms`
- `error_type`
- `数据用途`

### 3.7 面料·工艺库

保留：

- `名称`
- `类型`
- `是否非遗`
- `科普说明`
- `衣服总表-面料`
- `衣服总表-工艺`
- `素材表-关联面料·工艺`
- `被引用次数`
- `备注`

废弃/删除候选：

- `排期表-关联面料·工艺`：旧命名，迁到 `笔记表-关联面料·工艺` 或删除。

新增：

- `事实来源`
- `可信级别`
- `禁用说法`

### 3.8 灵感库

保留：

- `标题`
- `链接`
- `文案`
- `镜头`
- `优点`
- `缺点`
- `状态`
- `关联关键词`
- `关联衣服`
- `转化为笔记`

新增：

- `来源平台`
- `来源账号`
- `采集时间`
- `可借鉴点`
- `禁用片段/搬运风险`
- `去重键`

### 3.9 关键词库

保留：

- `关键词`
- `分组`
- `灵感库-关联关键词`
- `笔记表-标签·关键词`
- `被引用数`

新增：

- `启用状态`
- `禁用原因`
- `平台`

### 3.10 目标客户

保留：

- `账号名`
- `小红书号`
- `主页链接`
- `关键词`
- `标签简介`

新增：

- `人群假设`
- `证据链接`
- `更新时间`
- `适用账号`

### 3.11 素人推广案例

保留：

- `博主名字`
- `小红书号`
- `博主主页`
- `内容类型`
- `推广方式`
- `笔记链接`
- `添加时间`
- `补充说明`

新增：

- `合作状态`
- `转化指标`
- `适用账号`
- `素材授权状态`

### 3.12 Issue 表

保留但改语义：

- 表名建议改为 `员工需求表` 或 `运营问题反馈表`。
- 保留 `需求描述`、`Issue 标题`、`状态`、`优先级`、`提出人`、`提出时间`、`来源群聊`、`解决方案`、`通知状态`。

删除/废弃：

- `关联技能`：skill 版本归 git，不在 Base 维护。
- `完成时间` 可保留，但只作为员工需求完成时间，不对应 GitHub close。

新增：

- `github_issue_url`：只有需要开发跟踪时，由 agent 创建 GitHub Issue 后回填链接；不是反向替代 GitHub。
- `归属域`：内容/素材/账号/员工界面/开发。

### 3.13 修订日志

保留：

- `时间`
- `来源`
- `初始需求`
- `修改意见`
- `原始产出`
- `最终版本`

删除/废弃：

- `关联技能`

新增：

- `关联笔记`
- `修订类型`
- `审核人`

### 3.14 技能表

目标：删除或降级为只读投影。

如果员工界面确实需要看技能，新增只读投影字段：

- `技能名称`
- `来源仓库`
- `锁定版本/SHA`
- `安装状态`
- `说明`

禁止字段：

- 人工维护的 `状态`
- 人工维护的 `落表(规范)`
- 人工维护的 `输出落表`

这些都应来自 skill repo、`skills.lock.json` 和自动审计。

## 4. 新增体系模块

### 4.1 SkillCatalog

Owner：workspace。

职责：

- 读取 `skills.lock.json`
- 检查 qiaohe-skill / video-engine / local-skills 来源、SHA、挂载路径
- 输出“安装产物不是源”的审计报告
- 可选投影到 Base，但 Base 不可反向编辑

### 4.2 BaseWorkbench

Owner：workspace。

职责：

- 对 schema + live records 做质量审计
- 输出字段删除/新增/迁移计划
- 执行前备份，执行后 dump schema
- 区分生产只读与测试可写

### 4.3 PlaybookLibrary

Owner：workspace `brands/<brand>/accounts/*.md`。

职责：

- 每账号每模式的 playbook 声明
- playbook 公式、素材需求、生成 skill、素材视图 key
- 禁止 Base 再保存 playbook know-how

### 4.4 OperationalFixtureLane

Owner：workspace + Base 字段。

职责：

- `数据用途` 标记真实运营/演练/压测
- run_id 贯穿 Note/Material/RunLog
- 清理脚本按 run_id 和 数据用途删，不只靠 `_SIM` 前缀

## 5. 迁移顺序

1. 文档冻结本清单。
2. 新增 BaseWorkbench dry-run：只读列出“当前字段 → 目标动作”。
3. 新增 `账号` link、`数据用途`、`run_id` 等非破坏字段。
4. 迁移 Note 的账号归属，从 `账号(自动)`/内容类型 lookup 转为显式 `账号` link（测试 Base 已完成回填，旧 lookup 已进入删除目标）。
5. 删除或废弃 `内容类型表.取数字段·切面`、`内容类型表.文案元模版`。
6. 重写 `brands/README.md` 和 `brands/观云/lark_config.json`。
7. 把旧 formulas/knowledge_base 拆分为品牌全局 style guide 与 source intelligence。
8. 删除/降级 Base「技能表」（测试 Base 已删除）。
9. 将 Base「Issue 表」改名/改语义为员工需求，不再承担开发 issue。
10. 每步后跑：
    - `python3.10 -m pytest -q`
    - `python3.10 scripts/ar_check.py`
    - `python3.10 scripts/account_kernel_audit.py`
    - `ALERT_DRY_RUN=1 scripts/check_p1.sh..check_p6.sh`

## 6. 当前最该做的下一刀

优先做 BaseWorkbench dry-run，不直接删字段。原因：

- 现在 schema 仍记录旧字段，live records 已先把内容类型 know-how 清空。
- 下一步需要一个可重复迁移器，明确字段删除、字段新增、数据迁移、schema dump、验收证据。
- 这样可以把“测试 Base 无沉没成本”变成工程动作，而不是手工点 UI。
