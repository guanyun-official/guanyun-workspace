# CONTEXT · 领域词汇

> 给好 seam 起名的地方。写代码/评审用这些词,**别漂成 component / service / handler**。
> 心智和判据:`CLAUDE.md`。全景架构:`docs/架构.md`。

## 三层(先记住这个,别混)

- **Agent = 模型** —— 做**一切需要判断的事**。
- **Skill = Knowledge** —— 它此时的**指导**(方法论/SOP/范例)。**技能不是函数**:agent 把 `SKILL.md` 读进上下文,然后**自己动手**。
- **Harness = 本仓 + 运行时** —— **Tools + Knowledge + Observation + Action Interfaces + Permissions**。**harness 不思考。**

## 领域概念

- **Note(笔记)** — 一条内容一行,**状态机脊柱**:想法储备 → 待拍素材 → 待出文案 → 草稿待发 → 已批准 → 待发布 → 已发 → 已回流(暂缓归档旁路)。飞书「笔记表」一行 = 一个 Note。
  **模型只把 Note 推到『草稿待发』** —— 后面的审和发是**人的动作**(红线)。
  『待出文案』= 派活占位(**还没内容**);『草稿待发』= **已有稿子,人正等着审**。这俩是两回事:占位可推进,**待审稿不许覆盖**。

- **Account(账号)** — 一个小红书号。两张脸(皆 data):
  画像 = `brands/巧荷/accounts/{号}.md` 正文(发什么/怎么写);
  strategy = 同文件 frontmatter(cadence / autonomy / sourcing / **playbooks[]**)。
  `orchestrator/accounts` 加载。**它是常驻 Knowledge,不是配置文件。**

- **Playbook(方法论)** — 账号的一套发布方法论 = `content_type` + **`gen_skill`** + `material_needs` + 调性 + `body_len`。
  一号可多套。**加一套 = 写声明,零代码。**

- **gen_skill(生成技能)** — 一套 playbook 指向的写作技能(`skills/writing-*`)。
  模型加载它的 `SKILL.md`(含**该号真实帖 few-shot**),照它写。
  **技能唯一真源 = `qiaohe-skill` 仓**;`skills/` 是装出来的符号链接。**workspace 不藏技能。**

- **Material(素材)** — 一个图/视频**整文件**。真身在网盘(`/巧荷素材/`),表里只存**网盘指针** + 小缩略图。
  『类型』(12 类)· 『来源』(实拍 / **AI生成** —— 决定要不要勾 AI 声明)· 『备注』(vision 打的标,**分发选材靠它语义寻址**)。
  **视频的备注只描述一帧关键帧** —— 所以它标着 `(视频关键帧)`,别当成整条视频。

- **provenance(来源传播)** — `processing.derive_source`:成片来源**随像素出处**。
  纯拼接/剪辑(像素全来自实拍)→ 『实拍』(免声明);**任一输入是 AI、或过程用了 AI 生成新画面 → 『AI生成』**(下游必须人勾声明)。
  **这是合规,不是判断。焊死在代码里,绝不给模型决定。**

- **加工环(ADR-0006)** — 选材之后、挂笔记之前的 gated 一步。
  **决策(要不要加工/哪种)= 模型**(`compose.ai_decide`,看素材的 vision 标注);
  **执行 = 手**(拼图 / AI封面);**provenance + AI声明 = 代码焊死**。
  默认关(`GY_PROCESSING_ENABLED`)—— 关的**不是"要不要加工"这个判断**,关的是"这条能力放不放出去"。

- **文案的事实底座 = 素材备注**(**这是唯一在跑的机制,别搞混**)
  拍素材 → vision 打标出『备注』(颜色 / 光泽 / 垂坠 / 场景 / 光线 / 姿势 / 氛围)
  → `draft.material_facts()` 把**这条稿真正要配的那几张图/视频的备注**喂进 prompt
  → **文案是配着这些画面写的**。
  **写画面里看得出的;看不出的(面料成分、克重、朝代形制、非遗工序)一律留白,严禁编造** —— 否则货不对板。
  ⚠️ 顺序焊死:**先挑素材,再写文案**。反过来(先生成后挑图)LLM 眼前一片空白却被要求写质感 → 它只能编。

- **不注册衣服**(2026-07-14 整条支线已删) — 三个号就是:**拍素材 → 打标 → 配文案发**。
  没有衣服档案、没有 `--clothes`、没有知识库。
  "文案怎么和图片关联" 的答案**只有一个**:**素材的『备注』**(上一条)。别再去找别的。

- **唯一源边界** — Base owner = **运营事实与状态**(它同时是人的驾驶舱);
  workspace owner = 画像 / strategy / playbooks / 内容 know-how;
  skill owner = 可复用的"怎么做";网盘 owner = **媒体真身**。
  **非 owner 只能存指针/索引/派生快照。**

- **记录收窄函数** — `orchestrator/bitable` 的 `text / parse_ts / link_record_ids`:
  飞书多形态 record dict 的收窄 seam。**调用点一律 `bitable.text(f.get(字段常量))`**,字段名走 `NoteFields / MaterialFields / …` 常量。
  ⚠️ **link 字段的形态是陷阱**:`search` 返回 `{link_record_ids}`(无 text),`list/get` 返回 `[{record_ids, text}]`。
  **别信形态,先真读一遍返回**(这个坑栽过四次,见 `docs/踩坑账.md`)。

## 架构词汇

module / interface / depth / seam / adapter / leverage / locality / 删除测试。
