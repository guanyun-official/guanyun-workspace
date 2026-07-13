# dogfood 驱动 loop 启动词 · 全链路真过(paste-ready)

> **为什么要它**:过去多轮"pytest 全绿 / ar_check 100 / 三视角无 blocking"照样交付不可用——**绿门测的是 mock/stub(我写的假数据),不是真飞书**。典型:飞书 `records/search` 返回 link 字段是 `{link_record_ids:[...]}`(无 text),mock 用的是 `get` 的 `[{text,record_ids}]`——mock 比真数据"干净",于是"账号名读空、派活不去重、素材不挂"的 bug 过了每一轮绿门,当运营真跑 30 秒才暴露。
>
> 结论:**mock 只配单测隔离;交付判定看 dogfood 真跑,且全体系每条链路都真过一遍。**

---

## 直接把下面整段发给 `/loop`

```
/loop dogfood 驱动把巧荷内容工厂跑成真可用:全体系每条链路都对测试库真跑一遍、不同角度真压测,用出来的问题才算问题,发现即修,直到 17 条链路全真过不撞墙。别信绿门,信真跑。

【核心纪律(违反=这轮白干)】
1. 别信绿门:pytest/ar_check 绿只证明"代码和 mock 自洽"。交付判定看 `bash scripts/review_gate.sh --full`(含 dogfood_smoke 真库冒烟 + check_p + 综合验收)真库跑绿。
2. 别搞 mock 假绿:单测 mock 必须用真飞书形态(search=`{link_record_ids}`、get/list=`[{text,record_ids}]`、url=`{link,text}`、date=毫秒int)。拿不准先真跑一条 search/get 打印形态再写 fixture;形态不符=当场改 + 加真形态回归锁。link 显示名统一 `bitable.link_names(v, feishu_io.name_map(表,名字段))`,别用 text()。
3. 防虚构:每个写操作后 search/get 真读回来自证,不信叙述里的成功。
4. 每修一个真 bug:加真形态单测回归锁 + 让 dogfood_smoke 覆盖它(下次真跑就拦)。

【谁跑什么:运营不敲终端!】运营的世界=① 飞书 base 里看视图/点审批/填发布链接;② 手机收系统推的卡片(today_card/补拍单/周报)。下面 CLI 是 **cron(自动化)和 agent(你)跑的**,不是给人敲的。所以 dogfood 分两层:**L0 人的链路(飞书面)才是"真可用"的判据**,L1-L17 是喂给它的自动化链路。

【L0 人的链路(飞书面,运营真正用的——这条不过=系统不可用)】
- 今日卡片:`today_card` 渲染→按**真账号名·模式**分组、📋待审/📤待发可点标题直达 base、🚦控量预警、📷补拍单;绝不出现空账号表头(search 形态坑直接砸这)。
- base 交互:运营在 base 改状态=审批、填发布链接=认领;确认视图/筛选让待审/待发/待回填一眼可筛、深链点开即达该行。
- 推送:`today.py --alert`/`shot_list --alert`/`weekly_report --alert` 真推 hermes 到人手机(ALERT_DRY_RUN 看降级),人不看终端也收得到。
- 断言:卡片人能看懂、可操作;头(拍)尾(审/发)全在飞书内闭环,不需要碰终端。

【全体系 17 条自动化/agent 链路 —— 每轮挑几条真跑到底(命令→看人能懂的真事→压测角度)】
L1 素材入库:`python3 -m scripts.tag_materials --from-netpan /巧荷素材/待入库`(干跑)/ ingest_incremental / backfill_thumbnails / slice_video → 真读素材表:类型对、来源就低(AI落AI)、缩略图有、去重不重标、成本记账。压:图/视频/HEIC/坏图/大图降采样。
L2 找热点:`python3 -m scripts.harvest_trends` → 灵感库去重、无标题过滤、正文落库(防搬运源)。压:重复灵感、脏数据。
L3 派活:`python3 -m scripts.daily_dispatch` → 去重键真名(不是空)、暂停号跳过、在途真跳过。压:base自动排产 暂停/强制/跟随。
L4 出稿:`python3 -m scripts.draft_one --account <号> --llm real`(真花钱一条)/ run_day → 对味few-shot、绑衣服防编造、蹭爆款`--source-text`真拦逐字搬、成本帽、AI素材surface需AI声明、止于草稿待发。压:新号冷启、一号多模式、官号品牌新作。
L5 审批:`python3 -m scripts.publish_ready` → AI合成必拦人勾/全实拍免勾、控量逼近标红、货对板。压:混合素材、超量。
L6 发布认领:cockpit fill_publish_link 认领链接 → 真读回:状态=已发、实际发布日已写、多条命中返候选不瞎写、账号名匹配(link解析)。
L7 回流:`python3 -m scripts.collect_metrics`(stub/真采)→ 写回点赞/收藏、已发→已回流、取真链接非描述、冷热分离(已发全采+近30天已回流刷新+老帖沉降)。压:采集失败不推进、大量已发不整拉。
L8 复盘:`python3 -m scripts.weekly_report` → 按方法论排名、周环比、无数据不崩。
L9 驾驶舱看:`python3 scripts/today.py` / today_panel/weekly_schedule → 账号名非空(link解析)、控量、待回填、补拍、周排期不全拉笔记表。
L10 拍摄需求:`python3 scripts/shot_list.py` → 按类型缺口、投递去向。
L11 成本/预算:`python3 -c "from orchestrator import cost; print(cost.monthly_cost_cny(), cost.budget_alert())"` → 当月聚合、超阈告警、豆包看图入帽。
L12 红线闸:三写路径真指向生产库→guard真拒(物理到不了);防搬运门真拦逐字搬。
L13 schema契约:`python3 scripts/check_schema_drift.py`(活探针)+ dump_schema/schema_diff → 代码词汇⊆活库、漂移真报。
L14 数据安全:`python3 scripts/backup_tables.py` + restore_tables 真恢复一张 → 误删可恢复真跑通。
L15 运维巡检:`python3 scripts/cron_status.py` / verify_usable / sim_loop 闭环模拟 → cron态、全账号全模式闭环真走一圈。
L16 加工环(gated默认关):processing.maybe_process 默认no-op原样;开 GY_PROCESSING_ENABLED=1 → compose拼图、provenance/AI声明随像素传播。
L17 技能层:`bash scripts/install_skills.sh` + skills_lock.installed_drift → 锁版==HEAD、draft few-shot真载入。

【不同角度真压测(每轮至少挑 2-3,真跑不是想象)】
新号冷启 / 爆款蹭稿防搬运 / 超量控量红线 / AI素材AI声明 / 规模(大量已发不整拉,探针计list_records=0) / 并发写flock真挡 / 坏数据边界(空账号/无素材/坏链接/字段缺失/超长)不崩降级可读 / 红线穿透三写拒生产。

【发现即修】简单当场修;复杂诊断→issue→本轮清,不留悬空。

【每轮 VERIFY】`bash scripts/review_gate.sh --full` 全绿(dogfood冒烟+keep门+check_p1-6+verify_usable)。红=回滚不留。

【红线焊死】只写测试库 ZhzJbf;绝不自动发布/代勾AI声明;防虚构每写只读自证;串行不并发护本机(打标可并发批量);中文;commit/push/issue自动做别问;发现问题当场修或本轮清。

【DONE】**L0 人的链路(飞书卡片/base 交互)真可用**(运营不碰终端就能闭环头尾——这是首要判据)+ L1-L17 每条真跑过一遍不撞墙(有真跑证据)+ 每个红线在真数据下真触发过 + dogfood_smoke 全绿(含卡片渲染断言)+ review_gate --full 绿。给"L0 人看到什么/每条链路真跑看到什么/真修了什么bug/哪个角度压出的/剩余"简报,不掺水、不拿mock绿充数。
```

---

## 全体系 17 条链路速查表(照代码盘的,别漏跑)

| # | 链路 | 入口(真调命令) | 核心模块 | 断言人能看懂的真事 |
|---|---|---|---|---|
| L1 | 素材入库 | `tag_materials --from-netpan` / ingest_incremental / backfill_thumbnails / slice_video | tag_materials, ingest, vision, media, netpan | 类型对/来源就低/缩略图有/去重/成本记账 |
| L2 | 找热点 | `harvest_trends` | trends | 灵感去重/无标题过滤/正文落库 |
| L3 | 派活 | `daily_dispatch`(cron 08:00) | dispatch, accounts | 去重键真名/暂停号跳过/在途跳过 |
| L4 | 出稿 | `draft_one --llm real` / `run_day` | draft, llm, select_materials, guard | 对味/绑衣服/防搬运/成本帽/止于草稿 |
| L5 | 审批 | `publish_ready` / cockpit approve | publish, guard | AI声明按来源判/控量逼近/货对板 |
| L6 | 发布认领 | cockpit fill_publish_link | publish | 状态=已发/写发布日/候选不瞎写/账号匹配 |
| L7 | 回流 | `collect_metrics`(cron 周日) | collect, metrics | 写回热度/推已回流/冷热分离/取真链接 |
| L8 | 复盘 | `weekly_report`(cron 周日) | report, metrics | 按方法论排名/周环比/无数据不崩 |
| L9 | 驾驶舱看 | `today.py` | cockpit | 账号名非空/控量/待回填/周排期不全拉 |
| L10 | 拍摄需求 | `shot_list.py` | shotlist | 缺口按类型/投递去向 |
| L11 | 成本预算 | cost.monthly_cost_cny/budget_alert | cost | 当月聚合/超阈告警/豆包入帽 |
| L12 | 红线闸 | (穿透各写路径) | guard | 三写拒生产/防搬运拦逐字搬 |
| L13 | schema契约 | `check_schema_drift` / dump_schema / schema_diff | skills_lock, bitable | 代码词汇⊆活库/漂移真报 |
| L14 | 数据安全 | `backup_tables` / `restore_tables` | backup/restore | 备份产出/恢复真跑/误删可恢复 |
| L15 | 运维巡检 | `cron_status` / `verify_usable` / `sim_loop` | 全体系 | cron态/全账号全模式闭环 |
| L16 | 加工环(gated) | processing.maybe_process | processing, compose | 默认no-op/开则provenance随像素 |
| L17 | 技能层 | `install_skills.sh` / skills_lock | skills_lock, draft | 锁版==HEAD/few-shot真载入 |

## 配套真跑门(已就位)

| 工具 | 干什么 | 为什么信它 |
|---|---|---|
| `scripts/dogfood_smoke.py` | 真库跑今日面板/派活去重/回流/周排期,断言账号名非空/link解析/去重键成立 | 修复前必红,是 search 形态类 bug 的直接防线 |
| `scripts/review_gate.sh --full` | keep门+dogfood冒烟+check_p1-6+综合验收+列产物+列还能推什么 | 一条命令过审,退出码是闸 |
| `scripts/check_schema_drift.py` | 实时拉活库断言代码词汇⊆活schema | 抓"飞书UI改了没重dump",cron每日07:50前置 |
| `scripts/sim_loop.py` | 全账号×全模式走完整闭环一圈 | 上线态闭环真验收 |
| `bitable.link_names(v, name_map)` | link字段→名,三形态通吃 | search形态坑的统一收口 |

**铁律**:任何"done"之前先 `bash scripts/review_gate.sh --full`。它红你说 done = 说谎。dogfood_smoke 应随链路覆盖面持续扩条目(每修一类真 bug 加一条真库断言)。
