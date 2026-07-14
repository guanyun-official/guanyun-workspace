"""加工环(ADR-0006,默认关):素材选中 →(可选加工=拼/剪/AI生成)→ 挂笔记。

三层判据的活案例:
- **决策/执行 = 技能(智能叶子)**:要不要加工、哪种、怎么拼/生成——注入的 decide/execute 钩子(未接=骨架)。
- **落点/provenance/AI声明 = 代码焊死(确定性关节)**:成片来源随像素出处、AI声明需求由素材来源事实算出。
默认 config.PROCESSING_ENABLED=OFF → maybe_process 原样返回原始素材(现状链,零改动);
真需求(某模式非拼图/AI图不可)到再开 GY_PROCESSING_ENABLED=1 并接上技能钩子。

AI声明门的"任一素材=AI生成→必须勾"复用 guard.ai_declaration_required(不在这重造);
本模块只补"成片来源如何沿衍生链传播"(derive_source)与"加工步的 gated 落点"(maybe_process)。
"""
from __future__ import annotations

from typing import Callable

from . import config
from .bitable import MaterialSource as MSrc


def derive_source(input_sources: list[str], used_ai_generation: bool = False) -> str:
    """★provenance 传播焊死★:成片『来源』随像素出处(ADR-0004 沿衍生链传播)。
    任一输入素材=AI生成,或加工过程本身用了 AI 生成新画面 → 成片=AI生成(下游笔记须声明);
    否则(纯剪辑/拼接/调色,像素都来自实拍)→ 实拍(免声明)。
    **绝不给智能体判断**(合规红线):execute 钩子产出成片时必须用本函数定来源,再交 store_produced 落库。"""
    if used_ai_generation or any((s or "").strip() == MSrc.AI for s in (input_sources or [])):
        return MSrc.AI
    return MSrc.REAL


def processing_enabled() -> bool:
    """加工环开关(默认关)。GY_PROCESSING_ENABLED=1 才开;开了还得接上 decide/execute 技能钩子才真加工。"""
    return config.PROCESSING_ENABLED


def default_hooks():
    """加工环开时的默认钩子:decide=**AI 真判断**(像人一样看一眼素材再决定)、execute=按 kind 分派。
    懒导入 compose(默认关时不拉 PIL/网盘)。"""
    from . import compose
    return compose.ai_decide, compose.execute


def maybe_process(material_ids: list[str], *, account: str = "", mode: str = "",
                  decide: Callable | None = None, execute: Callable | None = None,
                  report: list | None = None) -> list[str]:
    """gated 加工步(select_materials 之后、挂笔记之前)。**默认关或缺钩子 → 原样返回原始素材**。

    开且钩子齐:decide(AI 看素材+模式,判要不要加工/哪种)→ 判"加工" 则 execute(拼图/AI封面 →
    内部用 derive_source 定来源 → store_produced 回存成片)→ 成片**追加**在原素材前(封面要排第一张);
    判"不加工" → 原样用原图(最常见,也最该是最常见)。

    **report:出了什么事必须让人知道**(2026-07-14 补)。老实现 `except Exception: return material_ids` ——
    加工判了、执行炸了(比如图像模型没开通),**它一声不吭地退回原图**,人还以为封面加上了。
    "安全退回"听着稳,落实下来就是一个永不作声的黑洞 —— 又是"想起来方便"。
    现在:任何降级都往 report 里写一句人话,draft 把它落进笔记的『质检』,卡片上 ⚠️ 给运营看。
    """
    if not processing_enabled() or not (decide and execute):
        return material_ids
    say = report if report is not None else []
    try:
        plan = decide(material_ids, account=account, mode=mode)
    except Exception as e:  # noqa: BLE001
        say.append(f"加工判断失败({type(e).__name__}),按不加工处理:{str(e)[:80]}")
        return material_ids
    if not plan or not plan.get("加工"):
        return material_ids                       # AI 判"不用加工"→ 直接用原图(不吭声是对的:没事发生)
    kind = plan.get("kind") or "?"
    try:
        produced_id = execute(plan)
    except Exception as e:  # noqa: BLE001  绝不炸穿 create_draft_note,但**必须说话**
        say.append(f"AI 判定该做「{kind}」({plan.get('理由') or '—'}),**但没做成**:{str(e)[:110]}"
                   f" → 本条仍用原素材")
        return material_ids
    if not produced_id:
        say.append(f"AI 判定该做「{kind}」,但执行返回空(素材不足/kind 不支持)→ 本条仍用原素材")
        return material_ids
    say.append(f"已自动生成「{kind}」并挂上({plan.get('理由') or '—'})")
    # 成片排**第一位**:小红书第一张图就是封面。原素材保留在后 —— 加工是"补一张",不是"换掉全部"。
    return [produced_id] + [m for m in material_ids if m != produced_id]
