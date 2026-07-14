"""补拍单:**把 agent 的判断,渲染成摄影师看得懂的东西**(Observation · 人面)。

★这里不再有"谁该补拍"的判断★

老实现 `shot_needs()` 干的是:遍历每号每类型 → 算 `缺 = 目标 - 已有` → `if 已有 >= 目标: continue`
→ 自动生成拍摄要求(从画像里截一句)→ 自动挑参考图。
**那整套是判断**:库存够不够、该不该催、催几条、怎么跟摄影师说、给他看哪张参考 —— 全是 agent 的事。
(而且它算出来的"缺"只是 `runway_alert_days` 减法,压根不看今天有没有活、这个号是不是要换选题。)

现在:
  · **事实**在 `board`(每号每类型:已拍可用几条 / 它声明的缓冲目标几条 / 库里现有的同类画面长什么样)
  · **判断**在 agent(要不要发这张单、催谁、催几条、怎么说人话、给他看哪张参考)
  · **渲染**在这里(harness 的本分:把它的判断变成摄影师手机上看得懂的一张卡)

## 渲染时焊死的两条(人面纪律,不是判断)

1. **投递去向必须说对**:`待入库` 箱,**直接传,不用管文件名**。
   系统**根本不读文件名**(分类全靠看图)。实测:文件命名成「ootd号·上身图」,系统标出来是「商品图」
   —— 看图判对了,是命名错了。再告诉人"文件名带类型更好认"就是**让他白费功夫**。
2. **别给人看代码路径**。补拍单的读者是**拿相机的人**,不是 agent。
   给他 `skills/writing-ootd-caption/SKILL.md` 让他去读?他在片场,手机上打不开也看不懂。
   参考必须是**能直接看的画面**(真实图链接 + 一句画面描述)。
"""
from __future__ import annotations

from . import config, netpan


def card(items: list[dict]) -> dict:
    """补拍单 → 飞书卡片。items 由 **agent** 给,每项:
        {"账号":.., "类型":.., "缺":N, "拍摄要求":"给人看的人话", "参考":[{"画面":.., "链接":..}]}

    `拍摄要求` 是**它写给摄影师的话** —— harness 不替它编(替它编 = 又一条导轨)。
    这里只保证:每项都带上"拍完往哪丢",且这句话是真的。
    """
    el: list[dict] = []
    for s in items:
        lines = [f"· **{s.get('账号', '?')}**：{s.get('类型', '?')}"
                 + (f" × {s['缺']} 条" if s.get("缺") else "")]
        if s.get("拍摄要求"):
            lines.append(f"   {s['拍摄要求']}")
        for ref in (s.get("参考") or []):
            pic = ref.get("画面", "")
            url = ref.get("链接", "")
            lines.append(f"   照着这个拍：「{pic}」" + (f" → {url}" if url else ""))
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
    if not el:
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": "（这次没有要补拍的）"}})
    el.append({"tag": "note", "elements": [{"tag": "lark_md", "content":
               f"拍完丢网盘 `{netpan.INBOX}` —— **直接传,不用管文件名**（系统看图自动归类）"}]})
    return {"config": {"wide_screen_mode": True},
            "header": {"template": "orange",
                       "title": {"tag": "plain_text", "content": f"📷 补拍单（{config.ENV_NAME}）"}},
            "elements": el}
