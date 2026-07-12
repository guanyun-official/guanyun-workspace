# autoresearch · 压测/打磨整个体系(用户视角自由折腾)

> `/autoresearch` 自主迭代:像**用户**一样自由探索/提需求/跑链路 → 发现 gap → 及时修(带回归锁)→ keep 门全程绿 → 直到体系经得起折腾。
> 设计取舍提 **ADR**,需求缺口提 **issue**。**防虚构:每步只读/真跑自证。**

## 配置
- **Goal**:整个体系经得起用户自由折腾——各种使用场景/链路/临时需求都能承接;找修所有类 gap,用户场景端到端实测。
- **Scope**:orchestrator/ scripts/ lib/ local-skills/ brands/ + base 契约 + 用户使用场景。
- **Metric**:gaps 找到+修复数(↑)。
- **Verify/Guard**:`python3 -m unittest discover -s tests`(OK)+ `ar_check`=100 全程不回归;每修带回归锁。
- **Baseline(iter#0)**:138 单测 PASS / ar_check SCORE=100。✅

## 为什么这类问题之前没发现(探测框架)
单测/ar_check 验的是**代码内部逻辑**(draft 出稿没、dispatch 按 md 派没、闸拦生产没),**没验"用户能在飞书点/能想到的东西,代码认不认"**这层契约。所以本轮换**用户视角**探测:
1. **base 声明未消费**:每个 base 字段/select/状态列,代码 honor 吗?(如已修的「自动排产」)
2. **状态机断点**:Note 每个状态流转,有代码接吗?还是只是显示?
3. **md 字段未生效**:账号 md 每个 strategy 字段,消费了吗?
4. **用户链路端到端**:加号/加模式、灵感转化、素材摄入、官号衣服KB、审→发→回流,真跑通吗?
5. **红线真硬吗**:控量/AI声明/防搬运/只测试库,能不能被绕?

## 迭代日志(gap = 发现→修→锁)
| # | 场景/探测(用户视角) | 发现的 gap | 修法 | 回归锁 | keep门 | ADR/issue |
|---|---|---|---|---|:--:|---|
| 1 | "我想暂停一个号"(base 点自动排产=暂停) | 「自动排产」列没被消费,dispatch 只看 md cadence | dispatch 读 base 自动排产,暂停跳过 | test_paused_account_skipped | ✅ | — |
| 2 | "自动排产 3 选项开启/暂停/跟随workspace" | 「开启」≡跟随workspace,未区分 | 三态语义定清+接「开启=强制派覆盖md」;抽纯函数 _should_dispatch | test_sched_decision_three_states | ✅ | ADR-0003 |
| 3 | "红线:防搬运出口闸真拦吗"(信红线) | no_source_leak/skill_gate 出稿路径**零调用**,红线是摆设 | guard.assert_no_source_leak 接进 draft real 路径 | NoSourceLeakGate | ✅ | — |
| 4 | "红线:控量≤3篇/天真 enforce 吗" | assert_publish_quota 全库**零调用** | 发布时约束、系统不自动发→暂缓,待 dedicated-agent 发布步接 | — | — | issue(待建) |

## 静态审计 backlog(子agent 全库扫,13 个"声明未消费";Note 状态机 9 态 100% 有消费无断点)
按用户可见度排:
- [ ] **runway_alert_days**(账号md):设了**没催拍告警**——planner/dispatch 零引用。用户可见 gap,待接催拍。
- [ ] **投手**(笔记表+账号表):没路由到发布(发布步/dedicated-agent 才用)。
- [ ] **生成参数 / 拍摄人 / 拍摄要求**(素材表):特性预留未实现(TARGET_ARCHITECTURE_INVENTORY 已追踪)。
- [ ] **cadence.pattern**(账号md):未分支(drip 等只是标签)。
> 结论印证:单测照不到"base/md 声明了但代码没消费"这类哑控制——只有对照用户可设 vs 代码实读才现形。审计脚本建议进 check_p*.sh。

## 观察
- base 数据实时驱动已验证:官号「自动排产」被改成跟随workspace 后,dispatch 立即开始派它(控制线真通了)。

## 迭代日志(续 · 动态用户场景)
| # | 场景/探测 | 发现 | 修法 | 回归锁 | keep门 |
|---|---|---|---|---|:--:|
| 5 | "加模式=改md不改schema 真吗" | 现4模式 content_type 全在 base 内容类型表;真Note内容类型/账号/3素材 link 全齐 | 无 gap(次要:加"全新"content_type 需 base 加行) | — | ✅ |
| 6 | "AI声明门真enforce吗" | assert_ai_declared 生产**零调用**(同控量门,休眠发布闸) | 发布/状态推进步是人/dedicated-agent→ issue待接 | — | — |
| 7 | "灵感→出稿链路" | 灵感库2条待转化,但**无 trend_imitate 号**消费→灵感孤儿 | config 缺口(需配 trend_imitate 号) | — | — |
| 8 | "素材池/官号货对板/回流鲁棒" | 官号要的**形象图 0 条**(官号押后,minor);clothes绑定✓;回流对0已发no-op | 无 code gap | — | ✅ |
| 9 | **"派活→出稿,一条内容一行吗"** | **create_draft_note 永远新建**→派活『待出文案』成孤儿、变两行;手动重复出稿堆重复 | 出稿找在途 Note→**推进**(待出文案→草稿待发)/刷新,无则新建 | DraftAdvancesInflightNote | ✅ |

| 10 | "红线完整性+唯一源双向+备份" | AI声明红线完整(无代码代写);base↔md账号双向一致;backup可跑 | 无 gap(红线扎实) | — | ✅ |
| 11 | **meta:"为什么没早发现"→硬化验收** | ar_check 唯一源只查 base⊆md 单向、不含内容类型 | 唯一源检查改**双向+覆盖内容类型**,加号/加模式漂移进keep门 | ar_check唯一源 | ✅ |

| 12 | **"设了 runway_alert_days 却没催拍"**(审计gap) | 该字段哑——planner/dispatch 零引用 | dispatch.runway_alerts:可用素材÷日发量<阈值→催拍;接进 daily_dispatch | test_runway_alert_when_materials_low | ✅ |

| 13 | "回流/切片/坏md韧性" | 都 sound(回流失败不阻断、切片CLI齐、坏md隔离不炸) | 无 gap | — | ✅ |
| 14 | **"回流后状态机走到已回流吗"** | **「已回流」死状态**:回流写点赞/收藏但不推进 已发→已回流→复盘读不到数据 | 回流采到数据→推进已发→已回流;已回流每周刷新;**真跑自证**(注入真URL→采到点赞49/状态已回流→清理) | test_writes_back_and_advances/loopedback_refreshed | ✅ |

| 15 | **"复盘均赞被谁算进去了"** | aggregate_by_playbook 不按状态过滤→草稿待发(有playbook、0赞)也计入→**复盘均赞被未发布草稿稀释** | aggregate 只聚合 已发/已回流(有真发布数据) | test_metrics(草稿不计) | ✅ |

| 16 | **"暂停号后综合验收还准吗"** | verify_usable 断言派活==全组合,自动排产暂停号被跳→暂停即假报未可用 | ④改子集(暂停跳过是功能);真跑证复原 | verify_usable | ✅ |
| 17 | **verify_usable 跑出真数据缺口** | 6素材全ootd独占,图文号1/2/官号 0可用→综合验收红(打脸文档"全绿");上身图 mis-tag违画像"共用同批" | 上身图对齐画像→共用(图文号1/2各3条);verify_usable ①也paused-aware | — | 🔶 官号仍红(缺形象图+衣服KB,押后) |

| 18 | **"出事(cron挂/verify红/登录过期)会告警吗"** | alerts.send 只在check_p5自检调,失败路径**零调用**;交接说"进程挂推群"是空头支票 | 归类**运营阶段待接**(同休眠发布闸;且"先不进群"下不宜现接live告警) | — | ⏸运营阶段 |

## 收敛观察(18轮后)
可修的**代码** gap 基本挖尽,keep门全程绿。剩两类,都非现在代码bug:
- **运营阶段待接线**(等 dedicated-agent + 进群启用):发布闸 assert_publish_quota/assert_ai_declared、失败告警 alerts.send、投手路由。
- **数据/config**(需用户/运营决策):官号缺形象图+真衣服KB(押后)、灵感库需配 trend_imitate 号、cadence.pattern/生成参数等特性预留。
> 治本已落:①用户视角探测法(base/md声明 vs 代码实读)②验收硬化(唯一源双向、verify/ar paused-aware)③状态机闭环(待出文案→草稿待发→已发→已回流全推进,真跑自证)。

| 19 | "关键词库/目标客户被消费吗" | 32关键词+17客户**无代码读=哑数据**(没喂回生成/选题);content-addressing #38 sound | 特性预留(可将来喂选题/SEO/targeting) | — | ⏸ |

## 收官(19轮 · autoresearch 收敛)
**代码 gap 挖尽**。修了 11 个真 gap(自动排产消费/开启语义/防搬运闸/状态机推进×2/唯一源双向/催拍/回流闭环/复盘聚合/验收paused-aware×2),全带回归锁、keep门全程绿、效果闭环真跑自证。最近几轮只落进两类既知桶(运营阶段待接线 / 声明未消费数据),非新bug=收敛信号。要再推进须**换 frontier**:启用运营阶段(发布/告警/dedicated-agent+进群)或决策预留数据。

| 20 | "iter9状态机推进真库验过吗" | 只单测过 | 真跑:注入待出文案→stub出稿→推进同行草稿待发+挂素材+无重复,清理 | (真跑自证) | ✅ |
| 21 | **"pipeline 记运行日志吗"** | log_run 定义但**全库零调用**→运行日志表不更新→周复盘读它=空、成本追踪没数据 | log_run 接进 draft_one/daily_dispatch/collect_metrics 的 run 边界;真跑验(9→10条含出稿) | (真跑自证) | ✅ |

| 22 | "备份能恢复吗/ingest扫得动吗" | **备份只dump无restore工具**("误删可恢复"=手动、link要按名重解析);ingest scan sound;预算帽真传claude -p | flag备份restore(feature待建);ingest/预算sound | — | 🔶 restore待建 |
| 23 | "还有休眠闸/死代码吗" | copy_quota_left+PER_RUN_COPY_LIMIT **只互引无调用无测试**=重引擎遗留死代码;Record适配器sound | 断舍离删死代码 | (无引用) | ✅ |

| 25 | **补齐"误删可恢复"的 restore 半边** | 备份只dump无restore工具 | 建 scripts/restore_tables.py:读备份→link按名重解析(修主字段坑)→dry-run默认/--write只测试库/写失败降级丢link保底;round-trip真跑自证(造→备份→删→恢复→找回→清理)+3单测 | test_restore | ✅ |

| 26 | **接告警(用户:发关联bot私聊)** | alerts.send失败路径零调用(iter18flag);home核实=p2p私聊 | verify_usable加--alert红了发私聊;collect登录过期告警;cron同步;真发自检成功 | (真发自证) | ✅ |

| 27a | **收尾:dump_schema URL盲区(不押后)** | lark-cli把URL归一成type=text→漂移检测盲区 | 靠 style.type=url 还原;重dump 3个URL字段现记url;keep门绿 | (重dump自证) | ✅ |
| 27b | **收尾:关键词库哑数据(不押后)** | 32关键词没喂回生成 | load_keywords接进出稿prompt(软注入/调性优先/real才注入不破离线);真跑验ootd正文纯净、标签自然带新中式 | KeywordInjection | ✅ |

## 待提 issue(休眠闸/config 缺口)
- assert_publish_quota(控量门)+ assert_ai_declared(AI声明门)生产零调用——发布/状态推进步(人/dedicated-agent)建时必接。
- 灵感库无 trend_imitate 号消费;官号缺形象图素材(押后)。

- ar_check 部分痛点走网络→偶发抖动(13↔14/14),重跑即复;非确定但非 bug。

(下面持续追加)
