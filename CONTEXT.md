# CONTEXT · 领域词汇（观云 Workspace）

> 给好 seam 起名的地方。架构评审与新代码用这些词，别漂成 component/service/handler。

## 领域概念

- **Note（笔记）** — 一条内容一行，状态机脊柱（想法储备→待拍素材→待出文案→草稿待发→已批准→待发布→已发→已回流；暂缓归档旁路）。飞书「笔记表」一行 = 一个 Note。
- **Account（账号）** — 一个小红书号。有**两张脸**（皆 data，非 skill）：**画像** `accounts/{号}.md`（发什么/怎么写，喂生成）+ **strategy** `accounts/{号}.strategy.json`（怎么运营：cadence/material_needs/autonomy，喂 planner）。
- **Material（素材）** — 一个图/视频文件。软链上墙（原件不动）+ 挂 SKU（关联衣服）+ 登记「素材表」。
- **SKU / 衣服** — 一件衣服，内容中枢。Note/Material 都关联到它。
- **Runbook** — 状态→动作 的纯函数路由（`orchestrator/runbook.route`），推进器的决策核，零 IO 零 LLM。
- **Record（记录适配器）** — `orchestrator/bitable.Record`：飞书多形态 record dict 的 seam。窄接口 `text/ts/link_ids/bool`，字段名走 `NoteFields/MaterialFields` 词汇常量。所有字段访问收口于此（候选A 深化，2026-07-08）。

## 架构词汇（见 /codebase-design）

module / interface / depth / seam / adapter / leverage / locality / 删除测试。

## 三层分离

能力=skill（怎么做，git 锁版）· 模式=data（每号 strategy/画像 + Bitable 状态）· 引擎=泛化（orchestrator + planner，读声明/状态执行，零账号特定代码）。加账号/加模式=改 data 零代码。

详见 `docs/架构与方法论.md`。
