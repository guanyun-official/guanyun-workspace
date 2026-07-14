"""加工执行(**手**):把 agent 判好的加工方案真做出来 → 回存网盘 03-成片 → 登记素材。

★这里没有"要不要加工"★

老实现有 `ai_decide()` —— harness 拿着一份写好的判断准则 prompt("绝大多数情况应该不加工"、
"视频笔记不要加封面"、"素材里有完整上身图就不需要 AI 封面"…),**去问另一个模型**该不该加工,
再把它的答案 JSON 解析出来执行。

那是**最隐蔽的一种导轨**:它看起来"很智能"(还在调 LLM 呢),实际上是 harness
把判断准则写死在一段 prompt 里,然后**替 agent 去问、替 agent 拿答案**。
判断准则一旦进了代码,它就不是 agent 的判断了 —— 它是我的规则,只是换了个模型来执行。

现在:**agent 自己看素材(它有眼睛)、自己判断要不要加工**(知识在技能里,可以违背也不出事),
判好了就调 `execute(plan)`。harness 只负责把像素真的做出来,以及**焊死 provenance**。

★焊死的一条(法律,不是判断)★
产物『来源』一律由 `guard.derive_source(输入来源, 是否用了AI生成)` 定 —— **agent 说了不算**。
AI 生了像素 → 来源=AI生成 → 发布前 AI 声明门要求人勾。合规链条一个环都不许松。
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from . import bitable, feishu_io, guard, ingest, media, netpan
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


def _resolve(material_ids: list[str]) -> tuple[list[str], list[str]]:
    """素材 record_id → (本地静图路径列表, 来源列表)。从素材表读指针 → netpan pull → 转 jpg。真 IO。"""
    imgs, sources = [], []
    for mid in material_ids:
        r = feishu_io.get_record(MF.TABLE, mid)
        if not r:
            continue
        f = r["fields"]
        ptr = bitable.text(f.get(MF.REL_PATH)).strip()
        if not ptr.startswith(netpan.POINTER_SCHEME):
            continue
        local = netpan.pull(netpan.pointer_path(ptr), netpan.CACHE)
        if media.kind(local) != "still":              # 拼图只拼静图
            continue
        imgs.append(media.to_jpg(local, str(netpan.CACHE)) if media.needs_jpg(local) else local)
        sources.append(bitable.text(f.get(MF.SOURCE)).strip())
    return imgs, sources


# ★产物的『类型』由 agent 给,不写死★(2026-07-14 架构审查)
# 老实现写死成 `"搭配图"` / `"形象图"` —— **这两个值在素材表里根本不存在**
# (词汇已改成纯内容:上身/商品/形象/搭配/…,不带"图"),真跑要么炸、要么给 select 悄悄加个新选项。
# 而且"这张拼图算什么内容"**本来就是它看图之后的判断**。


def compose_execute(plan: dict) -> str | None:
    """kind='拼图':PIL 网格合成(确定性,像素全来自输入)。
    素材不足 → None,**如实报"没做成"**(绝不静默退回原图假装做好了)。"""
    if len(plan.get("inputs") or []) < 2:
        return None
    imgs, sources = _resolve(plan["inputs"])
    if len(imgs) < 2:
        return None
    out = str(netpan.CACHE / f"拼图-{plan['inputs'][0]}.jpg")
    grid_compose(imgs, out)
    source = guard.derive_source(sources, used_ai_generation=False)   # 纯拼图无AI→随输入像素出处
    rid, _ = ingest.store_produced(out, plan.get("类型") or "搭配", source=source,
                                   note=plan.get("备注") or f"拼图 源自 {'+'.join(plan['inputs'])}")
    netpan.clear_cache()
    return rid


def cover_execute(plan: dict) -> str | None:
    """kind='AI封面':ARK 文生图 → 下载 → 回存网盘 + 登记素材 → 返回素材 record_id。

    ★provenance 焊死★:这里的像素**是 AI 生成的**,`derive_source(..., used_ai_generation=True)`
    必然给出『AI生成』→ 该素材挂上笔记后,**AI 声明门**会要求人勾才能进待发布。

    模型没开通 → `ark.ModelNotOpen` **直接往上抛,不吞**:调用方如实报错。
    悄悄跳过才是最坏的 —— 人会以为封面加上了。
    """
    import urllib.request

    from . import ark
    prompt = (plan.get("封面提示词") or "").strip()
    if not prompt:
        return None
    url = ark.image(prompt)                                    # 未开通→ModelNotOpen 抛出,不静默
    out = netpan.CACHE / f"AI封面-{abs(hash(prompt)) % 10**10}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r, open(out, "wb") as fh:  # noqa: S310
        fh.write(r.read())
    _, sources = _resolve(plan.get("inputs") or [])
    source = guard.derive_source(sources, used_ai_generation=True)   # 必然=AI生成(像素是生的)
    rid, _ = ingest.store_produced(str(out), plan.get("类型") or "形象", source=source,
                                   note=(plan.get("备注") or
                                         f"AI封面 · 提示词:{prompt[:80]} · 发布时放第一张"))
    netpan.clear_cache()
    return rid


_EXECUTORS = {"拼图": compose_execute, "AI封面": cover_execute}


def execute(plan: dict) -> str | None:
    """按 plan['kind'] 分派执行。不认识的 kind → None(如实报"不支持")。
    真要长出新能力(如剪辑),在 `_EXECUTORS` 里加一行 —— **而不是在某段 prompt 里多写一句话就当做完了**
    (那正是"想起来方便":判断端会照着判,执行端根本没有那只手)。"""
    fn = _EXECUTORS.get(plan.get("kind") or "")
    return fn(plan) if fn else None
