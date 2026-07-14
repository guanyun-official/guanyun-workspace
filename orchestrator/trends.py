"""找热点 → 灵感库(系统化热点采集的『落库』一环)。

**『找』是 agent 的事**(它用 `xhs-extract-master` / `xhs-collector` 技能去抓、自己判断哪条值得学);
**『落』由本函数收口** —— 按标题去重、URL 字段正确包装、只写测试库。
落库后 `board` 会把未转化的灵感摆给它看,它自己决定拿哪条来出稿(闭环靠 `mark_converted` 回填)。
"""
from __future__ import annotations

from . import bitable, config, feishu_io, guard
from .bitable import InspirationFields as IF


def mark_converted(idea_id: str, note_id: str) -> None:
    """灵感转化成笔记了 → 回填灵感库,闭合环(灵感 → 出稿 → 回填,不重复捞同一条)。
    『转化为笔记』是 **link 字段**,写的是 record_id **列表**,不是字符串 —— 真跑才暴露的坑,codify 防复发。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    feishu_io.update_record(IF.TABLE, idea_id, {IF.CONVERTED: [note_id]})


def harvest_trends(items: list[dict], brand: str = "巧荷", write: bool = False) -> dict:
    """把找到的热点/爆款灵感落灵感库。items=[{标题, **文案**, 可借鉴?, 源链接?}]。
    按标题去重(已在库跳过);write=False 干跑预览、True 落库(过 base 红线闸)。
    返回 {新增, 去重跳过, **无正文**}。

    **『文案』(原帖正文)是防搬运红线的命根子**(2026-07-14 全体系对齐审查抓到的):
    `guard.assert_no_source_leak` 比对的就是它——出稿逐字搬了原帖 ≥10 连续实义字符就拒。
    可这个函数原来的输入契约是 `[{标题, 可借鉴?, 源链接?}]`——**根本没有正文这一项**,
    "找热点"从设计上就没打算存原帖正文。于是真实数据里**灵感库 5 条『文案』全空**,
    防搬运门每次都走"源过短→提前放行"分支 → **整段逐字搬也能过**。
    门和喂门的那条链路,从来没对齐过。
    现在:接收并落『文案』;**落了没有正文的灵感,明确警告**——因为从它出的稿会被红线直接拒。
    """
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    # ★不认识的键 → **炸,别静默吞**★(2026-07-14 数字生命上班第一天撞到)
    #
    # CLI 的 --help 曾经写着 `{"标题","文案","链接","优点"}`,而这里读的是 `源链接`/`可借鉴`。
    # 数字生命**照着 help 传**,于是「可借鉴」和「爆款源」**被无声丢弃** —— 不报错、不警告,
    # 行还是建出来了,**看起来完全成功**。它读回来才发现:灵感的全部价值(可借鉴的打法)
    # 和溯源链接,一个字都没进去。**3 行残数据就这么落进了真库。**
    #
    # "静默丢弃未知键"写的时候觉得宽容,落实下来就是**往真库灌残数据,而且没有任何人会发现**。
    # (它自己的话:"响的能自己发现,静默的会把脏数据写进真库 —— 静默那个毒得多。")
    KEYS = {"标题", "文案", "可借鉴", "源链接"}
    for it in items:
        bad = set(it) - KEYS
        if bad:
            raise ValueError(
                f"灵感的键写错了:{sorted(bad)} 不认识。\n"
                f"合法的键只有这四个:标题(必填)· 文案(原帖正文,学结构用)· "
                f"可借鉴(它凭什么火)· 源链接(溯源)。\n"
                f"**不静默丢** —— 丢了你不会知道,而残数据会留在真库里。")
    existing = {bitable.text(r["fields"].get(IF.TITLE)).strip()
                for r in feishu_io.list_records(IF.TABLE)}
    new: list[str] = []
    dup: list[str] = []
    no_body: list[str] = []          # 落了但没正文的 → 从它出的稿会被防搬运红线直接拒
    for it in items:
        title = (it.get("标题") or "").strip()
        if not title:
            continue
        if title in existing:
            dup.append(title)
            continue
        body = (it.get("文案") or "").strip()      # **原帖正文 = 学结构的情报本身**
        if not body and it.get("源链接"):
            # 有链接却没正文 → **自己去抓**(非登录,零凭证,已真跑验证)。
            # 以前这里什么都不做,只把标题记进"无正文",然后我对外说"非登录抓不到" —— **那是错的**:
            # 我调 note 原子时没带 xsec_token、又读错了键(正文在 note.desc,我读的顶层 desc)。
            # 带上 token 读 note.desc,正文就在那儿(真抓:186 字 / 311 字)。
            from . import metrics
            body = (metrics.fetch_source(it["源链接"]).get("文案") or "").strip()
        row: dict = {IF.TITLE: title}
        if body:
            row[IF.BODY] = body
        else:
            no_body.append(title)
        if it.get("可借鉴"):
            row[IF.MERITS] = it["可借鉴"]
        if it.get("源链接"):
            row[IF.LINK] = bitable.url_value(it["源链接"])   # 链接是 URL 字段,须 {link,text} 包
        if write:
            feishu_io.create_record(IF.TABLE, row)
        new.append(title)
        existing.add(title)
    # **干跑和实跑,返回值必须看得出区别**(2026-07-14 数字生命撞到):
    # 老实现两次返回一模一样,一个字都不差 —— **光看返回值分不出它到底写没写**。
    # 干跑存在的**唯一意义**就是"告诉我实跑会发生什么";它和实跑长得一样,人就只能去猜。
    return {"写库了": write, "新增": new, "去重跳过": dup, "无正文": no_body,
            "自证": "python3 -m orchestrator board  → 看『灵感库(未转化的爆款)』" if write
                    else "(干跑,没写库。加 --write 才真落)"}


def update_idea(idea_id: str, fields: dict) -> None:
    """改灵感库的一行(补『可借鉴』『源链接』『文案』等)。

    **为什么需要它**(2026-07-14 数字生命上班第一天):`idea.add` 的 help 和代码对不上,
    它照着 help 传,『可借鉴』和『爆款源』被静默吞掉 → 3 行残数据落进真库。
    而 CLI 里**只有 add / converted,没有 update** → **它想修都修不了**(add 按标题去重,重跑只会跳过)。
    它按纪律没有绕过去写脚本,就把残数据留在库里等我给一只手。**这就是那只手。**
    """
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # 红线:只写测试库
    # ★两个 idea 动词,键名必须一样★(2026-07-14 数字生命第二天撞到)
    # 老实现:`idea.add` 收 {标题,文案,可借鉴,源链接},`idea.update` 收 {标题,文案,优点,链接}
    # —— **两个动词的键名正好相反**,而 help 给的示例又是 add 那套。
    # 它照着 help 写 `--set 可借鉴=...`,当场被拒:"灵感库没有这些字段:['可借鉴','源链接']"。
    # (好在这次**它响了、还说清了合法键**,它 30 秒就绕过去了,没写进库 —— 门是对的,**示例在骗人**。)
    # 现在:**统一用 add 那套输入契约**(标题/文案/可借鉴/源链接),内部再映射到 base 的字段名。
    IN2FIELD = {"标题": IF.TITLE, "文案": IF.BODY, "可借鉴": IF.MERITS, "源链接": IF.LINK}
    bad = set(fields) - set(IN2FIELD)
    if bad:
        raise ValueError(
            f"灵感的键写错了:{sorted(bad)} 不认识。\n"
            f"合法的键只有这四个(**和 idea.add 完全一样**):"
            f"标题 · 文案(原帖正文)· 可借鉴(它凭什么火)· 源链接(溯源)")
    patch = {}
    for k, v in fields.items():
        fld = IN2FIELD[k]
        patch[fld] = bitable.url_value(v) if fld == IF.LINK and isinstance(v, str) else v
    feishu_io.update_record(IF.TABLE, idea_id, patch)


