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


def maybe_process(material_ids: list[str], *, account: str = "", mode: str = "", clothes: str = "",
                  decide: Callable | None = None, execute: Callable | None = None) -> list[str]:
    """gated 加工步(select_materials 之后、挂笔记之前)。**默认关或缺技能钩子 → 原样返回原始素材**(现状链)。
    开且钩子齐:decide(技能判断:要不要加工/哪种)→ 若判"加工" execute(技能+工具:拼/剪/AI生成 →
    内部用 derive_source 定来源 → store_produced 回存成片)→ 返回成片素材 id 列表;判"不加工"→ 用原图。
    钩子注入式(依赖倒置)→ 可不接真技能直测;缺钩子即使开着也安全退回原图(不炸、不臆造加工)。"""
    if not processing_enabled() or not (decide and execute):
        return material_ids
    try:
        plan = decide(material_ids, account=account, mode=mode, clothes=clothes)
        if not plan or not plan.get("加工"):
            return material_ids                   # 技能判定"不加工"→ 直接用原图(最常见)
        produced_id = execute(plan)               # 技能执行 → store_produced → 成片素材 id
        return [produced_id] if produced_id else material_ids
    except Exception:  # noqa: BLE001  加工钩子抛错→安全退回原图(绝不炸穿 create_draft_note;宁可不加工也不断链)
        return material_ids
