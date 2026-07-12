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
from orchestrator import bitable, config, feishu_io, media, netpan  # noqa: E402
from orchestrator.bitable import AccountFields as AF, MaterialFields as MF  # noqa: E402
import scripts.ingest as ing  # noqa: E402

TAXONOMY = """你是巧荷(汉服/新中式)素材打标员。看图逐张输出标签。判据:
- 类型: 上身图(人穿着的静图) | 上身视频(此项给视频关键帧,标它) | 形象图(偏产品/细节/面料刺绣特写,非上身)
- 来源: 实拍(真拍的,哪怕后期剪辑/调色) | AI生成(画面由AI合成的). 这批都是真人拍摄,除非明显是AI合成图,一律"实拍"。
- 适用账号: 唯美/高端出片→["ootd号"];真实自然素人感→["图文号1","图文号2"];认不准适配谁→[](留空)。形象图/细节特写通常没有唯美出片账号消费→[]。
- 备注: 一句话客观描述(颜色/形制/场景/光线/姿势或细节),供货对板与内容寻址。
只输出 JSON 数组,每张一个对象 {"类型","来源","适用账号":[],"备注"},顺序严格对应给你的图片编号,不要多余解释。"""


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
    """一次 claude -p 批量看多张图 → 标签 JSON 数组(省钱)。串行一批。"""
    listing = "\n".join(f"图{i + 1}: {p}" for i, p in enumerate(view_paths))
    prompt = f"{TAXONOMY}\n\n逐张看下面 {len(view_paths)} 张图并按编号顺序输出 JSON 数组:\n{listing}"
    r = subprocess.run(["claude", "-p", prompt, "--output-format", "json",
                        "--max-turns", str(4 + 2 * len(view_paths))],
                       capture_output=True, text=True, timeout=600, cwd=str(config.WORKSPACE))
    try:
        result = json.loads(r.stdout[r.stdout.find("{"):]).get("result", "")
    except (json.JSONDecodeError, ValueError):
        result = r.stdout
    return _extract_json(result)


def run(folder: str, batch_size: int = 5, limit: int = 0, write: bool = False) -> list[dict]:
    """自动打标一整个网盘文件夹:diff 去重 → 分批(拉+转码/抽帧 → claude 打标 → register)→ 清缓存。"""
    acc_id = {bitable.text(r["fields"].get(AF.NAME)).strip(): r["record_id"]
              for r in feishu_io.list_records(AF.TABLE)}
    # 去重:按已登记素材的网盘文件名(register 把文件名存进 链接.text)——手动标过的也认得,不重标
    seen = {bitable.text(r["fields"].get(MF.LINK)).strip() for r in feishu_io.list_records(MF.TABLE)}
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
            metas.append({"code": Path(e["name"]).stem, "ptr": netpan.pointer(e["path"]),
                          "kind": kind})
        tags = tag_batch(views)
        for meta, tag in zip(metas, tags):
            mtype = tag.get("类型") or ("上身视频" if meta["kind"] == "video" else "上身图")
            source = "AI生成" if (tag.get("来源") == "AI生成") else "实拍"
            accs = [acc_id[n] for n in (tag.get("适用账号") or []) if n in acc_id] or None
            row = {"code": meta["code"], "type": mtype, "source": source,
                   "note": tag.get("备注", ""), "accounts": accs}
            if write:
                ing.register(meta["code"], mtype, meta["ptr"], tag.get("备注", ""), source, accs)
            out.append(row)
            print(f"  {'✓登记' if write else '·试跑'} {meta['code']} [{mtype}/{source}/{'赛道' if accs else 'orphan'}] {tag.get('备注','')[:34]}")
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
