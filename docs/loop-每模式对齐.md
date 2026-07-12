# LOOP · 每账号每模式"继续发相似" 对齐循环

> 一句话目标:**每个账号每个模式都能持续产出"和它历史帖相似"的稿,且加号/加模式=改 data 零改代码零改表(scalable)。**
> 本文 = `/goal`(目标) + `/loop`(每轮做什么) + `monitor`(盯什么) + 轻量 `/verify`(每模式验收)四合一控制面。
> 逐模式过一遍,和 2026-07-12 讨论 ootd 号时同一套动作。**这张表就是状态,resumable;加一行 = 纳管一个新模式。**

## /goal — 目标与完成定义

- **总目标**:体系支持"每 账号×模式 继续发相似内容",且可扩展。
- **单模式完成定义(Definition of Done)**:一条 dry-run 稿在盲评里"像该号该模式的历史帖"(调性/结构/篇幅/钩子都对位),且 `轻量verify` 全绿、不破坏既有硬门。
- **scalable 判据**:纳管一个新账号/新模式 = 本表加一行 + 写账号 md/建 gen_skill,**不改 orchestrator、不改 schema**。做不到就是架构欠账,记进"待办"。

## 精神:大刀阔斧断舍离(loop 的一条铁律)

- **每模式 = 1 个专门(特化)技能**——住 `local-skills/`、含该号真实帖 few-shot。**要点:每模式的 SOP 尽量唯一**,一个模式一条清晰打法,**别让 agent 在多个相似技能间混淆**(这才是"1 特化"的真正目的)。
- **通用能力(剪辑 `video-editing`、采集 `xhs-extract` 等)扁平共享、随便调**——不做"每模式硬配一个通用"的要求;注册给 agent 也是扁平的、按需取,用哪个无所谓。方法能并进特化就并(ootd 逐字稿四层已并进 `writing-ootd-caption`);**冗余/易混的通用技能就删**(`guanyun-OOTD-text` 已删)。
- 加一分能力前先问:能不能删一分?**清爽 = 可维护 = scalable。** 每号每模式连带体系都按这套仔细打磨,不是填完了事。

## /loop — 每轮处理一个"账号×模式",5 步

> 和讨论 ootd 一致。每轮只推进一行,串行不并发。

0. **看真实在发什么**(extract 技能):抓该号真实帖 → 记 调性 / 结构 / 篇幅 / 钩子 / 素材形态。
   - 标题级:非登录 `xhs user --url <主页> --raw-fields` 恒能拿(注:默认 normalize 会把 note_id 抹掉,取正文另说)。
   - 正文/逐字稿:非登录 `xhs note` 需 **note URL**(主页 SSR 无 note_id);无 URL 则走登录(mcp 扫码 / claude-in-chrome)。
1. **skill 适配**:该 playbook 的 gen_skill(特化)是否抓住这个模式的真实 voice?通用基座是否匹配?few-shot 够不够(标题级 → 结构级)?**不合就直接增删调整技能**(特化住 `local-skills/`,通用改 `qiaohe-skill`)。
2. **base 适配**:这个模式在 base 需要的字段/tag/数据齐不齐(账号表主页 URL、内容类型 tag、素材投影…)?数据缺口回填——**只测试库 ZhzJbf,破坏性先备份读回自证,只改自建**。
3. **workspace 适配**:账号画像 6 维完整吗(定位/打法/爆款规律/变现引流/可迁移打法/风险)?playbook 指针、素材需求、篇幅公式对吗?
4. **轻量 verify**:跑 `verify_mode <账号> <模式>` 全绿(见下)+ 既有硬门不回归(单测 / ar_check=100 / schema 不漂)。绿了才在本表打勾。

## monitor — 盯三样

- **进度**:本表未完成行数(下方 WORKLIST 未全绿的行)。
- **回归**(既有 3 monitor):单测红 / `ar_check` < 100 / `schema/test` git diff 漂移。
- **每模式 verify 由绿转红**:改一处别踩塌另一处。

## 轻量 /verify — `verify_mode <账号> <模式>`(待建,规格如下)

一个模式"能继续发相似"的最小充分证据,四查(全绿才算过):
1. **skill 加载**:`load_gen_skill(gen_skill)` 非空,SKILL.md 真被读到。
2. **few-shot 进 prompt**:`compose_prompt` 产物里确有该号 few-shot 段(非空、贴该模式)。
3. **素材够**:该模式 `material_needs` 在素材表有可选素材(≥1)。
4. **dry-run 稿贴调性**:`draft_one --account <号> --content-type <模式>`(stub 零成本先跑通,real 抽查)产物结构/篇幅符合该模式公式(如 ootd 视频=短意境;种草=口语安利;官号=四层叙事去科普)。
> 只读为准;写操作后只读自证。verify 脚本本身带单测(加能力必带测试)。

## WORKLIST — 状态表(一行一模式;这就是 loop 的记忆)

| # | 账号 | 模式 | gen_skill | 0看真实 | 1skill | 2base | 3workspace | 4verify | 备注 |
|---|---|---|---|:--:|:--:|:--:|:--:|:--:|---|
| 1 | ootd号 | 视频唯美OOTD | writing-ootd-caption | ✅ | ✅ | ✅ | ✅ | ✅ | **整行绿**。技能合并+真跑验证逐字稿(修compose_prompt"就短"bug+回归锁);base回填主页URL(读回自证);画像补爆款规律/变现引流/可迁移打法3维。摩擦已修:主页链接进URL_FIELDS |
| 2 | ootd号 | 图文唯美OOTD | writing-ootd-caption | ✅ | ✅ | ✅ | ✅ | ✅ | **整行绿**。技能加图文分支(视频→逐字稿/图文→几句短文,SOP分开);真跑验证图文出短文非逐字稿(2.0元) |
| 3 | 图文号1 | 素人图文种草 | writing-amateur-ootd | ✅ | ✅ | ✅ | ✅ | ✅ | **整行绿**。skill无需改(已含momo few-shot);真跑验证:素人真实体感("讲不出专业词，很轻也很稳")+纠结安利腔,与ootd判若两号 |
| 4 | 图文号2 | 素人图文种草 | writing-amateur-ootd | ✅ | ✅ | ✅ | ✅ | ✅ | **整行绿**。skill无需改;真跑验证:身材友好强安利("显瘦给满分""微胖姐妹放心冲"),与#3同技能不同画像→不同人设,差异化成立 |
| 5 | 官号@巧荷·东方美学 | 品牌新作展示 | writing-brand-newpiece | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | **⏸暂缓(本批不做)**:模式复杂——需真实衣服KB+货对板不编造;writing-brand-newpiece 偏薄(844字,4层方法原在已删的guanyun里),下一批补 |

图例:⬜未做 🔶进行中 ✅过。

## 已发现待办(来自 ootd 讨论,滚动补)

- [x] **`guanyun-OOTD-text` 已删(断舍离)**:它就是时从今式四层的老底子;方法已并入 ootd 的 `writing-ootd-caption`(压缩去考据),各号文案改由 workspace 特化技能自足。清了 skills.lock/symlink/AGENT.md/cron 引用。
- [x] **ootd号 逐字稿技能已合并**:`writing-ootd-caption` 现=短标题 + 25-30s 逐字稿(时从今式四层压缩、去考据)。**遗留**:dry-run 只出了短文案没出四层逐字稿 → `compose_prompt` 截 1500 字或提示没压住,待修(见 #1 的 4verify)。
- [ ] **ootd号 画像补 3 维**:爆款规律 / 变现引流 / 可迁移打法(现只显式落了定位/打法/风险)。
- [ ] **base 数据缺口**:ootd号 账号表「主页链接」存的是昵称"巧荷｜OOTD",应回填真 URL(user_id `60befdfd000000000101cc10`,见 `docs/MIGRATION_P2.md`)。
- [ ] **extract 技能限制记档**:非登录主页 SSR 无 note_id → 取正文需 note URL 或登录态;`--raw-fields` 不解决(那批 24hex 是作者 userId,非 note_id)。

## 权威依据
`AGENTS.md`(环境/红线)· `docs/架构一图流.md` · `brands/巧荷/accounts/README.md`(账号=data 非一号一技能)· `CONTEXT.md`(词汇)。
