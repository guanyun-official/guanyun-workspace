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

## 待提 issue(休眠闸/config 缺口)
- assert_publish_quota(控量门)+ assert_ai_declared(AI声明门)生产零调用——发布/状态推进步(人/dedicated-agent)建时必接。
- 灵感库无 trend_imitate 号消费;官号缺形象图素材(押后)。

(下面持续追加)
