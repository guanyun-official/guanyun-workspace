"""自动打标管线(#40 素材不用人管理的命门):网盘素材 → 拉+转码/抽帧 → claude -p 看图按
local-skills/tagging-material 技能出标签 JSON → ingest.register。图片+视频都处理。无人值守(cron 可挂)。

  python3 -m scripts.tag_materials --from-netpan /巧荷/2026.7.1手机拍静态 --limit 6      # 试跑
  python3 -m scripts.tag_materials --from-netpan /巧荷/2026.7.1手机拍静态 --write         # 真入库

省钱:一次 claude -p 批量看多张(默认 5)出 JSON 数组,不一图一次(≈¥/次)。串行不并发。
只写测试库;来源默认实拍(agent 判 AI 合成才标 AI生成);无赛道留 orphan;按素材编号去重不重复登记。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import bitable, feishu_io, media, netpan, vision  # noqa: E402
from orchestrator.bitable import MaterialFields as MF  # noqa: E402
import scripts.ingest as ing  # noqa: E402

# 打标只出**客观事实**(这素材是什么),不管消费(哪个号/模式用=分发选材时决定)。
# 类型对齐素材表真实 12 类;备注是可寻址层(分发靠它语义选材),要写丰富。
TAXONOMY = """你是巧荷(汉服/新中式服饰)素材打标员。逐张看图,只客观描述"这是什么素材",不猜它给谁用。

【类型】(严格从下面 12 类里选一个最贴切的,视频给的是关键帧——按视频内容判)
- 上身图: 真人穿着成衣的静图(能看到人+衣服整体上身效果)
- 上身视频: 真人穿着走动/展示的视频
- 商品图: 单件成衣的展示图(平铺/挂拍/模特静态商品向,主体是"这件衣服"当商品卖)
- 形象图: 品牌调性/氛围向的形象照(人或场景为主,非纯商品、非纯细节)
- 搭配图: 多件单品成套搭配的展示(强调"怎么搭")
- 细节图: 局部特写但非面料/工艺(如领型、系带、口袋、配饰等结构细节)
- 面料·纹理特写: 面料肌理/织物纹路/刺绣纹样的微距特写(主体是"布料/纹样"本身)
- 工艺特写: 制作工艺特写(盘扣、锁边、非遗工序等"手艺"细节)
- 制作过程视频: 裁剪/缝制/染整等制作过程的视频
- 空镜·场景: 无人的场景/静物/环境空镜(园林、桌面、背景等)
- 文物原图: 博物馆/典籍里的文物原件图(考据来源)
- 文物对照图: 文物与成衣并排对照的图(考据+复原对照)

【来源】实拍(真拍的,哪怕后期剪辑/调色都算实拍) | AI生成(画面由AI合成的)。这批默认真人拍摄,除非明显是AI合成图,一律"实拍"。

【备注】一句话客观描述,尽量覆盖:颜色 / 形制(如对襟·马面·褙子)/ 场景 / 光线 / 姿势或机位 / 显眼细节 / 氛围。这是分发选材的寻址依据,写具体、别空泛。**不要**写"适合XX号"这类消费判断。

只输出 JSON 数组,每张一个对象 {"类型","来源","备注"},顺序严格对应图片编号,不要多余解释。"""


def _keyframe(video: str, out_dir: Path) -> str:
    """视频抽 1 帧关键帧给 agent 看(标整条视频)。ffmpeg 取第 1 秒那帧。"""
    out = out_dir / (Path(video).stem + "_frame.jpg")
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", video, "-frames:v", "1", str(out)],
                   capture_output=True, text=True, timeout=120)
    return str(out) if out.exists() else video


def _extract_json(text: str) -> list:
    """从 claude 输出里抠出 JSON 数组(容错 ```json 包裹/前后废话)。"""
    i, j = text.find("["), text.rfind("]")
    if i < 0 or j < 0:
        return []
    try:
        return json.loads(text[i:j + 1])
    except json.JSONDecodeError:
        return []


def tag_batch(view_paths: list[str]) -> list[dict]:
    """一次看多张图 → 标签 JSON 数组(省钱,串行一批)。后端由 vision seam 选(doubao 便宜/claude 兜底)。"""
    prompt = (f"{TAXONOMY}\n\n共 {len(view_paths)} 张图,按给你的先后顺序逐张判断,"
              f"输出与图片数等长、顺序一一对应的 JSON 数组。")
    return _extract_json(vision.see(view_paths, prompt))


def _valid_type(raw: str, kind: str) -> str:
    """模型返回的类型钳到素材表真实 12 类;越界/空 → 按形态兜底(不污染 select 选项防 schema 漂移)。"""
    return raw if raw in ing._TYPE_PREFIX else ("上身视频" if kind == "video" else "上身图")


def _seen_names(mats: list[dict]) -> set[str]:
    """已登记素材的网盘文件名集合(链接.text 存过文件名;相对路径=指针也能抽文件名)——去重防重标。"""
    seen: set[str] = set()
    for r in mats:
        f = r["fields"]
        seen.add(bitable.text(f.get(MF.LINK)).strip())
        rp = bitable.text(f.get(MF.REL_PATH)).strip()
        if rp:
            path = netpan.pointer_path(rp) if rp.startswith(netpan.POINTER_SCHEME) else rp
            seen.add(Path(path).name)
    seen.discard("")
    return seen


def run(folder: str, batch_size: int = 5, limit: int = 0, write: bool = False) -> list[dict]:
    """自动打标一整个网盘文件夹:diff 去重 → 分批(拉+转码/抽帧 → 看图打标 → register)→ 清缓存。
    **打标只出客观事实**(类型/来源/备注);适用账号一律留空(消费=分发选材时决定)。"""
    mats = feishu_io.list_records(MF.TABLE)
    seen = _seen_names(mats)
    seen_codes = {bitable.text(r["fields"].get(MF.CODE)).strip() for r in mats}   # 供 gen_code 递增序号
    files = [e for e in netpan.list_dir(folder)
             if not e["is_dir"] and media.kind(e["name"]) in ("still", "video")
             and e["name"] not in seen]
    if limit:
        files = files[:limit]
    out: list[dict] = []
    for k in range(0, len(files), batch_size):
        batch = files[k:k + batch_size]
        views, metas = [], []
        for e in batch:
            local = netpan.pull(e["path"], netpan.CACHE)
            kind = media.kind(local)
            view = media.to_jpg(local, str(netpan.CACHE)) if media.needs_jpg(local) else \
                (_keyframe(local, netpan.CACHE) if kind == "video" else local)
            views.append(view)
            metas.append({"name": e["name"], "ptr": netpan.pointer(e["path"]), "kind": kind})
        tags = tag_batch(views)
        for meta, tag in zip(metas, tags):
            mtype = _valid_type(tag.get("类型", ""), meta["kind"])
            source = "AI生成" if (tag.get("来源") == "AI生成") else "实拍"
            code = ing.gen_code(mtype, meta["name"], seen_codes)   # 系统编码 <类型>-批次-序号
            seen_codes.add(code)
            row = {"code": code, "type": mtype, "source": source, "note": tag.get("备注", "")}
            if write:
                ing.register(code, mtype, meta["ptr"], tag.get("备注", ""), source)  # 适用账号留空
            out.append(row)
            print(f"  {'✓登记' if write else '·试跑'} {code} [{mtype}/{source}] {tag.get('备注','')[:36]}")
        netpan.clear_cache()   # 每批处理完清缓存(按需缓存不占地)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-netpan", required=True, help="网盘文件夹,如 /巧荷/2026.7.1手机拍静态")
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个(试跑/控成本)")
    ap.add_argument("--write", action="store_true", help="真入库(默认试跑不写)")
    a = ap.parse_args()
    if not netpan.logged_in():
        print("❌ 网盘未登录(需 GY_NETPAN_MODE=real + BaiduPCS-Go 已登录)", file=sys.stderr)
        return 2
    print(f"自动打标 {a.from_netpan}  batch={a.batch_size} limit={a.limit or '全部'} write={a.write}")
    res = run(a.from_netpan, a.batch_size, a.limit, a.write)
    print(f"\n{'✅ 入库' if a.write else '试跑'} {len(res)} 条" + ("(加 --write 真入库)" if not a.write else ""))
    if a.write and res:
        feishu_io.log_run(summary=f"自动打标入库 {len(res)} 条 · {a.from_netpan}", action="自动打标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
