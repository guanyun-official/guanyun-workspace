# CONTEXT · 领域词汇（观云 Workspace）

> 给好 seam 起名的地方。架构评审与新代码用这些词，别漂成 component/service/handler。

## 领域概念

- **Note（笔记）** — 一条内容一行，状态机脊柱（想法储备→待拍素材→待出文案→草稿待发→已批准→待发布→已发→已回流；暂缓归档旁路）。飞书「笔记表」一行 = 一个 Note。
- **Account（账号）** — 一个小红书号。**两张脸**（皆 data）：画像 `accounts/{号}.md`（发什么/怎么写，喂生成）+ strategy frontmatter（怎么运营，喂 planner）。strategy 里有 **playbooks[]**。
- **SourceOwnership（唯一源边界）** — Base / workspace / skill / 素材盘的 owner 规则。Base owner=运营事实、状态、员工界面索引；workspace owner=画像、strategy、playbooks、内容切面/公式；skill owner=可复用“怎么做”；素材盘 owner=媒体文件、子素材视图与 usage。非 owner 只能保存外键、索引、派生快照，不能成为第二真相源。详见 `docs/SOURCE_OWNERSHIP.md`。
- **AccountKernel（账号内核）** — Base「账号表/内容类型表」与 workspace `brands/<品牌>/accounts/{账号}.md` 的 SourceOwnership 审计 seam。它不替代 Account，而是把员工界面里的账号事实、workspace 画像/strategy/playbooks、planner/llm 消费关系收口到一个可审计 module；核心不是同步两份数据，而是阻止 Base 和 workspace 对同一 know-how 双写。
- **Playbook（方法论）** — 账号的一套发布方法论（`strategy.playbooks[]`，2026-07-09 起）。= 配方（内容切面/节奏权重/material_needs/标题·正文公式）+ **gen_skill**（产这套笔记的技能）+ **view**（指向自己的素材视图键）。一号可多套；显式声明优先，否则从 content_mix 合成。加一套=写声明零代码。`orchestrator/accounts.playbooks_of/resolve_playbook`。
- **Material（素材）** — 一个图/视频**整文件**，软链上墙（原件不动）+ 登记「素材表」。SKU 可选（挂得上就挂）。`素材表.适用账号` = **原料级候选账号**(ingest 时的粗提示)，与下面的 View（方法论级精选）是**两个层级不是冗余**。
- **View（方法论视图）/ Clip（子素材）** — 盘上机器索引（`lib/material_view`，非 Bitable，2026-07-09 起）。每套 playbook 一套软链 bin(`_views/{账号}/{playbook}.jsonl`)；**Clip = 文件的一个切片/切面**，`clip_id=哈希(素材编号,span)` 稳定(搬家不断链)。同素材可被多方法论以不同 span 复用。
- **UsageLedger（使用账本）** — 盘上 `_usage.jsonl`，usage **唯一真值**。发布回填「关联子素材」的 clip_ids → 记 note↔clip。支撑回溯(trace_note)、视图余量、linked%/used% 使用率。
- **MediaTask（媒体加工任务）** — AI剪候选的盘上可恢复状态账本（`素材库/_processing/*.json`），状态为 `待生成剪单 → 剪单待人确认 → 待物化 → 成片待验收 → 可建 Note`。daily 只幂等创建/读取任务；只有 `可建 Note` 且输出 Material 已登记时，才进入 Note 状态机。
- **SKU / 衣服** — 一件衣服，内容中枢（可选）。Note/Material 可关联到它。
- **Runbook** — 状态→动作 的纯函数路由（`orchestrator/runbook.route`），推进器的决策核，零 IO 零 LLM。
- **Record（记录适配器）** — `orchestrator/bitable.Record`：飞书多形态 record dict 的 seam。窄接口 `text/ts/link_ids/bool`，字段名走 `NoteFields/MaterialFields` 词汇常量。所有字段访问收口于此（候选A 深化，2026-07-08）。

## 架构词汇（见 /codebase-design）

module / interface / depth / seam / adapter / leverage / locality / 删除测试。

## 三层分离

能力=skill（怎么做，git 锁版）· 模式=data（每号 strategy/画像 + Bitable 状态）· 引擎=泛化（orchestrator + planner，读声明/状态执行，零账号特定代码）。加账号/加模式=改 data 零代码。

详见 `docs/架构与方法论.md`。
