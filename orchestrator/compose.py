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
    """保守规则版决策(留作 ai_decide 的离线兜底/单测对照):模式含『搭配』且 ≥2 张 → 拼图。
    **它不是"像人一样判断"** —— 一条死规则而已。生产走 ai_decide。"""
    if "搭配" in (mode or "") and len(material_ids) >= 2:
        return {"加工": True, "kind": "拼图", "inputs": material_ids[:4], "理由": "规则:搭配类且≥2张"}
    return {"加工": False}


_DECIDE_PROMPT = """你是巧荷(汉服/新中式服装品牌)的内容运营,正在过一条即将发布的小红书笔记。

【这条笔记】账号:{account} 模式:{mode}
【它已经选好的素材(豆包看图打的真实标注,发布时配的就是这些)】
{facts}

【你能做的加工,只有这两种】
1. AI封面 —— 生成一张封面图放在**第一张**。小红书第一张就是封面,决定人点不点进来。
   什么时候值得做:现有素材没有一张能当封面(比如全是局部特写/细节图,没有能一眼看懂的主图),
   或者这条是图文笔记、需要一张有信息量的开场图。
2. 拼图 —— 把 2~4 张现有素材拼成一张(像素全来自原图,不生成新画面)。
   什么时候值得做:多套搭配要放一起对比。

【判断准则 —— 像人一样,别为了做而做】
· **绝大多数情况应该"不加工"**:素材本身够用,就直接发。加工是补短板,不是走流程。
· 视频笔记(模式含"视频")**不要**加封面(视频的封面是抽帧,不是另配图)。
· 素材里已经有能当封面的完整上身图/形象图 → 不需要 AI 封面。
· AI 生成的画面**必须勾 AI 声明**(合规),会给运营添一道手续 —— 没有明显收益就别加。

只输出一个 JSON,不要解释:
{{"加工": true/false, "kind": "AI封面" 或 "拼图" 或 "", "理由": "一句话,人能看懂", "封面提示词": "若 kind=AI封面,给一句中文文生图提示词,须贴合上面素材的真实颜色/衣服/场景,不许凭空编造别的衣服"}}"""


def ai_decide(material_ids: list[str], *, account: str = "", mode: str = "",
              clothes: str = "") -> dict:
    """**AI 像人一样看一眼素材,再决定这条要不要加工**(加工环的智能叶子)。

    以前这里是 `simple_decide` —— 一条死规则("模式含『搭配』且≥2张 → 拼图")。
    那不叫判断,叫 if。用户要的是"整体就像人一样":看完素材,觉得该加个封面就加。

    喂给它的是**真素材的 vision 备注**(豆包看图打的标),不是素材 id ——
    让它**看得见画面**再判断,否则又是"眼前一片空白却被要求下判断"(和当初出稿编造是同一个病)。
    返回形态不对/模型抽风 → 返回 {"加工": False}(保守:宁可不加工,不乱加)。
    """
    import json

    from . import ark, draft, feishu_io
    rows = [r for r in feishu_io.list_records(MF.TABLE) if r["record_id"] in set(material_ids)]
    facts = draft.material_facts(rows) or "(没有素材)"
    text, _ = ark.chat(_DECIDE_PROMPT.format(account=account, mode=mode, facts=facts[:1500]))
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i:
        return {"加工": False}
    try:
        plan = json.loads(text[i:j + 1])
    except (ValueError, TypeError):
        return {"加工": False}
    if not plan.get("加工"):
        return {"加工": False}
    plan["inputs"] = material_ids
    return plan


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
    """kind='拼图':PIL 网格合成(确定性,像素全来自输入)。
    ★provenance:成片来源由 processing.derive_source(输入来源, 是否用AI) 定,不自己拍脑袋★。
    素材不足 → None(maybe_process 会如实报告"没做成",不静默)。"""
    import scripts.ingest as ing
    if len(plan.get("inputs") or []) < 2:
        return None
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


def cover_execute(plan: dict) -> str | None:
    """kind='AI封面':ARK 文生图 → 下载 → 回存网盘+登记素材 → 返回素材 record_id。

    ★provenance 焊死★:这里的像素**是 AI 生成的**,所以 `derive_source(..., used_ai_generation=True)`
    必然给出『AI生成』→ 该素材挂上笔记后,**AI 声明门**会要求人勾 AI 声明才能进待发布。
    合规链条是:AI 生了像素 → 素材『来源=AI生成』→ 门要求声明 → **人勾**(机器绝不代勾)。

    模型没开通 → ark.ModelNotOpen 直接往上抛(**不吞**):maybe_process 会把
    "AI 判定该加封面,但没做成:模型未开通" 写进笔记『质检』,卡片上 ⚠️ 给运营看。
    悄悄跳过才是最坏的 —— 人会以为封面加上了。
    """
    import urllib.request

    import scripts.ingest as ing
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
    source = processing.derive_source(sources, used_ai_generation=True)   # 必然=AI生成(像素是生的)
    rid, _ = ing.store_produced(str(out), "形象图", source=source,
                                note=f"AI封面(豆包 Seedream 生成)· 提示词:{prompt[:80]}"
                                     f" · 发布时放第一张")
    netpan.clear_cache()
    return rid


_EXECUTORS = {"拼图": compose_execute, "AI封面": cover_execute}


def execute(plan: dict) -> str | None:
    """execute 钩子的**分派器**:按 plan['kind'] 找执行器。不认识的 kind → None(如实报"不支持")。
    加工环真要长出新能力(如剪辑),就在 _EXECUTORS 里加一行 —— 而不是在 decide 的 prompt 里
    多写一句话就当做完了(**那正是"想起来方便"**:AI 会照着判,而执行端根本没有那只手)。"""
    fn = _EXECUTORS.get(plan.get("kind") or "")
    return fn(plan) if fn else None
