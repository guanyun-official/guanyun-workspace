# CONTEXT · 领域词汇（观云 Workspace）

> 给好 seam 起名的地方。架构评审与新代码用这些词，别漂成 component/service/handler。
> **2026-07-11 大刀阔斧后**：重引擎(engine/planner/推进器)、素材视图层(View/Clip/UsageLedger)、
> MediaTask、AccountKernel、Runbook 已删。下面是精简骨架的现行词汇。

## 领域概念

- **Note（笔记）** — 一条内容一行，状态机脊柱（想法储备→待拍素材→待出文案→草稿待发→已批准→待发布→已发→已回流；暂缓归档旁路）。飞书「笔记表」一行 = 一个 Note。**薄执行器只把 Note 推到「草稿待发」**，后面靠人审+人发。
- **Account（账号）** — 一个小红书号。**两张脸**（皆 data）：画像 `brands/观云/accounts/{号}.md` 正文（发什么/怎么写，喂生成）+ strategy frontmatter（怎么运营 cadence/autonomy/sourcing，含 **playbooks[]**）。`orchestrator/accounts` 加载。
- **薄执行器（ThinExecutor）** — `orchestrator/draft.py`（CLI `scripts/draft_one.py`）= 体系核心。读账号声明 → 取该号 playbook 的 gen_skill → 加载其 SKILL.md（真实帖 few-shot）→ 组稿（画像+few-shot+配方）→ 过 base 红线闸 → 写笔记表一行「草稿待发」。stub 默认零成本，`--llm real` 走 `llm.run_prompt` 预算帽。不走重引擎、不排产、不建视图。
- **Playbook（方法论）** — 账号声明的一套发布方法论（`strategy.playbooks[]`）= 内容类型 content_type + **gen_skill**（产这套笔记的技能）+ material_needs + 调性。一号可多套（现一号一套）；`orchestrator/accounts.playbooks_of/resolve_playbook/gen_skill_of`。加一套=写声明零代码。
- **gen_skill（生成技能）** — 一套 playbook 指向的生成能力。特化的住 `local-skills/`（如 writing-ootd-caption，compose 通用能力 + 该号真实帖 few-shot）、通用的在 qiaohe-skill remote。薄执行器 `load_gen_skill` 读其 `SKILL.md` 正文注入生成 prompt（补上「gen_skill 曾只是标签」的缺口）。
- **SourceOwnership（唯一源边界）** — Base / workspace / skill / 素材盘的 owner 规则。Base owner=运营事实、状态、员工界面索引；workspace owner=画像、strategy、playbooks、**内容 know-how**；skill owner=可复用“怎么做”；素材盘 owner=媒体文件。非 owner 只能存外键/索引/派生快照。审计已从重型 AccountKernel 收敛为 ar_check 的「唯一源」检查（Base 账号表名 ⊆ workspace 声明）。详见 `docs/SOURCE_OWNERSHIP.md`。
- **知识库 know-how** — `brands/观云/knowledge_base/衣服/{衣服编号}.md`：从 Base 衣服总表迁出的**内容 know-how**（卖点内核/形制·设计理念/文物出处·文化依据/纹样），写考据文案用。§4：衣服/工艺/文物出处是内容 know-how，归 workspace，不进 Base 商品目录。
- **Material（素材）** — 一个图/视频**整文件**，软链上墙（原件不动）+ 登记「素材表」。`scripts/ingest.py` 的 scan/link/register/orphans 是安全摄入原语。（薄执行器 A 当前只产文案、尚未接素材选择，见 issue #32。）
- **SKU / 衣服** — 一件衣服。Base「衣服总表」已瘦身为身份/关系字段（衣服编号/款式名称/启用账号/工艺·面料 link/生命周期状态），内容 know-how 迁 workspace 知识库。
- **Record（记录适配器）** — `orchestrator/bitable.Record`：飞书多形态 record dict 的 seam。窄接口 `text/ts/link_ids/bool`，字段名走 `NoteFields/MaterialFields/AccountFields/ContentTypeFields` 词汇常量。所有字段访问收口于此。

## 架构词汇（见 /codebase-design）

module / interface / depth / seam / adapter / leverage / locality / 删除测试。

## 三层分离

能力=skill（怎么做，git 锁版 `skills.lock.json`）· 模式=data（每号 strategy/画像 + Bitable 状态）· 引擎=**薄执行器**（`orchestrator/draft.py`，泛化：读声明/状态执行，零账号特定代码，已在 4 号泛化验证）。加账号/加模式=改 data 零代码；新需求=加 skill 不改 schema。

详见 `docs/架构与方法论.md`。
