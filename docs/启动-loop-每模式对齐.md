# 启动句 · loop:每号每模式"继续发相似"对齐(试水批)

> 直接贴进新 session 开场。控制面/状态/待办都在 `docs/loop-每模式对齐.md`(那张 WORKLIST 就是 loop 的记忆,resumable)。

---

巧荷内容工厂 · loop:每号每模式"继续发相似"对齐。**试水批 = ootd号 / 图文号1 / 图文号2 三个(模式固定);官号押后一批**(要真实衣服KB+货对板,复杂)。

**先读**:`docs/loop-每模式对齐.md`(本 loop 的 /goal + monitor + 轻量verify + 状态表)· `AGENTS.md`(环境/红线/工具)· `docs/架构一图流.md` · `brands/巧荷/accounts/README.md`(账号=data;**加号/加模式=表加一行+写 md,插拔式注册,不改代码不改 schema**)。

**目标**:每 账号×模式 能持续产出"像它历史帖"的稿,且体系 scalable(插拔)。

**怎么跑**:按状态表逐行推进,每行(一个账号×模式)走 5 步、和已打磨的 ootd 视频同一套——
① **看真实在发什么**(extract 技能):标题非登录 `xhs user --url <主页> --raw-fields` 恒能拿;**正文/逐字稿要 note URL**(主页 SSR 枚举不到 note_id,人贴帖链接最省事,或登录 mcp/claude-in-chrome)。
② **skill 适配**:特化技能住 `local-skills/` + 该号真实帖 few-shot;不合就**直接增删调整**。
③ **base 适配**:该模式需要的字段/tag/数据缺口回填——**只测试库 ZhzJbf,破坏性先备份读回自证、只改自建**。
④ **workspace 适配**:账号画像 6 维(定位/打法/爆款规律/变现引流/可迁移打法/风险)、playbook 指针、素材需求。
⑤ **轻量 verify**:真 dry-run 出稿贴调性(`draft_one --account <号> [--content-type <模式>] --llm real`,不加 --write 不写库)+ 单测全绿 + `ar_check`=100 不回归。绿了才在表里打勾。

**断舍离精神(loop 铁律)**:**每模式只求 1 个专门(特化)技能——目的是每模式 SOP 尽量唯一,别让 agent 在相似技能间混淆**;通用能力(剪辑 `video-editing`、采集等)扁平共享、随便调,不硬配。方法能并进特化就并、冗余/易混通用就删(`guanyun-OOTD-text` 已删)。加一分先问能不能删一分。**每号每模式连带体系都要仔细打磨,不是填完了事。**

**已到哪**:
- **#1 ootd号·视频唯美OOTD**:①看真实✅(22帖标题 + 时从今 3 条逐字稿研究)②skill✅(`writing-ootd-caption` 已合并=短标题 + 25-30s 时从今式四层逐字稿,去考据;修了 `compose_prompt` 硬编码"视频就短"的 bug、加回归锁,真跑验证逐字稿出来了)⑤verify🔶(稿+硬门过);**剩** ③base(ootd号账号表「主页链接」存的是昵称,回填真 URL,user_id `60befdfd000000000101cc10`,见 `docs/MIGRATION_P2.md`)④workspace(画像补 爆款规律/变现引流/可迁移打法 三维)。
- **#2 ootd号·图文唯美OOTD / 图文号1 / 图文号2**:待做(图文号1/2 主页 URL 已在 base✓)。

**铁律**:只测试库 ZhzJbf 写、生产 N9IVbi 焊死;绝不自动发布、AI 声明人勾、防搬运(产出不含对标原句);真跑优先、**LLM 一次一个别重跑**(一发 ≈2 元);base 破坏性先备份读回自证、只删自建;串行不并发;输出中文;防虚构:每写操作只读命令自证,叙述与只读不符以只读为准。

从 #1 剩的 base/workspace 接着做,或你说从哪个号起。

---
