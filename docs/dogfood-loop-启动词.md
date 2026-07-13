# dogfood 驱动 loop 启动词(paste-ready)

> **为什么要它**:过去多轮"pytest 全绿 / ar_check 100 / 三视角无 blocking"照样交付不可用的系统——因为**绿门测的是 mock 和 stub(我自己写的假数据),不是真飞书**。真相在"人真用"和"mock 同意"之间的缝里:例如飞书 `records/search` 返回 link 字段是 `{link_record_ids:[...]}`(无 text),而 mock 用的是 `get_record` 的 `[{text,record_ids}]` 形态——mock 比真数据"干净",于是"账号名读空、派活不去重、素材不挂"的 bug 过了每一轮绿门,直到**当运营真跑 30 秒**才暴露。
>
> 结论:**mock 只配做单测隔离;交付判定必须看 dogfood 真跑。** 下面这条 loop 把这个纪律焊死。

---

## 直接把下面整段发给 `/loop`

```
/loop dogfood 驱动把巧荷内容工厂跑成真可用:每步对测试库真跑、不同角度真压测,用出来的问题才算问题,发现即修,直到运营能端到端跑完一天不撞墙。别信绿门,信真跑。

【核心纪律(违反=这轮白干)】
1. 别信绿门:pytest/ar_check 绿只证明"代码和 mock 自洽",不证明能用。**交付判定看 `python3 scripts/dogfood_smoke.py` + `bash scripts/review_gate.sh --full` 真库跑绿**,不看单测绿。
2. 别搞 mock 假绿:单测 mock 必须用**真飞书 API 的真形态**(search=`{link_record_ids}`、get=`[{text,record_ids}]`、url=`{link,text}`、date=毫秒 int)。拿不准就先真跑一条 `feishu_io.search_records/get_record` 打印真形态,再写 fixture。发现某处 mock 形态和真库不符=当场改 fixture 并加真形态回归锁。
3. 每个写操作后只读自证(防虚构):写完用 search/get 真读回来确认,不信叙述里的成功。

【每轮:当运营把这条链真跑一遍(每步真过,不是设计过)】
① schema 漂移前置:`python3 scripts/check_schema_drift.py` 真库对齐(红=先修词汇/快照)。
② 看今日面板:`python3 -c "from orchestrator import cockpit; print(cockpit.today_panel('巧荷'))"` —— 眼睛看账号名/模式/控量/待回填是不是**人能看懂的真值**(不是空、不是 id、不是一坨)。
③ 派活:`python3 -m scripts.daily_dispatch`(干跑看清单)→ 看去重键是不是真名、在途是否真跳过。
④ 出稿:`python3 -m scripts.draft_one --account <号> --llm real`(真花钱出一条)→ 看文案对味/绑定衣服/成本记账/止于草稿待发不越审。蹭爆款走 `--source-text` 真喂正文,**逐字搬要真被防搬运门拦**。
⑤ 审+发:走 publish 审批 + `fill_publish_link` 认领链接 → 真读回确认状态=已发、实际发布日已写、AI声明按素材来源真判(AI合成的必拦人勾)。
⑥ 回流:`harvestable_notes` + collect(stub 或真采)→ 真读回确认写回点赞/收藏、状态推进已回流。
⑦ 周看板:`weekly_schedule` / 复盘 → 真值可读。
⑧ 收尾:`bash scripts/review_gate.sh --full`(含 dogfood 冒烟+check_p+综合验收)。

【不同角度真压测(每轮至少挑 2-3 个真跑,不是想象)】
- 新号冷启:一个素材/画像稀薄的号,出稿会不会崩/编造/空包。
- 爆款蹭稿:真传一段爆款正文,防搬运门真拦逐字搬、真放行改写。
- 超量红线:给某号真堆到 >单号日上限,控量真标🚦逼近。
- AI 素材:挂一条 AI生成素材,AI声明真判"必须勾"、机器绝不代勾。
- 规模:真造/模拟大量已发,确认 today_panel/collect 真不整拉笔记表(探针计 list_records 次数=0 for 笔记表)。
- 并发写:两个写进程真抢,flock 真挡(LockBusy)。
- 坏数据边界:空账号/无素材/坏链接/字段缺失/超长——真跑不崩、降级可读,不是抛栈。
- 红线穿透:三写路径真指向生产库,guard 真拒(物理到不了)。

【发现即修(不拖泥带水)】
简单的当场直接修;复杂的诊断清楚→放 issue→本轮就修,不留悬空。每修一个真 bug 加一条**真形态回归锁**(单测用真形态)+ 让 dogfood_smoke 覆盖它(下次真跑就拦)。

【每轮 VERIFY】
`bash scripts/review_gate.sh --full` 全绿(dogfood 冒烟 + keep门 + check_p1-6 + verify_usable)。红=回滚不留。真库真跑绿才算这轮成立。

【红线焊死】只写测试库 ZhzJbf;绝不自动发布/绝不代勾 AI 声明;防虚构每写只读自证;串行不并发护本机(打标可并发批量);中文;commit/push/issue 自动做别问;发现问题当场修或提 issue 本轮清。

【DONE】运营能端到端真跑一天不撞墙(①→⑧ 全真过)+ dogfood_smoke 全绿 + 上面每个红线在真数据下真触发过一次(有真跑证据)+ review_gate --full 绿。给"每步真跑看到什么/真修了什么 bug/哪个角度压出的/剩余"简报,不掺水、不拿 mock 绿充数。
```

---

## 配套工具(这条 loop 用到的、已就位的真跑门)

| 工具 | 干什么 | 为什么信它 |
|---|---|---|
| `scripts/dogfood_smoke.py` | 真库跑今日面板/派活去重/回流/周排期,断言账号名非空、link 解析、去重键成立 | 修复前必红(账号空),是 search 形态类 bug 的直接防线 |
| `scripts/review_gate.sh --full` | keep门 + dogfood冒烟 + check_p1-6 + 综合验收 + 列产物 + 列还能推什么 | 一条命令过审,退出码是闸;④告诉你还能推什么(反莫名停) |
| `scripts/check_schema_drift.py` | 实时拉活库 field-list,断言代码词汇 ⊆ 活 schema | 抓"飞书 UI 改了没重 dump",cron 每日 07:50 前置 |
| `orchestrator/bitable.link_names(v, id_name)` | link 字段→显示名,三形态通吃(search 回 id 靠 name_map 还原) | search 形态坑的统一收口,别再各写各的 |

**铁律**:任何"done"之前,先 `bash scripts/review_gate.sh --full`。绿=真跑过;它红你说 done=说谎。
