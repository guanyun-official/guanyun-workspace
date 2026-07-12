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
| 2 | "自动排产 3 选项开启/暂停/跟随workspace" | 「开启」≡跟随workspace,未区分(3选项只1个真起作用) | 待定:接开启=强制发 or 断舍离砍成2态 | — | — | ADR? |

(下面持续追加)
