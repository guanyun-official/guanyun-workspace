"""账号声明(**常驻 Knowledge**):读 `brands/<品牌>/accounts/<号>.md`。

一个号的声明 = frontmatter(JSON:模式们、要什么素材、篇幅规格、缓冲目标)
             + 正文(**画像**:这个号说话是什么调性、什么人设、真实爆款长什么样)

**agent 出稿前读它。** harness 只负责把它读出来 —— **不替它挑,不替它判。**

★2026-07-14 架构审查删掉的东西★

· `weight`(权重)+ `playbook_for` 的 `max(weight)` —— **cadence 轮转的残骸**。
  轮转删掉之后,weight 只剩一个用途:同 content_type 撞上多套 playbook 时,
  **替 agent 挑权重最高的那套**。那是判断 —— 而且它挑的结果
  **决定了防搬运门去捞哪份技能的 few-shot**(挑错 = 门在守错东西)。
  现在:撞了就 **炸**(声明写歧义了该改声明,不该让代码替人猜)。

· `playbooks_of` 里那套"向后兼容合成"(从 content_mix/content_types 拼出 playbook)——
  三个真账号全是显式声明,这条路 **零命中**。

· 默认 `gen_skill = "write-xiaohongshu"` —— **那份技能已经删了**(它在教 agent 发布,直撞红线)。
  一个指向不存在的技能的默认值 = **防搬运门捞不到 few-shot** —— 门瞎了还假装在守。
  现在:没声明就是没有。

· `validate_playbooks` / `problems` —— 唯一调用者 `ar_check.py` 已删。
  声明写坏了 → `Account.error` 有值 → **board 把它直接摆出来**(眼睛的事,不是检查器的事)。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config


def playbooks_of(strategy: dict) -> list[dict]:
    """这个号声明了哪几套模式(playbook)。**只读声明,不合成、不排序。**

    一套 playbook = `{id, content_type, gen_skill, material_needs, material_form, body_len}`
    —— agent 出稿时读它:**这个模式要什么素材(内容×形态)、用哪份技能写、篇幅多少**。
    """
    return strategy.get("playbooks") or []


def gen_skill_of(pb: dict | None) -> str:
    """这套模式用哪份技能写文案。**没声明就是没有,不给默认值。**"""
    return (pb or {}).get("gen_skill") or ""


def resolve_playbook(strategy: dict, playbook_id: str = "", content_type: str = "") -> dict | None:
    """按 id 或 content_type **查出**是哪套模式。**查表,不是挑选。**

    同一个 content_type 撞上多套 playbook → **炸**,不替你猜。
    """
    pbs = playbooks_of(strategy)
    if playbook_id:
        for pb in pbs:
            if pb.get("id") == playbook_id:
                return pb
    if not content_type:
        return None
    hit = [pb for pb in pbs if pb.get("content_type") == content_type]
    if len(hit) > 1:
        raise ValueError(
            f"账号声明写歧义了:内容类型「{content_type}」对应 {len(hit)} 套 playbook "
            f"({[pb.get('id') for pb in hit]})。**代码不替你猜哪套** —— "
            f"去 `brands/*/accounts/*.md` 把它们的 content_type 分开。")
    return hit[0] if hit else None


class Account:
    def __init__(self, name: str, strategy: dict, profile_text: str, error: str | None = None):
        self.name = name
        self.strategy = strategy
        self.profile_text = profile_text     # **画像** —— 出稿前读它(这个号说话是什么调性)
        self.error = error                   # 非 None = 声明坏了 → board 直接摆出来,不静默


    def playbooks(self) -> list[dict]:
        return playbooks_of(self.strategy)


def _accounts_dir(brand: str) -> Path:
    return config.WORKSPACE / "brands" / brand / "accounts"


def _parse(stem: str, raw: str) -> Account:
    strategy, body, error = {}, raw, None
    if raw.lstrip().startswith("---"):
        s = raw.lstrip()
        end = s.find("---", 3)
        if end != -1:
            try:
                strategy = json.loads(s[3:end].strip())
            except json.JSONDecodeError as e:
                error = f"frontmatter JSON 解析失败: {e}"
            body = s[end + 3:].lstrip("\n")
    return Account(strategy.get("account", stem), strategy, body, error)


def load(name: str, brand: str = "巧荷") -> Account | None:
    p = _accounts_dir(brand) / f"{name}.md"
    return _parse(name, p.read_text(encoding="utf-8")) if p.exists() else None


def load_all(brand: str = "巧荷") -> dict[str, Account]:
    d = _accounts_dir(brand)
    if not d.exists():
        return {}
    return {a.name: a for p in d.glob("*.md") if p.name != "README.md"
            for a in [_parse(p.stem, p.read_text(encoding="utf-8"))]}
