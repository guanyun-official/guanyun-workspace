"""自动打标管线(#40 素材不用人管理的命门):网盘素材 → 拉+转码/抽帧 → vision seam 看图出标签
JSON(对齐素材表真实 12 类)→ ingest.register。图片+视频都处理。无人值守(cron 可挂)。

  python3 -m scripts.tag_materials --from-netpan /巧荷/2026.7.1手机拍静态 --limit 6      # 试跑
  python3 -m scripts.tag_materials --from-netpan /巧荷/2026.7.1手机拍静态 --write         # 真入库

看图后端由 orchestrator.vision seam 选(GY_VISION_BACKEND=doubao 便宜/claude 兜底);doubao 需 env ARK_API_KEY。
省钱:一次批量看多张(默认 5)出 JSON 数组,不一图一次。串行不并发。
只写测试库;**打标只出客观事实**(类型+来源+丰富NL备注),适用账号留空(消费=分发选材决定);
按网盘文件名去重不重复登记(手动标过的也认得)。
"""
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  ⚠️  这是一条【导轨】—— 它把驾驶者换成了轨道。**下个 session 要换掉它。**        ║
# ║                                                                              ║
# ║  它里面搅着三种性质完全不同的东西:                                             ║
# ║    ✅ 原子(Tools)     —— 留在 harness                                        ║
# ║    ❌ 判断(该归模型)   —— _valid_type 硬钳制 = "这张图是什么类型" · 批大小 · 并发度      ║
# ║    ❌ 方法(该进技能)   —— TAXONOMY 12 类分类法 —— **技能里已有一份,这里又抄了一遍**      ║
# ║                                                                              ║
# ║  **拆完之后,全景图里没有"脚本"这一层**:cron 只负责叫醒 agent,不含任何判断。   ║
# ║  agent 读面板(Observation)、读技能(Knowledge)、用原子(Tools)、撞红线。   ║
# ║                                                                              ║
# ║  ⚠️ **不是"删",是"换"** —— 现在删掉它,内容工厂当场没有心跳。                   ║
# ║     先造出"agent 上班"这个入口,再把 cron 指过去。                             ║
# ║                                                                              ║
# ║  详见 docs/架构.md 第四节。判据:CLAUDE.md「唯一判据」。                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

from __future__ import annotations

import argparse
import json
import re
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


def tag_batch(view_paths: list[str]) -> tuple[list[dict], float]:
    """一次看多张图 → (标签 JSON 数组, 看图成本元)。后端由 vision seam 选(doubao 便宜/claude 兜底)。
    成本用 vision 实测 usage 估,冒泡到 run 汇总记运行日志→纳入月度成本硬闸(打标看图曾在帽外)。"""
    prompt = (f"{TAXONOMY}\n\n共 {len(view_paths)} 张图,按给你的先后顺序逐张判断,"
              f"输出与图片数等长、顺序一一对应的 JSON 数组。")
    text, cost = vision.see_with_cost(view_paths, prompt)
    return _extract_json(text), cost


_VIDEO_TYPES = frozenset({"上身视频", "制作过程视频"})


def _valid_type(raw: str, kind: str) -> str:
    """模型返回的类型钳到素材表真实 12 类,且**按文件形态约束**:
    Doubao 看的是关键帧(静图),会把视频误标成静图类——**视频文件强制落视频类**(默认上身视频);
    静图若误落视频类/越界→上身图。防 schema 漂移 + 防"视频标成上身图"。"""
    raw = (raw or "").strip()
    if kind == "video":
        return raw if raw in _VIDEO_TYPES else "上身视频"
    return raw if (raw in ing._TYPE_PREFIX and raw not in _VIDEO_TYPES) else "上身图"


def _note_of(tag: dict, kind: str) -> str:
    """备注落库前的**诚实标注**:视频的备注**只是一帧关键帧**的描述,必须说出来。

    2026-07-14 上班撞到:补拍单让摄影师拍「上身视频」,给的参考写着
    「浅粉色…衣身**局部特写**,画面下方有裸露的手臂局部」—— 摄影师当场懵:
    你让我拍上身视频,给我看个局部特写?
    真相是那确实是条上身视频(EG9A7581.MP4),但豆包看的是**抽出来的一帧**,
    而那一帧恰好是个特写。抽帧打标是当初定的设计,没错 —— 错在**备注没说自己只是一帧**。
    于是一帧被当成了全部:摄影师照它拍、文案拿它当"这条视频的画面事实"。
    加四个字,谁读都不会误会。
    """
    note = (tag.get("备注") or "").strip()
    if kind == "video" and note and not note.startswith("(视频关键帧)"):
        return f"(视频关键帧){note}"
    return note


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


def _tag_one_batch(files_batch: list[dict]) -> tuple[list[tuple], float]:
    """一个 batch 的 prep + 看图打标(可并发调度)。**批失败隔离**(Doubao 报错跳过该批不炸整个文件夹);
    标签空/少也不丢图(_align 补兜底)。返回 ([(meta, view, tag)], 本批看图成本元)。"""
    metas, views = _prep_batch(files_batch)
    if not views:
        return [], 0.0
    try:
        tags, cost = tag_batch(views)
    except Exception as ex:                                  # noqa: BLE001  单批打标失败隔离
        print(f"  ⚠批打标失败(跳过{len(views)}张): {str(ex)[:80]}", file=sys.stderr)
        return [], 0.0
    if len(tags) != len(views):
        print(f"  ⚠标签数({len(tags)})≠图数({len(views)}):按序对齐,缺的兜底类型(不丢图)", file=sys.stderr)
    return _align(metas, views, tags), cost


def run(folder: str, batch_size: int = 5, limit: int = 0, write: bool = False,
        concurrency: int | None = None) -> list[dict]:
    """自动打标一整个网盘文件夹:diff 去重 → **分批并发**(拉+转码/抽帧 → 看图打标,每图/每批隔离)→ 串行登记 → 清缓存。
    **打标只出客观事实**(类型/来源/备注);适用账号留空(消费=分发选材时决定)。
    并发度默认 config.TAG_CONCURRENCY(护本机负载,上线服务器调高)。**登记串行**=gen_code 序号单调 + feishu 限流。"""
    concurrency = concurrency or config.TAG_CONCURRENCY
    mats = feishu_io.list_records(MF.TABLE)
    seen = _seen_names(mats)
    seen_codes = {bitable.text(r["fields"].get(MF.CODE)).strip() for r in mats}   # 供 gen_code 递增序号
    entries = [e for e in netpan.list_dir(folder) if not e["is_dir"]]
    all_media = [e for e in entries
                 if media.kind(e["name"]) in ("still", "video") and e["name"] not in seen]

    # **跳过了什么,必须说出来**(2026-07-14 走摄影师流程发现):真跑时摄影师往待入库箱传了图,
    # 系统只回一句「试跑 0 条」——**一个字都不解释为什么**。他会懵:"我明明传了啊?"
    # 而跳过有两种,含义完全不同:
    #   · 非图非视频 → 传错文件了(该删)
    #   · 已登记同名 → **危险**:去重键是**纯文件名**,而相机是循环编号(DSC6680.jpg 换张卡就重现),
    #     素材表又没存大小/哈希 → 一批全新的片子只要文件名撞上历史,就会被**静默吞掉**。
    #     待入库箱是中转箱,正常流程里入库后就该清空;箱里躺着"已登记"的文件本身就是异常。
    skipped_dup = [e["name"] for e in entries
                   if media.kind(e["name"]) in ("still", "video") and e["name"] in seen]
    skipped_kind = [e["name"] for e in entries if media.kind(e["name"]) not in ("still", "video")]
    if skipped_kind:
        print(f"  ⏭ 跳过 {len(skipped_kind)} 个非图非视频文件(传错了?):{skipped_kind[:5]}", file=sys.stderr)
    if skipped_dup:
        print(f"  ⚠️ 跳过 {len(skipped_dup)} 个**文件名已登记过**的:{skipped_dup[:5]}\n"
              f"     去重看的是**文件名**。若这些其实是新拍的片子(相机循环编号会撞名!),"
              f"改个名再传,否则会被当成旧素材静默丢掉。\n"
              f"     若确认是旧素材,把它们从待入库箱移走(箱子是中转,入库后就该清空)。", file=sys.stderr)
    # **视频一律收,抽关键帧打标**(2026-07-14 用户确认的设计意图:"视频抽关键帧打标,用这个匹配;
    # 没有加工 gate 就按这个匹配作为视频素材;有 gate 才下载下来看怎么加工")。
    #
    # 修的是这个死循环:原来 GY_INGEST_VIDEO=0 **直接跳过所有视频** → 补拍单催「上身视频×3」、
    # 摄影师拍了传网盘、系统跳过不收、补拍单继续催 —— **人拍了,系统不收,然后继续催他拍**。
    #
    # 我一度改成"按大小拦"(小成片收、大 raw 拒),那也是错的:**拒收不是护本机的正确手段**。
    # 真正的负载问题是 TAG_CONCURRENCY=4 → 4 个 1GB 视频**并发**下载 = 4GB 同时压盘。
    # 正解是**串行**(见下面 `chunk`):一次只下一个,抽完帧立刻删缓存。这既实现了"抽帧打标",
    # 又守住了"别把高负载压用户笔记本"——那条红线要的是串行,不是拒收。
    files = all_media                                        # 静图 + 视频,一律抽帧打标
    vids = [e for e in files if media.kind(e["name"]) == "video"]
    if vids:
        print(f"  🎬 {len(vids)} 个视频:中点抽关键帧 → 看图打标(**串行处理**,一次只拉一个,抽完即删缓存)",
              file=sys.stderr)
    if limit:
        files = files[:limit]
    # **图片并发,视频串行**——护本机的正确手段是"一次只拉一个大文件",不是"拒收视频"。
    # 图:一张几 MB,一批 5 张并发 4 批 = 峰值几十 MB,无压力。
    # 视频:raw 底片 700MB~1GB(真查网盘:EG9A7549.MP4=1007MB)。若跟图一样批 5 并发 4,
    # 峰值 = 20 个 GB 级文件同时下载 → 直接压爆用户笔记本的磁盘和带宽。
    # 所以视频**每批 1 个、并发度 1**:拉一个 → 抽中点关键帧 → 看图打标 → 删缓存 → 拉下一个。
    stills = [e for e in files if media.kind(e["name"]) == "still"]
    videos = [e for e in files if media.kind(e["name"]) == "video"]
    batches = [(stills[k:k + batch_size], concurrency)      # (这批文件, 该用多大并发)
               for k in range(0, len(stills), batch_size)]
    batches += [([v], 1) for v in videos]                    # 视频:一个一批,串行
    out: list[dict] = []
    total_cost = 0.0                                        # 看图成本汇总(冒泡到运行日志→月度成本硬闸)
    chunk = max(1, concurrency)                              # 每 chunk 并发 N 批,跑完统一清缓存(护磁盘)
    for i in range(0, len(batches), chunk):
        group = batches[i:i + chunk]
        # 这一组里只要有视频批(并发度=1),整组就降到串行——绝不让两个 GB 级下载撞在一起
        par = min(concurrency, min(c for _, c in group))
        pairs: list[tuple] = []
        with ThreadPoolExecutor(max_workers=max(1, par)) as ex:   # 打标并发(护本机=并发度低;视频=1)
            for br, cost in ex.map(_tag_one_batch, [b for b, _ in group]):   # 主线程汇总成本,并发安全
                pairs.extend(br)
                total_cost += cost
        for meta, view, tag in pairs:                       # 串行登记:gen_code 序号单调
            mtype = _valid_type(tag.get("类型", ""), meta["kind"])
            source = "AI生成" if (tag.get("来源") == "AI生成") else "实拍"
            code = ing.gen_code(mtype, meta["name"], seen_codes)
            seen_codes.add(code)
            note = _note_of(tag, meta["kind"])
            row = {"code": code, "type": mtype, "source": source, "note": note}
            if write:
                thumb_token = ""
                try:                                        # 顺带生成+上传缩略图(base驾驶舱瞄一眼),失败不拦登记
                    thumb = str(netpan.CACHE / (Path(view).stem + "_thumb.jpg"))
                    media.thumbnail(view, thumb, 400)
                    thumb_token = feishu_io.upload_media(thumb, meta["name"] + ".jpg")
                except Exception as e:  # noqa: BLE001  缩略图失败不拦登记
                    print(f"  ⚠缩略图失败 {code}: {str(e)[:40]}", file=sys.stderr)
                ing.register(code, mtype, meta["ptr"], note, source, thumb_token=thumb_token)
            out.append(row)
            print(f"  {'✓登记' if write else '·试跑'} {code} [{mtype}/{source}] {tag.get('备注','')[:36]}")
        netpan.clear_cache()                                # 每 chunk 清缓存(按需缓存不占地)
    if write and total_cost > 0:                            # 看图成本记运行日志→月度成本硬闸真看得到打标花销
        feishu_io.log_run(summary=f"打标看图 {len(batches)} 批 · {len(out)} 张",
                          action="看图打标", table="素材表", cost=round(total_cost, 4))
    print(f"  看图成本估算 ≈ {round(total_cost, 4)} 元（{config.VISION_BACKEND}，usage实测×费率）", file=sys.stderr)
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
        feishu_io.log_run(summary=f"重标清除老打标行 {len(legacy)} 条(相对路径空,已备份)", action="重标清除", table="素材表")
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
        feishu_io.log_run(summary=f"自动打标入库 {len(res)} 条 · {a.from_netpan}", action="自动打标", table="素材表")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
