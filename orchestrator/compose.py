"""加工执行(加工环 execute 钩子的可跑实现):原始素材 → 真加工成成片 → store_produced 回存登记。

加工环(ADR-0006)默认关;开时由 processing.maybe_process 的 execute 钩子调这里。
已实现(确定性、无外部服务、可真跑):
- **拼图**(`grid_compose` + kind='拼图'):PIL 网格合成,像素全来自输入素材 → 来源由 `derive_source` 定
  (纯实拍拼=实拍免声明;含 AI 输入=AI生成需声明)。
待接(留路由,honest 标注依赖):
- **剪辑**(kind='剪辑')→ `video-editing` skill(agent 主剪 + 本地 VectCutAPI:9001),重,另接;
- **AI生成**(kind='AI生成')→ ARK image-gen(文生图/图生图,需 image-gen 模型),来源=AI生成需声明。

decide(要不要加工/哪种)是可替换的**智能叶子**;这里给保守规则版,真需求可换 LLM/更强技能钩子。
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from . import bitable, feishu_io, media, netpan, processing
from .bitable import MaterialFields as MF


def grid_compose(image_paths: list[str], out_path: str, cell: int = 640,
                 cols: int | None = None, bg=(255, 255, 255)) -> str:
    """N 张图 → 网格拼图(确定性,像素全来自输入=纯拼接)。返回 out_path。至少 1 张。"""
    imgs = [Image.open(p).convert("RGB") for p in image_paths]
    if not imgs:
        raise ValueError("grid_compose 需至少 1 张图")
    cols = cols or math.ceil(math.sqrt(len(imgs)))
    rows = math.ceil(len(imgs) / cols)
    canvas = Image.new("RGB", (cols * cell, rows * cell), bg)
    for i, im in enumerate(imgs):
        im.thumbnail((cell, cell))
        x = (i % cols) * cell + (cell - im.width) // 2
        y = (i // cols) * cell + (cell - im.height) // 2
        canvas.paste(im, (x, y))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=88)
    return out_path


def simple_decide(material_ids: list[str], *, account: str = "", mode: str = "",
                  clothes: str = "") -> dict:
    """默认加工决策(保守规则版):模式含『搭配』且 ≥2 张素材 → 提议拼图;否则不加工(用原图)。
    这是 workflow 关节里可替换的智能叶子——真需求可换 LLM/看图技能钩子做更聪明的判断。"""
    if "搭配" in (mode or "") and len(material_ids) >= 2:
        return {"加工": True, "kind": "拼图", "inputs": material_ids[:4]}
    return {"加工": False}


def _resolve(material_ids: list[str]) -> tuple[list[str], list[str]]:
    """素材 record_id → (本地静图路径列表, 来源列表)。从素材表读相对路径指针→netpan pull→转 jpg。真 IO。"""
    idx = {r["record_id"]: r["fields"] for r in feishu_io.list_records(MF.TABLE)}
    imgs, sources = [], []
    for mid in material_ids:
        f = idx.get(mid)
        if not f:
            continue
        ptr = bitable.text(f.get(MF.REL_PATH)).strip()
        if not ptr.startswith(netpan.POINTER_SCHEME):
            continue
        local = netpan.pull(netpan.pointer_path(ptr), netpan.CACHE)
        if media.kind(local) != "still":              # 拼图只拼静图
            continue
        imgs.append(media.to_jpg(local, str(netpan.CACHE)) if media.needs_jpg(local) else local)
        sources.append(bitable.text(f.get(MF.SOURCE)).strip())
    return imgs, sources


def compose_execute(plan: dict) -> str | None:
    """execute 钩子:按 plan 真加工出成片、回存登记。当前实现 kind='拼图'(PIL grid,确定性)。
    ★provenance:成片来源由 processing.derive_source(输入来源, 是否用AI) 定,不自己拍脑袋★。
    返回成片素材 record_id;不支持的 kind / 素材不足 → None(maybe_process 安全退回原图)。"""
    import scripts.ingest as ing
    if plan.get("kind") != "拼图" or len(plan.get("inputs") or []) < 2:
        return None                                    # 剪辑/AI生成留待接 video-editing/ARK image-gen
    imgs, sources = _resolve(plan["inputs"])
    if len(imgs) < 2:
        return None
    out = str(netpan.CACHE / f"拼图-{plan['inputs'][0]}.jpg")
    grid_compose(imgs, out)
    source = processing.derive_source(sources, used_ai_generation=False)   # 纯拼图无AI→随输入像素出处
    rid, _ = ing.store_produced(out, "搭配图", source=source,
                                note=f"拼图 源自 {'+'.join(plan['inputs'])}")
    netpan.clear_cache()
    return rid
