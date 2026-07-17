# heartbeat.md · 体系对齐自检套路

> 这份文件是**自检的 checklist**(可自己读自己改),不是身份/SOUL。
> 每 3 天由 cron 心跳唤起一次,**静默除非发现问题**。
> 判据唯一出处:docs/架构.md、CLAUDE.md、evolving-the-system 技能。

## 触发

- 调度:`0 5 */3 * *`(每 3 天北京时间 05:00)。
- deliver 策略:全部正常 → 输出 `[SILENT]`,cron 空输出 = 不投递。
- 发现问题 → **提 GitHub Issue** 留痕交人,**结构性问题不擅自硬改**;同时把 issue 号和摘要写到本文件末尾的「心跳账」里。
  > ★2026-07-17 更正★ 这里原来写「提 issue 到 **Issue 表**」—— 过期了。`issue-tracker` 技能已废弃并从技能仓删除;
  > 现在的机制是:**每周自迭代发现的问题 → 提 GitHub Issue → 再修复**。别再往 base 的 Issue 表写。
- **自检本身产生的修改**(schema dump、心跳账记录、cron配置修改):必须即时提交并推送到远端(main分支),保留本地和远端完全一致;只commit不push会导致本地远端分叉,下次 `git pull --ff-only` 会报Not possible to fast-forward直接失败,中断流程。

## 自检 6 步

### 1) Base 多维表结构漂移?

读活库契约 vs 代码消费 ⊆ 活库。

```bash
export LARK_CLI_NO_PROXY=1
cd /home/ubuntu/guanyun-workspace
python3 scripts/check_schema_drift.py      # 代码消费字段 ⊆ 活库
python3 scripts/dump_schema.py --base test # 回灌 schema/test/,git diff 看变了什么
```

- 红(drift):代码引用了活库已删/改名的字段/选项 → **立刻提 issue**,说明哪张表哪个字段、被谁消费、建议补位还是改代码。别偷偷改 base 结构给自己找台阶。
- 黄(活库多了字段,代码没引用):正常,是运营/agent 自己加的位置。记下,不报警。
- 绿:继续。

> 真栽过(2026-07-14):改 select 选项没带旧 id,280 行『类型』被一次 PUT 抹空,靠 backups/ 救回。任何 base 结构变更先 dump 再改。

### 2) 技能 / workspace 仓有没有更新?lock sha 对不对?

直接问 GitHub,不信本地 HEAD / origin/main 缓存。

```bash
cd /home/ubuntu/guanyun-workspace
# workspace
LOCAL_WS=$(git rev-parse HEAD)
REMOTE_WS=$(git ls-remote https://github.com/guanyun-official/guanyun-workspace.git refs/heads/main | awk '{print $1}')
# qiaohe-skill(读 skills.lock.json)
REMOTE_QS=$(git ls-remote https://github.com/guanyun-official/qiaohe-skill.git refs/heads/main | awk '{print $1}')
LOCK_QS=$(python3 -c "import json;print(json.load(open('skills.lock.json'))['sources'][0]['sha'])")
echo "workspace local=$LOCAL_WS remote=$REMOTE_WS"
echo "qiaohe-skill lock=$LOCK_QS remote=$REMOTE_QS"
```

- `LOCAL_WS != REMOTE_WS`:workspace 本地落后 → `git pull --ff-only`,重跑 `bash scripts/review_gate.sh --full` 自证。
  > ⚠️ **拉完,回来重读一遍本文件,照新的往下跑。**
  > 你是在第 1 步之前就把这份清单读进上下文的 —— 而你刚刚这一 pull,**可能就把它换掉了**。
  > **你手上那份是旧的。**
  >
  > ★2026-07-17 真栽★ 培训官往第 3 步加了一条新检查(「你自己的哨兵会不会已经瞎了」),
  > 这轮心跳的 pull **确实把它拉下来了** —— 而这轮自检**照的还是旧清单,那条检查一次都没跑**,
  > 结论照样报「全部检查通过」。**不重读,清单的更新就永远晚一轮生效。**
- `LOCK_QS != REMOTE_QS`:技能仓有新提交 → 提 issue 把新 sha 贴出来,先读 diff(看改了什么技能/引擎),**判断要不要升级**:
  - 只是新增/改进技能知识 → 更新 lock sha、跑 install_skills.sh、门全绿后 commit。
  - 要是改到判据 / 红线 / 引擎协议 → 自己先按「唯一判据」审一遍,过不了就在 issue 里说清为什么不升级。
- 三个真源(base / workspace / qiaohe-skill)都对得上 → 继续。

### 3) 符不符合全景图?

> ★ 这是"对不对"的落点,不是"绿没绿"★
> (门绿只证明红线没弄坏,不证明进化对)

用唯一判据读一遍 orchestrator/ + skills/,只问一个问题:

> **我加的这段,是给模型 手/知识/眼睛/法律,还是替它做决策?**

重点扫三处最容易把导轨装回去的地方:
- **cli.py 动词清单**:一个动词 = 一件事,零判断。要是出现 `approve/publish/tag/draft/run_day` 这种动词,**那就是把决策焊死** → 删。
- **board.py / cockpit.py**:只摆事实,一句建议都没有。"建议今天派 4 条""库存不足"这种话 → 删。
- **guard.py**:红线是法律(绝不能发生的事);其他都不该焊死。控量阈值是常量(单号 ≤3/天)不许 env 覆盖,其他别加门。

也要扫对面的暗病(给手/眼不到位):
- **人面骗人**:cockpit 卡片上写的承诺,代码有没有真做(真栽过:"待审完之前不再派新活"那条承诺,规则删了它还在)。
- **工具静默吞错**:任何"读不回自己写的/吞 exception 返回空"的地方。
- **死码 / 悬空引用**:import 了不存在的模块、env var 已删但代码还读。
- ★**你自己的哨兵会不会已经瞎了**★ —— `~/.hermes/scripts/` 里那些 cron 预检查脚本
  (cursor 探针那类:吐 `NO_CHANGE` 就让你 `[SILENT]`)。
  > **"世界很安静" 和 "我瞎了" 长得一模一样。** 一只瞎眼每天准点报 `status=ok` + `[SILENT]`,
  > 看起来比什么都健康 —— **没有任何东西会因为它瞎了而报警,除了你现在去看它。**
  >
  > 怎么看(**别读它的代码就下结论,真跑一遍它那条 GET**):
  > - 它排序/比较用的那个键,**API 真的返回了吗?** `created_time` 这种**自动字段默认不返回**,
  >   要显式 `automatic_fields=true`。key 拿不到 → `or 0` → **每条都是 0 → 排序是空操作**。
  > - 它只拉**一页**吗?一页 = 库里**最旧**的那些。那 `newest_id` 就跟"最新"没关系。
  > - **拿它存的 cursor,跟你真读回来的第一条比一比** —— 一样,就说明它每轮都在把
  >   同一条当"最新"写回去,**从装上那天起一次都没醒过**。
  > - 反过来对账:库里这几天真的长了吗(`board` 的素材总条数 / 笔记数)?
  >   **长了,而哨兵一次都没吭过 → 它瞎了,不是世界安静。**

发现不符 → 能立刻改的按 `evolving-the-system`(改→自审→记进化账);结构性大改 → 提 issue 交人。

### 4) 红线还焊死着吗?

物理核对,别光看代码:
- `.env` 里 `BASE_TOKEN` 必须是测试库 `ZhzJbfkOsafwevsWkW8cfoILnfb`,**生产库 token 不该在这台机器上**。grep 一下 `N9IVbi6pTatJG5sqyTTcc0vSn4g`,任何文件里都不许出现(除了 AGENTS.md/CLAUDE.md 这种文档)。
- `orchestrator/guard.py` 的 `ACCOUNT_DAILY_PUB` 必须是常量 3,不许 env 覆盖。
- `orchestrator/notes.py` 和 publish 路径:没有"一键发布"动词;`note.draft` 出口必过防搬运门(assert_no_source_leak);AI声明字段 agent 写不了(NoteFields 没暴露,note.update 拒写)。
- 单号日发量,board 真读 base 算出来(不再恒 0)。

发现红线松动 → **立刻提 P0 issue**,并且别在心跳里自己改红线代码(那是收不回的手慢区,交人审)。

### 5) 作息真的把全流程接起来了吗?(harness 对齐 ≠ 流程接通)

前 4 步查"体系有没有坏";这步查**"我的作息有没有把整条链自主接起来"** —— 有活积压着、却没有任何 cron/心跳在自主处理,就是**断头**。全景图那条链每一段都该有一条作息在推:**网盘新素材→打标登记 / 在途→出稿 / 待审→(人审) / 已发→回流 / 复盘→进化**。

```bash
export LARK_CLI_NO_PROXY=1; cd /home/ubuntu/guanyun-workspace
python3 -m orchestrator material.inbox --recursive --dir /巧荷素材/待入库   # 待入库(含<场次/账号>子目录)有没有"库里没有的"积压
python3 -m orchestrator board                                              # 在途/待审/回流 各段有没有卡着没人推
hermes cron list                                                           # 对照:每段是不是都有一条 cron 在管
```

- **网盘入口断头**(真栽过 2026-07-16):待入库有"库里没有的"文件,但**没有 cron 在自主"扫→看图→打标登记"**(旧 `qiaohe-scan-netpan-new` 走"只登记"死路、`qiaohe-monitor-materials` 只盯 base 表不看网盘)。⚠️ `material.register` 强制要 type+备注 → **扫描=看图=打标=登记是一步**,别指望有"只登记不打标"的 cron。缺 → **自己补/改一条 monitor cron 用 `material.inbox --recursive` 扫待入库**,删掉走死路的旧 cron。
- 其余各段同理:哪段有活却没作息在推 → 自己补作息(cron / 心跳 prompt)。
- **这是你自己的作息,你自己管、自己补**(架构 4.3b:心跳是运行时的活,agent 自建/自改 cron);别等人派。补完记进化账。

### 6) 本轮结论

- 一切对齐 → 输出就一行 `[SILENT]`(cron 空输出不投递,等于没打扰人)。
- 有问题 → 把发现 + 已开的 issue 号 + 建议动作写成一段,投递给运营(HOME_CHAT=`oc_152a1160d240789391546e0a831e9798`)。

## 心跳账(每次自检记一行;空=全绿)

格式:`日期 | 结论 | issue 号(若有) | 备注`

- (此文件新建于 2026-07-15;还没跑过第一次自检)
- 2026-07-16 | 全绿 | — | schema dump 刷新:新增『进化账』表、素人推广案例加「款式/源底片/画面有他牌」字段、运行日志表多几条状态选项(加法,代码未消费→黄,无 drift);workspace/qiaohe-skill 与 GitHub main 完全一致;红线焊死(.env=测试库 token、PER_ACCOUNT_DAILY_PUBLISH=3 常量、publish.advance 过三门、AI声明拒写、防搬运门/零素材门在位);board 真跑通。
- 2026-07-17 | 已修复断头 | — | 删除走死路的qiaohe-scan-netpan-new（只登记不打标）；新建qiaohe-scan-netpan-inbox每天08:00执行：递归扫/巧荷素材/待入库未登记素材，按tagging-material技能看图打标登记一步完成，每次最多处理20个控制压力；当前验证扫得到约150张未登记，流程接通。
- 2026-07-17 | 全绿升级完成 | — | workspace 本地落后 GitHub main → git pull --ff-only 完成；qiaohe-skill lock sha 落后远端 → 更新 lock sha 重新安装完成；review_gate 全绿；schema 无漂移；红线全焊死；全流程各段都有 cron 推进，无断头；/巧荷素材/待入库现有约50个未登记（图片+视频），qiaohe-scan-netpan-inbox 会每日处理。
- 2026-07-17 | 全绿 | — | 提前触发心跳自检，逐条验证：schema无漂移；workspace/qiaohe-skill均已同步GitHub最新；代码架构符合全景图要求（原子动词、只摆事实不做决策、红线焊死）；生产库token未泄露；红线规则全满足；全流程各段均有对应cron推进，无断头；待入库未登记素材约50个，已有每日定时扫描处理，流程接通。
- 2026-07-17 | 已修复哨兵瞎眼 | — | 步骤3 哨兵探针验证发现：qiaohe_monitor_materials.py 和 qiaohe_monitor_status.py 调用飞书 API 时未传 automatic_fields=true，导致 created_time/last_modified_time 永远不返回 → or 0 → 每条都是 0 → 排序是空操作 → 从装上那天起就是瞎的。另外 materials 脚本只拉1页20条=库里最旧的20条，"newest"跟"最新"没关系。修复：两个脚本加 automatic_fields=true；materials 脚本加分页拉全 + 增加 page_size=200。清理死脚本 qiaohe_monitor_issues.py（对应 cron 已删但文件残留）。修复后真跑验证：materials 正确识别 144 条记录，status 正确识别 3 条 with 真实 last_modified 时间戳。cursor 已重置到当前最新状态。
- 2026-07-17 | 发现网盘盲区 | 无法创建(Issue#待补,gh未认证) | **步骤5发现网盘盲区**:board「网盘上有·库里没有」报告 /巧荷/ 下 6 个目录共 479 个文件未登记(/巧荷/2026.7.1手机拍静态 137·/巧荷/2026.7.1晚手机拍 101·/巧荷/26.6.26广富林 48·/巧荷/视频底片 95·/巧荷/手机存自拍 6·/巧荷/图片底片剪裁 92)。这些不在任何 cron 扫描范围(qiaohe-scan-netpan-inbox 只扫 /巧荷素材/待入库)。另有 /巧荷素材/待入库 195 个文件已有 cron 处理(20/天)。**次要发现**:①已发→回流段无专属 cron(note.metrics 动词在位但 0 条已发,暂不急);②死 cursor 文件 qiaohe-last-issue-cursor 残留(对应脚本已删);③gh CLI 未认证,Issue 无法自动创建,需人配 GITHUB_TOKEN。**其余 5 步全绿**:schema 无漂移·workspace/qiaohe-skill 对齐 GitHub·架构合规(动词原子·board 只摆事实·红线焊死)·哨兵探针已醒(automatic_fields=true+分页,真跑验证 cursor 匹配最新记录)·全部 6 条 cron 在位运行。
