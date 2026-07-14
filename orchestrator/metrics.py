"""取数工具集 —— 两只手 + 几个小工具。**这里没有"回流采集"这件事。**

  · `fetch_source(url)`  抓一条**爆款**的标题+正文(非登录 SSR,零凭证)→ 给 trends 看结构、供出稿参考
  · `by_playbook(notes)` 把**已发/已回流**的笔记按方法论聚合成事实(条数/总赞/均赞/…)→ 给周报摆数
  · `expand_share_link` / `_cn_num` / `_num`  短链展开、中文计数归一的小工具

★**回流的『抓』不在这里** —— 那是 agent 的操作★
  它有 `xhs-extract-master` / `xhs-collector` 两个采集技能,用哪个、抓到的数信不信,是它的判断。
  harness 只给它**把数写回世界的手**(`note.metrics` → `notes.write_metrics`);不替它去抓,
  也不"喂回排产"(排产/dispatch 早拆了,见 docs/架构.md 4.1)。

★**没有 stub、没有 mode**★ —— 全是真 subprocess(只读,零封号)。
  老实现有个 `GY_METRICS_MODE=stub` 让离线单测不触网;单测已全删,那个开关也删了(config.py / 架构.md 4.4)。
  死规矩:**不搞 mock、不搞 stub**(参 netpan.py 的写法)。抓不到就如实返回空,绝不假装成功。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from . import bitable, config
from .bitable import NoteFields as NF, NoteStatus as NS

def _cn_num(v) -> int | None:
    """小红书中文计数 → int:'8.5万'→85000,'1.2亿'→120000000,'815'→815,'-'/''→None。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*(万|亿)?$", s)
    if not m:
        return None
    n = float(m.group(1)) * {"万": 1e4, "亿": 1e8}.get(m.group(2), 1)
    return int(round(n))


def expand_share_link(url: str) -> str:
    """小红书**分享短链** `xhslink.com/...` → 展开成带 `xsec_token` 的真链接。

    ★为什么必须有(2026-07-14 真跑撞到)★
    **人从小红书"分享"出来的就是短链** —— 运营回填『发布链接』时,粘的就是它。
    而采集器的 `note` 原子**必须带 `xsec_token`** 才拿得到数据(踩坑账第二节第 2 条),
    短链上**没有 token**。

    结果:运营老老实实照卡片填了链接,**回流永远抓不到数** —— 而且不报错,只是数字一直是 0。
    然后周报会说"链接已经填了,却还是零赞,不是你的问题" —— **话说得体贴,可根本就采不到。**

    不是短链就原样返回(幂等)。展不开就返回原样(调用方会如实报"没采到")。
    """
    if "xhslink.com" not in url:
        return url
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return r.geturl() or url
    except Exception:  # noqa: BLE001  展不开 → 原样返回,调用方如实报"没采到"(绝不假装成功)
        return url


def _extract_note(url: str) -> dict:
    """抓一条笔记的原始数据(**只给 `fetch_source` 用** —— 出稿要看爆款的结构)。

    ⚠️ **回流的『抓』不在这里** —— 那是 agent 的操作:它有 `xhs-extract-master` /
    `xhs-collector` 两个技能,**用哪个、抓到的数信不信,是它的判断**(它已经证明它会判:
    真跑时它拒绝相信"搜索卡 7441 赞 / 详情页 4 赞"那组自相矛盾的数)。
    harness 只给它**把数写回世界的手**(`note.metrics`)。

    我差点在这里长出第二份采集器(归一键名、决定先试哪条路)—— **那就是"方法有两份真源"**。
    """
    url = expand_share_link(url)                     # 分享短链 → 带 xsec_token 的真链接
    xhs = config.WORKSPACE / "skills" / "xhs-extract-master" / "scripts" / "xhs"
    r = subprocess.run(["python3", str(xhs), "note", "--url", url],   # 技能要 --url(位置参数返空)
                       capture_output=True, text=True, timeout=90)
    i = r.stdout.find("{")
    return json.loads(r.stdout[i:]) if i >= 0 else {}


def _note_source(d: dict) -> dict:
    """note 原始 dict → {标题, 文案}(**纯函数**,形态归一集中一处)。
    实测形态:`xhs note --url <带xsec_token的URL>` → {"note": {"title":…, "desc": 真正文, …}, …};
    也吃顶层壳(不同原子/版本的两种返回)。"""
    n = d.get("note") or d
    return {"标题": (n.get("title") or "").strip(),
            "文案": (n.get("desc") or "").strip()}


def fetch_source(url: str) -> dict:
    """抓一条爆款的**标题 + 正文**(非登录,零凭证)→ {标题, 文案};失败返 {}(不阻断)。

    **我在这件事上错了三次,记在这**(2026-07-14):
      我一路对外宣称"非登录抓不到正文,详情页只吐 452 字节空壳",据此把『文案』当成拿不到的东西,
      还改了红线设计去绕开它。真相是:
        ① 我调 note 原子时**没带 xsec_token**(feed 明明给了 `xsecToken`,我没用);
        ② 拿到返回后**读错了键** —— 正文在 `note.desc`,我读的顶层 `desc`,自然是空。
        ③ 而 `metrics._extract_note` **本来就在这个文件里跑通了这个原子**(采互动数据用的),
           我却没去看一眼。
      真跑实证:带 token 抓真热点 →『30S搞定！有手就会的新中式发型』正文 186 字、赞 10万+。
      **不真读一遍返回就下结论 —— 同一个病,这是第三次。**
    """
    if not url:
        return {}
    try:
        return _note_source(_extract_note(url))
    except Exception as e:  # noqa: BLE001
        print(f"[抓正文降级] {e}", file=sys.stderr)
        return {}


def by_playbook(notes: list[dict]) -> dict:
    """按方法论聚合**事实**:{方法论: {条数, 总赞, 均赞, 总藏, 总评}}。只算已发/已回流。

    ★删掉了 近30天/本周/上周/周环比/ranked★(2026-07-14 架构审查)
    那几个窗口**只为一句结论服务**:「👉 本周最有效:『X』—— 可加权/多产这类」。
    而"哪套方法论更有效、要不要多产"**是模型的判断**(全景图 AGENT 框里写着「周报该怎么说」)。
    harness 摆数,agent 说话。
    """
    # ★"没抓到" ≠ "真的 0"★(2026-07-15 数字生命抓到)
    # 老实现 `d["总藏"] += _num(f.get(NF.COLLECTED))` —— 收藏没抓到时字段是 None,`_num(None)=0`
    # → **一堆假 0 累进总数**。下一个读周报的 agent 会以为"这套方法论收藏就是 0",据此判断。
    # `note.metrics` 抓不到就不写(那只手是对的);到了这里,**没写的就该算"没抓到",不是 0**。
    def _got(v):     # 抓到了吗:字段有值(含真 0)才算抓到;None / 空串 = 没抓到
        return v is not None and not (isinstance(v, str) and not v.strip())

    agg: dict[str, dict] = {}
    for f in notes:
        if bitable.text(f.get(NF.STATUS)) not in (NS.PUBLISHED, NS.LOOPED_BACK):
            continue                  # 只聚合已发/已回流(草稿 0 赞会稀释均值)
        pb = bitable.text(f.get(NF.PLAYBOOK)).strip() or "(没填方法论)"
        d = agg.setdefault(pb, {"条数": 0, "总赞": 0, "总藏": 0, "总评": 0,
                                "赞没抓到": 0, "藏没抓到": 0, "评没抓到": 0})
        d["条数"] += 1
        for name, field in (("赞", NF.LIKED), ("藏", NF.COLLECTED), ("评", NF.COMMENTS)):
            v = f.get(field)
            if _got(v):
                d[f"总{name}"] += _num(v)
            else:
                d[f"{name}没抓到"] += 1
    for d in agg.values():
        got = d["条数"] - d["赞没抓到"]
        d["均赞"] = round(d["总赞"] / got, 1) if got else "(赞都还没采回)"
    return agg


def _num(v) -> int:
    """健壮取数:int/float/字符串数字/中文计数('8.5万')都吃(飞书数值字段回读常为字符串)。非数→0。"""
    n = _cn_num(v)
    return n if n is not None else 0
