"""自动打标管线(#40 素材不用人管理的命门):网盘素材 → 拉+转码/抽帧 → vision seam 看图出标签
JSON(对齐素材表真实 12 类)→ ingest.register。图片+视频都处理。无人值守(cron 可挂)。

  python3 -m scripts.tag_materials --from-netpan /巧荷/2026.7.1手机拍静态 --limit 6      # 试跑
  python3 -m scripts.tag_materials --from-netpan /巧荷/2026.7.1手机拍静态 --write         # 真入库

看图后端由 orchestrator.vision seam 选(GY_VISION_BACKEND=doubao 便宜/claude 兜底);doubao 需 env ARK_API_KEY。
省钱:一次批量看多张(默认 5)出 JSON 数组,不一图一次。串行不并发。
只写测试库;**打标只出客观事实**(类型+来源+丰富NL备注),适用账号留空(消费=分发选材决定);
按网盘文件名去重不重复登记(手动标过的也认得)。
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import bitable, config, feishu_io, media, netpan, vision  # noqa: E402
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

【来源】实拍(真人真拍,哪怕后期剪辑/调色) | AI生成(画面由AI合成)。正常真人出片标实拍;**只要疑似AI合成就标AI生成**(合规硬要求:漏标AI是硬伤,就低不就高、宁可让人往下摘不可漏标)。注:来源最终以落点为准——AI素材落 02-AI生成/ 目录会被强制标AI生成。

【备注】一句话客观描述,尽量覆盖:颜色 / 形制(如对襟·马面·褙子)/ 场景 / 光线 / 姿势或机位 / 显眼细节 / 氛围。这是分发选材的寻址依据,写具体、别空泛。**不要**写"适合XX号"这类消费判断。

只输出 JSON 数组,每张一个对象 {"类型","来源","备注"},顺序严格对应图片编号,不要多余解释。"""


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


_VIDEO_TYPES = frozenset({"上身视频", "制作过程视频"})


def _valid_type(raw: str, kind: str) -> str:
    """模型返回的类型钳到素材表真实 12 类,且**按文件形态约束**:
    Doubao 看的是关键帧(静图),会把视频误标成静图类——**视频文件强制落视频类**(默认上身视频);
    静图若误落视频类/越界→上身图。防 schema 漂移 + 防"视频标成上身图"。"""
    raw = (raw or "").strip()
    if kind == "video":
        return raw if raw in _VIDEO_TYPES else "上身视频"
    return raw if (raw in ing._TYPE_PREFIX and raw not in _VIDEO_TYPES) else "上身图"


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


def _align(metas: list[dict], views: list[str], tags: list[dict]) -> list[tuple]:
    """按序把 (meta, view, tag) 对齐;标签少于图=缺的补 {}(_valid_type 会兜底),**绝不静默丢图**。纯函数直测。"""
    return [(metas[i], views[i], tags[i] if i < len(tags) else {}) for i in range(len(metas))]


def _prep_batch(files_batch: list[dict]) -> tuple[list[dict], list[str]]:
    """拉取+转码一批(**每图隔离**:一张坏图跳过不炸全场)。返回 (metas, view_paths)。IO/CPU,在并发 worker 跑。"""
    metas, views = [], []
    for e in files_batch:
        try:
            local = netpan.pull(e["path"], netpan.CACHE)
            kind = media.kind(local)
            if media.needs_jpg(local):
                view = media.to_jpg(local, str(netpan.CACHE))
            elif kind == "video":
                view = media.video_keyframe(local, str(netpan.CACHE))   # 中点抽帧(ffprobe定位)
            else:
                view = local
            if not Path(view).exists():                      # 转码没产出(sips 静默失败)→ 跳过,不让读空文件炸全场
                print(f"  ⚠跳过(视图缺失/转码失败) {e['name']}", file=sys.stderr)
                continue
            metas.append({"name": e["name"], "ptr": netpan.pointer(e["path"]), "kind": kind})
            views.append(view)
        except Exception as ex:                              # noqa: BLE001  单图 prep 失败隔离,不拖垮整批
            print(f"  ⚠跳过(prep失败) {e['name']}: {str(ex)[:60]}", file=sys.stderr)
    return metas, views


def _tag_one_batch(files_batch: list[dict]) -> list[tuple]:
    """一个 batch 的 prep + 看图打标(可并发调度)。**批失败隔离**(Doubao 报错跳过该批不炸整个文件夹);
    标签空/少也不丢图(_align 补兜底)。返回 [(meta, tag)]。"""
    metas, views = _prep_batch(files_batch)
    if not views:
        return []
    try:
        tags = tag_batch(views)
    except Exception as ex:                                  # noqa: BLE001  单批打标失败隔离
        print(f"  ⚠批打标失败(跳过{len(views)}张): {str(ex)[:80]}", file=sys.stderr)
        return []
    if len(tags) != len(views):
        print(f"  ⚠标签数({len(tags)})≠图数({len(views)}):按序对齐,缺的兜底类型(不丢图)", file=sys.stderr)
    return _align(metas, views, tags)


def run(folder: str, batch_size: int = 5, limit: int = 0, write: bool = False,
        concurrency: int | None = None) -> list[dict]:
    """自动打标一整个网盘文件夹:diff 去重 → **分批并发**(拉+转码/抽帧 → 看图打标,每图/每批隔离)→ 串行登记 → 清缓存。
    **打标只出客观事实**(类型/来源/备注);适用账号留空(消费=分发选材时决定)。
    并发度默认 config.TAG_CONCURRENCY(护本机负载,上线服务器调高)。**登记串行**=gen_code 序号单调 + feishu 限流。"""
    concurrency = concurrency or config.TAG_CONCURRENCY
    mats = feishu_io.list_records(MF.TABLE)
    seen = _seen_names(mats)
    seen_codes = {bitable.text(r["fields"].get(MF.CODE)).strip() for r in mats}   # 供 gen_code 递增序号
    all_media = [e for e in netpan.list_dir(folder)
                 if not e["is_dir"] and media.kind(e["name"]) in ("still", "video")
                 and e["name"] not in seen]
    if config.INGEST_VIDEO:
        files = all_media                                    # 服务器/确需:视频也入(下载一次→中点抽帧)
    else:
        vids = [e for e in all_media if media.kind(e["name"]) == "video"]
        if vids:
            print(f"  ⏭ 跳过 {len(vids)} 个视频(GY_INGEST_VIDEO=0 护本机;raw是剪辑原料→走成片入库)",
                  file=sys.stderr)
        files = [e for e in all_media if media.kind(e["name"]) == "still"]   # 本机默认只入静图
    if limit:
        files = files[:limit]
    batches = [files[k:k + batch_size] for k in range(0, len(files), batch_size)]
    out: list[dict] = []
    chunk = max(1, concurrency)                              # 每 chunk 并发 N 批,跑完统一清缓存(护磁盘)
    for i in range(0, len(batches), chunk):
        pairs: list[tuple] = []
        with ThreadPoolExecutor(max_workers=concurrency) as ex:   # 打标并发(护本机=并发度低)
            for br in ex.map(_tag_one_batch, batches[i:i + chunk]):
                pairs.extend(br)
        for meta, view, tag in pairs:                       # 串行登记:gen_code 序号单调
            mtype = _valid_type(tag.get("类型", ""), meta["kind"])
            source = "AI生成" if (tag.get("来源") == "AI生成") else "实拍"
            code = ing.gen_code(mtype, meta["name"], seen_codes)
            seen_codes.add(code)
            row = {"code": code, "type": mtype, "source": source, "note": tag.get("备注", "")}
            if write:
                thumb_token = ""
                try:                                        # 顺带生成+上传缩略图(base驾驶舱瞄一眼),失败不拦登记
                    thumb = str(netpan.CACHE / (Path(view).stem + "_thumb.jpg"))
                    media.thumbnail(view, thumb, 400)
                    thumb_token = feishu_io.upload_media(thumb, meta["name"] + ".jpg")
                except Exception as e:  # noqa: BLE001  缩略图失败不拦登记
                    print(f"  ⚠缩略图失败 {code}: {str(e)[:40]}", file=sys.stderr)
                ing.register(code, mtype, meta["ptr"], tag.get("备注", ""), source, thumb_token=thumb_token)
            out.append(row)
            print(f"  {'✓登记' if write else '·试跑'} {code} [{mtype}/{source}] {tag.get('备注','')[:36]}")
        netpan.clear_cache()                                # 每 chunk 清缓存(按需缓存不占地)
    return out


_LEGACY_TYPES = frozenset({"上身图", "上身视频", "形象图"})   # 字段归位前只用过这 3 类


def _legacy_rows(mats: list[dict]) -> list[dict]:
    """老打标行 = 字段归位前(旧 register)入库的行:相对路径为空 **且** 类型是旧 3 类之一。
    加类型判据防误伤"人在飞书 UI 手动新建的行"(那些也没相对路径,但类型多是别的/或该保留)。
    这些正是本轮要重标的;删掉后重跑 tagger 会以真实 12 类+字段归位重新入库。
    三重保底:dry-run 先列出给人过目 + --write 前全表备份 + 只测试库。纯谓词(零 IO,records 注入)→ 可直测。"""
    out = []
    for r in mats:
        f = r["fields"]
        no_relpath = not bitable.text(f.get(MF.REL_PATH)).strip()      # 相对路径空 = 旧 register 入的
        old_type = bitable.text(f.get(MF.TYPE)).strip() in _LEGACY_TYPES
        if no_relpath and old_type:
            out.append({"record_id": r["record_id"], "code": bitable.text(f.get(MF.CODE)),
                        "type": bitable.text(f.get(MF.TYPE)), "file": bitable.text(f.get(MF.LINK))})
    return out


def reset_legacy(write: bool = False) -> list[dict]:
    """重标第一步:列出/清除老打标行(相对路径空)。write=True 先**全表备份**(误删可恢复)再删,否则只列(干跑)。
    删后重跑 `tag_materials --from-netpan <源文件夹> --write` 即以真实 12 类+字段归位重新入库。
    红线:只在测试库删(assert_base_allowed)、只删老自建行(相对路径空)、删前备份读回自证。"""
    mats = feishu_io.list_records(MF.TABLE)
    legacy = _legacy_rows(mats)
    if write and legacy:
        from orchestrator import guard
        import scripts.backup_tables as backup
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只在测试库删
        backup.main()   # 删前全表备份(误删可恢复;备份读回自证)
        for row in legacy:
            feishu_io.delete_record(MF.TABLE, row["record_id"])
        feishu_io.log_run(summary=f"重标清除老打标行 {len(legacy)} 条(相对路径空,已备份)", action="重标清除")
    return legacy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-netpan", help="网盘文件夹,如 /巧荷/2026.7.1手机拍静态")
    ap.add_argument("--reset-legacy", action="store_true",
                    help="重标准备:列出/清除老打标行(相对路径空);配 --write 才真删(先自动备份)")
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个(试跑/控成本)")
    ap.add_argument("--write", action="store_true", help="真入库/真删(默认试跑不写)")
    a = ap.parse_args()
    if a.reset_legacy:
        legacy = reset_legacy(a.write)
        for row in legacy:
            print(f"  {'✗已删' if a.write else '·待删'} {row['code']} [{row['type']}] {row['file']}")
        print(f"\n{'✅ 已清除' if a.write else '干跑列出'} {len(legacy)} 条老打标行"
              + ("(加 --write 真删,会先备份;删后重跑 --from-netpan 重标)" if not a.write else "(已备份;现可重跑 --from-netpan 重标)"))
        return 0
    if not a.from_netpan:
        print("❌ 需 --from-netpan <文件夹> 或 --reset-legacy", file=sys.stderr)
        return 2
    if not netpan.logged_in():
        print("❌ 网盘未登录(需 GY_NETPAN_MODE=real + BaiduPCS-Go 已登录)", file=sys.stderr)
        return 2
    print(f"自动打标 {a.from_netpan}  batch={a.batch_size} limit={a.limit or '全部'} write={a.write} "
          f"看图后端={config.VISION_BACKEND}")
    res = run(a.from_netpan, a.batch_size, a.limit, a.write)
    print(f"\n{'✅ 入库' if a.write else '试跑'} {len(res)} 条" + ("(加 --write 真入库)" if not a.write else ""))
    if a.write and res:
        feishu_io.log_run(summary=f"自动打标入库 {len(res)} 条 · {a.from_netpan}", action="自动打标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
