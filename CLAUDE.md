# CLAUDE.md

巧荷内容工厂的 **harness**。**观云=母公司,巧荷=当前品牌**(`brand` 维度 / `brands/巧荷/` / 人看到的显示,一律"巧荷";仓库名拼音不改)。

环境事实(Base/账号/凭证/工具):`AGENTS.md`。架构:`docs/架构.md`。病例:`docs/踩坑账.md`。词汇:`CONTEXT.md`。

## 心智

**Agency 来自模型。Agent 产品 = 模型 + Harness。**
**我们不"开发 agent",我们造 harness。造好 harness,模型会完成剩下的。**

```
Harness = Tools + Knowledge + Observation + Action Interfaces + Permissions
```

- **Tools / Action Interfaces** — 它的手:`feishu_io` `netpan` `ark` `media` `ingest` `xhs-extract`
- **Knowledge** — 它的知识:`skills/`(按需加载)+ 本文件(常驻,所以必须短)+ 账号声明 + schema 常量
- **Observation** — 它的眼睛:`cockpit`(今日卡片)`shotlist`(补拍单)`report`(周报)+ base 视图
- **Permissions** — 它的法律:`guard.py` 五道红线门

**技能是 Knowledge,不是函数。** agent 把 `SKILL.md` 读进上下文(渐进披露),它变成模型此时的知识,**然后模型自己动手**。不是 `result = skill.f(x)` 等返回值——那等于又把决策从模型手里拿走。

## 唯一判据(动手前必过)

> **这段代码是在替模型做决策,还是在给模型提供 Tools / Knowledge / Observation / Permissions?**
>
> **替模型决策 → 错。删掉,交回去。**
> **提供手/知识/眼睛/法律 → 对。那是 harness 的本分。**

推论:「每天定时看网盘有没有新素材,有就打标」—— **这是模型的操作**,哪怕天天发生。harness 只给它手(`netpan.list_dir` / `ingest.register`)、知识(`tagging-material` 技能)、法(`guard`)。**"这张图是什么类型"是判断,归模型。**

**技能 vs 红线**:能被违背而不出事的 → 技能;**一旦被违背就是事故的 → 红线**。
(技能里写着"绝不抄原句",模型照样搬;拦住它的是 `guard.assert_no_source_leak`。)

## 红线(焊死,不可协商)

- **只写测试库 `ZhzJbf`**。生产库 `N9IVbi` **读也不许碰** —— 守卫必须在**任何 IO 之前**。
- **绝不自动发布。** 出稿一律止于『草稿待发』。
- **绝不代勾 AI 声明。** AI 像素 → 素材『来源=AI生成』→ 门要求声明 → **人勾**。
- **红线不许有旋钮。** 阈值焊成常量;要改就改代码 + commit + 留痕。
- 明文凭证只从 env 读,绝不入代码/库。

## 实测纪律

- **不搞 mock、不搞 stub。** 绿门只证明"代码和 mock 自洽";交付只认真跑(真库/真 ARK/真网盘/真小红书)。
- **别信形态,先真读一遍 API 返回**再写代码、再下结论。(同一个坑栽过四次。)
- **每个写操作后,用只读命令读回来自证。** 不信自己的叙述。
- **串行跑门,别并发**(并发制造过假红)。
- **检查器自己必须过"把 bug 塞回去,看它报不报"。** **误报比漏报更毒** —— 喊三次狼来了,门就没人看了。
- **要么真做出来,要么删掉。** 别留着骗人。

## 人面(运营不敲终端;人面不过 = 系统不可用)

真渲染 今日卡片 / 补拍单 / 周报,以运营和摄影师的眼睛读,问:
① 他会不会懵? ② **有没有话在骗人**(数字对但话不对 / 建议没基于真实状态 / 承诺了做不到的事)? ③ 有没有**算了却没给人看**、**拦了却没说为什么**?

- **拦住 ≠ 说清楚。** 好门 = 拦住 + 说明白为什么 + 给出路。别甩堆栈给人。
- **只说确凿为真的话。** 没核实的断言不许进人面产物。

## 核心病

**"人想起来方便的逻辑,落实下来都是 bug"** —— 在脑子里想通了就当做完了。
镜像同样致命:**本可以直接做完的事,别想成要先造个东西。**

## 提交

**中文**(注释/commit/issue)。**commit / push / issue 自动做,别问。**
提交前:`bash scripts/review_gate.sh --full` + `python3 scripts/alignment_audit.py` **全绿**。红=不留,别拿"部分绿"充数。

## 已知欠账

`scripts/tag_materials.py` `daily_dispatch.py` `draft_one.py` —— **把驾驶者换成了导轨**:它们替模型决定了"这张图是什么""今天派什么活""选哪些素材""稿子行不行"。该拆成:**手留 harness,决策还给模型,方法进技能**。详见 `docs/架构.md` 第四节。
