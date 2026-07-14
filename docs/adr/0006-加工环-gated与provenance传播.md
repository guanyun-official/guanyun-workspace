# ADR-0006 · 加工环:gated 默认关 + provenance 沿衍生链传播 + AI 声明只 surface

- 状态:已接受(2026-07-13,对齐跑实 loop 定调)
- 相关:ADR-0004(媒体唯一源与素材来源语义)、`orchestrator/processing.py`、`orchestrator/guard.py`、`orchestrator/draft.py`、`orchestrator/cockpit.py`、`scripts/ingest.py`(store_produced)

## 背景
"人只管头尾"的中间,选中原始素材后、挂笔记前,常有一步很自然的想法:**要不要把几张素材整合剪辑一下?要不要 AI 生成点东西达到更好效果?**(拼图、剪辑、AI 补场景、甚至 AI 直接生成新素材)。作为人很自然,但怎么给到 AI、又不塌合规(AI 参与的笔记必须标 AI)、还不背过早复杂度——需要定清结构。

同时这是"复杂流程在技能体系下怎么开发"的活案例(见 `docs/架构.md` 三层判据),用它把边界钉死。

## 决策:决策/执行交技能,落点/provenance/AI声明代码焊死,整环默认关

**三层判据落到加工环:**

| 部分 | 归属 | 谁做 |
|---|---|---|
| 要不要加工、哪种、怎么拼/生成 | **技能(智能叶子)** | 注入的 `decide` / `execute` 钩子(未接=骨架) |
| 加工步的落点(选材后、挂笔记前) | **workflow 关节** | `processing.maybe_process`(gated) |
| 成片来源随像素出处 | **代码焊死** | `processing.derive_source`,**绝不给智能体判断** |
| 笔记是否须勾 AI 声明 | **代码焊死** | 复用 `guard.ai_declaration_required`,系统只 **surface**,人自己勾 |

**1. 整环默认关(`GY_PROCESSING_ENABLED=0`)。** `maybe_process` 在默认关或缺技能钩子时**原样返回原始素材**(现状链,零改动)。真需求(某模式非拼图/AI 图不可)到再开并接钩子。→ 现在不背复杂度,骨架先在,开箱即用。

**2. 成片是素材表一条新行,不拆二表。** 加工产出 = `store_produced` 回存网盘 03-成片 + 登记素材表新行;衍生自谁记 `备注`/`生成参数`。素材/笔记连贯(ADR-0004 单一源)。

**3. ★provenance 沿衍生链传播,代码焊死★。** `derive_source(输入素材来源[], 加工是否用了AI)`:
- 任一输入素材 = AI生成,**或** 加工过程用了 AI 生成新画面 → 成片 = **AI生成**(须声明);
- 否则(纯剪辑/拼接/调色,像素都来自实拍)→ **实拍**(免声明)。
`execute` 钩子产出成片时**必须**用它定来源再交 `store_produced`。这样"以后原始素材里也有 AI 生成的、其参与的笔记要标 AI"自动就对——**不靠谁记得**。

**4. AI 声明只 surface,人自己勾(红线)。** 笔记须声明 = 其任一关联素材来源=AI生成(`guard.ai_declaration_required`,不重造)。系统在 `cockpit.today_panel/card` 把"⚠️需 AI 声明"**顶到人审前**,并在 `publish.review_approved` 门上拦"含 AI 未勾不进待发布"。**系统只算+提示,勾选永远是人**。

## 后果
- **零行为变化上线**:`draft.create_draft_note` 已插 `maybe_process` seam,默认关=passthrough,keep 门全绿(pytest 235 / ar_check 100)。
- **合规不塌**:provenance 用代码传播、AI 声明用素材来源事实算,实拍不必逐条人工确认、AI 合成一条都跑不掉;人勾的红线不动。
- **可直测**:`derive_source`、`maybe_process`(钩子注入)、AI声明 surface 都有单测(`tests/test_processing.py`、`tests/test_cockpit.py`)。
- **待接**:`decide`/`execute` 技能(加工决策 + 拼/剪/AI图生图执行)+ AI 图像生成后端 seam——真需求到再建,本 ADR 已把结构钉死,建时不必再纠结边界。
