"""Account 定义加载器(候选C:画像+strategy 两文件塌成一个 Account,一处知道存储格式)。

一个账号 = 一个 `brands/{brand}/accounts/{号}.md`:
  ---
  {JSON frontmatter = strategy: cadence/material_needs/autonomy/...}
  ---
  正文 = 画像 prose(发什么/怎么写,喂生成)

消费方各取所需(seam 只此一处):
  planner → load(号).strategy    (结构化,排产)
  llm     → load(号).profile_text(自然语言,注入生成)
用 JSON frontmatter(非 YAML)避免新依赖;stdlib 即可解析。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config


def playbooks_of(strategy: dict) -> list[dict]:
    """账号的发布方法论(playbook)列表——纯函数,吃 strategy dict(planner 拿到的就是 dict)。

    一个 playbook = 一套完整发布配方:内容切面 + 节奏权重 + 素材需求 + (可选)标题/正文公式 +
    指向自己的素材视图 `view` 键(每套方法论一套软链,见 docs/架构演进-素材视图与方法论.md · G4)。

    显式 `strategy.playbooks` 优先;否则从 content_types/content_mix/material_needs **向后兼容合成**
    (每个内容类型 = 一个 playbook:id=content_type、weight 取 content_mix、material_needs 取该类型、
    view=id)。于是"加一套方法论"=写一条 playbook 声明零代码;老账号不改文件即等价为多 playbook。
    """
    explicit = strategy.get("playbooks")
    if explicit:
        return explicit
    mix = strategy.get("content_mix") or {}
    needs = strategy.get("material_needs") or {}
    types = strategy.get("content_types") or list(mix) or list(needs)
    n = len(types)
    return [{
        "id": t,
        "content_type": t,
        "weight": mix.get(t, round(1.0 / n, 3) if n else 0),
        "material_needs": needs.get(t, []),
        "view": t,
        "gen_skill": "write-xiaohongshu",  # 生成该方法论笔记的技能(G13);显式 playbook 可覆盖
    } for t in types]


def gen_skill_of(pb: dict | None) -> str:
    """一套方法论用哪个技能产笔记(G13:能力=skill,playbook 指向自己的生成技能)。缺则默认。"""
    return (pb.get("gen_skill") if pb else "") or "write-xiaohongshu"


def playbook_for(strategy: dict, content_type: str) -> dict | None:
    """给一条笔记的内容类型,解析它属于哪套 playbook(G11 过渡解:按 content_type 匹配)。
    多个 playbook 同 content_type 时取权重最高者(此为歧义点——彻底解需 Note 显式引用 playbook,
    走 Base 迁移)。无匹配返 None(生成降级为通用画像)。"""
    cands = [pb for pb in playbooks_of(strategy) if pb.get("content_type") == content_type]
    if not cands:
        return None
    return max(cands, key=lambda pb: float(pb.get("weight") or 0))


def resolve_playbook(strategy: dict, playbook_id: str = "", content_type: str = "") -> dict | None:
    """解析笔记所属 playbook:显式 id 优先(G11:笔记表.方法论 字段),否则按 content_type 猜。
    显式赋值消掉"同 content_type 多 playbook"的歧义;为空则回退 playbook_for。"""
    if playbook_id:
        for pb in playbooks_of(strategy):
            if pb.get("id") == playbook_id:
                return pb
    return playbook_for(strategy, content_type)


def validate_playbooks(strategy: dict) -> list[str]:
    """校验显式 playbooks 声明的健壮性(坏声明不静默,呼应 problems())。评审 finding#4:
    - 每个 playbook 须有 id;
    - view 键须唯一(两套方法论共用一套软链视图会串味/回溯歧义);
    - 权重须归一(∑≈1,epsilon 0.01)——否则争用/配比失真。
    合成的 playbooks(无显式声明)天然合法,返回空。"""
    explicit = strategy.get("playbooks")
    if not explicit:
        return []
    out = []
    if any(not pb.get("id") for pb in explicit):
        out.append("有 playbook 缺 id")
    views = [pb.get("view") for pb in explicit]
    dup = sorted({v for v in views if v and views.count(v) > 1})
    if dup:
        out.append(f"view 键冲突(多套方法论共用视图会串味): {dup}")
    total = sum(float(pb.get("weight") or 0) for pb in explicit)
    if abs(total - 1.0) > 0.01:
        out.append(f"权重未归一: ∑={round(total, 3)}≠1")
    return out


class Account:
    def __init__(self, name: str, strategy: dict, profile_text: str, error: str | None = None):
        self.name = name
        self.strategy = strategy
        self.profile_text = profile_text
        self.error = error  # 非 None=frontmatter 解析失败;problems() 暴露、验收报红,不静默

    def playbooks(self) -> list[dict]:
        """本账号的方法论列表(见 playbooks_of)。"""
        return playbooks_of(self.strategy)


def _accounts_dir(brand: str) -> Path:
    return config.WORKSPACE / "brands" / brand / "accounts"


def load(name: str, brand: str = "观云") -> Account | None:
    p = _accounts_dir(brand) / f"{name}.md"
    if not p.exists():
        return None
    return _parse(name, p.read_text(encoding="utf-8"))


def load_all(brand: str = "观云") -> dict[str, Account]:
    out = {}
    d = _accounts_dir(brand)
    if not d.exists():
        return out
    for p in d.glob("*.md"):
        if p.name == "README.md":
            continue
        acc = _parse(p.stem, p.read_text(encoding="utf-8"))
        if acc:
            out[acc.name] = acc
    return out


def problems(brand: str = "观云") -> dict[str, str]:
    """{账号名: 错误} for 声明有问题的账号(空=全部健康)。两类坏声明都'有声':
      ① frontmatter JSON 解析失败(acc.error);
      ② 显式 playbooks 声明不健壮(validate_playbooks:缺 id / view 冲突 / 权重未归一)。

    供验收/监控消费:ar_check 断言此为空——防坏 {号}.md 静默少排号 / 坏 playbook 配比失真无人知
    (呼应 ADR-0003『声明了但代码没消费』的哑控制一类;此前 validate_playbooks 写了却没接 gate)。
    """
    out: dict[str, str] = {}
    for a in load_all(brand).values():
        if a.error:
            out[a.name] = a.error
            continue                                  # 解析都失败,不再校验 playbook 内容
        errs = validate_playbooks(a.strategy)
        if errs:
            out[a.name] = "; ".join(errs)
    return out


def _parse(stem: str, raw: str) -> Account | None:
    strategy, body, error = {}, raw, None
    if raw.lstrip().startswith("---"):
        s = raw.lstrip()
        end = s.find("---", 3)
        if end != -1:
            front = s[3:end].strip()
            body = s[end + 3:].lstrip("\n")
            try:
                strategy = json.loads(front)
            except json.JSONDecodeError as e:
                error = f"frontmatter JSON 解析失败: {e}"
    name = strategy.get("account", stem)
    return Account(name, strategy, body, error)
