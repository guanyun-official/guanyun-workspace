"""素材:**眼睛**(事实)+ **手**(把网盘里的东西变成你能看的)。

拆导轨留下的东西。原来 `draft.py` 里那套「选素材」是 **6 条过滤规则 + 两层排序**
(类型 → 已拍 → 赛道 → 内容寻址 → 少用优先 → 画面别重样),它替模型决定了**配哪几张图**。
那是判断,已删。

这里只剩两件 harness 的本分:

  · `facts()`   —— **把素材摆出来,连同判断所需的一切事实**(类型/来源/画面备注/被引用次数/
                   适用账号/拍摄状态)。**不排序、不打分、不筛掉任何一条**(除非你要的服务端过滤)。
                   挑哪几张、要不要避开重样画面、要不要优先用没用过的 —— **全是 agent 的判断**,
                   知识在技能 `tagging-material` / `selecting-materials` 里。

  · `viewable()` —— 网盘指针 → 拉下来 → 转成**能看的**(HEIC→JPG,视频→中点关键帧)→ 本地路径。
                   **然后 agent 用自己的眼睛看。** harness 不替它看,也不替它说这是什么。
                   (原来是 `vision.see(TAXONOMY prompt)` —— harness 拿着一份分类法去问另一个模型
                    "这是什么类型",再把答案钳到 12 类里。那是**替模型做决策**,连人家的答案都改。)
"""
from __future__ import annotations

from pathlib import Path

from . import bitable, feishu_io, media, netpan
from .bitable import AccountFields as AF, MaterialFields as MF


def _fact(r: dict, acc_names: dict) -> dict:
    """一条素材的**全部事实**(agent 据此判断该不该用它;harness 不替它判)。"""
    f = r["fields"]
    link = f.get(MF.LINK)
    return {
        "id": r["record_id"],
        "编号": bitable.text(f.get(MF.CODE)),
        "类型": bitable.text(f.get(MF.TYPE)),     # **纯内容**:上身/商品/形象/搭配/细节/面料·纹理/工艺/…
        "形态": bitable.text(f.get(MF.FORM)),     # **图 / 视频** —— 独立一维(见 bitable.MaterialForm)
        "来源": bitable.text(f.get(MF.SOURCE)),          # 实拍 / AI生成(AI生成→发布前人必须勾 AI 声明)
        "拍摄状态": bitable.text(f.get(MF.SHOT_STATUS)),
        "备注": bitable.text(f.get(MF.NOTE)),            # 画面事实(谁打的标就是谁看到的画面)=文案的事实底座
        "适用账号": bitable.link_names(f.get(MF.ACCOUNTS), acc_names),   # 空=没归赛道,谁都能用
        # **被引用次数 = 数反向链接,不信 formula**(飞书 formula 对 DuplexLink 恒返 0,已删该字段)。
        # 它是**事实**,给 agent 看:哪些素材被用滥了、哪些还没人用过。
        # 「优先用没用过的」是**判断**,归 agent(知识在技能里),不是这里排个序就替它决定了。
        "被引用次数": len(bitable.link_record_ids(f.get(MF.BACKLINK))),
        "链接": bitable.text(link) if not isinstance(link, dict) else (link.get("link") or ""),
        "指针": bitable.text(f.get(MF.REL_PATH)),        # baidupan:/… 耐久指针(viewable() 吃它)
    }


def facts(types: list[str] | None = None, status: str = "", account: str = "",
          form: str = "") -> list[dict]:
    """素材事实清单。types 给定 → **服务端过滤**(不全表拉,规模护栏)。
    status / account / form 是**事实过滤**(拍摄状态=已拍 / 适用账号含某号 / 形态=视频),
    不是选择 —— **过滤 ≠ 替你挑**。

    ⚠️ 这里**不排序**。原来按「被引用次数升序」排(少用优先),那是替 agent 决定先看谁。
    现在按表序原样给,被引用次数作为**一列事实**摆在那 —— 要不要避开用滥的,你自己看。"""
    rows = feishu_io.search_in(MF.TABLE, MF.TYPE, types) if types else feishu_io.list_records(MF.TABLE)
    acc_names = feishu_io.name_map(AF.TABLE, AF.NAME)
    out = [_fact(r, acc_names) for r in rows]
    if status:
        out = [m for m in out if m["拍摄状态"] == status]
    if form:
        out = [m for m in out if m["形态"] == form]
    if account:
        # 显式标了别的号 = 排除;**没标 = 可用**(打标时不填适用账号,消费时才决定)
        out = [m for m in out if (not m["适用账号"]) or account in m["适用账号"]]
    return out


def by_ids(ids: list[str]) -> list[dict]:
    """按 record_id 取素材事实(按 id 取单条,不全表扫)。保持传入顺序。"""
    acc_names = feishu_io.name_map(AF.TABLE, AF.NAME)
    out = []
    for rid in ids:
        r = feishu_io.get_record(MF.TABLE, rid)
        if r:
            r.setdefault("record_id", rid)
            out.append(_fact(r, acc_names))
    return out


def registered_names() -> set[str]:
    """已登记素材的**网盘文件名**集合 —— 打标去重的**事实**(不是决定)。

    给 agent 看,让它自己判断:待入库箱里这个文件是不是已经收过了。
    ⚠️ 去重键是**纯文件名**,而相机是循环编号(DSC6680.jpg 换张卡就重现)——
    同名 ≠ 同一张片子。所以这里只报事实『同名的已登记过』,**要不要跳过由 agent 判**。
    (老实现是直接静默跳过 → 一批新片只要撞名就被吞掉,没人知道。)"""
    seen: set[str] = set()
    for r in feishu_io.list_records(MF.TABLE):
        f = r["fields"]
        seen.add(bitable.text(f.get(MF.LINK)).strip())
        rp = bitable.text(f.get(MF.REL_PATH)).strip()
        if rp:
            path = netpan.pointer_path(rp) if rp.startswith(netpan.POINTER_SCHEME) else rp
            seen.add(Path(path).name)
    seen.discard("")
    return seen


def used_codes() -> set[str]:
    """已用的素材编号(gen_code 递增序号用)。"""
    return {bitable.text(r["fields"].get(MF.CODE)).strip() for r in feishu_io.list_records(MF.TABLE)}


def inbox(folder: str = "") -> dict:
    """待入库箱(或指定网盘目录)现在有什么 —— **事实**,不做任何取舍。

    每个文件报:名字 / 形态(still·video·other)/ **是否已登记过同名的**。
    跳过什么、收什么,**agent 自己判**(老实现替它判了:非图非视频静默跳、同名静默吞)。"""
    seen = registered_names()
    entries = [e for e in netpan.list_dir(folder or netpan.INBOX) if not e["is_dir"]]
    return {
        "目录": folder or netpan.INBOX,
        "文件": [{"名字": e["name"], "路径": e["path"], "形态": media.kind(e["name"]),
                  "已登记过同名": e["name"] in seen} for e in entries],
    }


def viewable(remote_paths: list[str], frames: int = 5) -> list[dict]:
    """网盘路径 → 拉下来 → 转成**你能看的本地文件**,**然后你用自己的眼睛看**(Read 那些路径)。
    harness 到此为止 —— 它不告诉你画面里是什么。

    · 静图(含 HEIC/LIVP)→ 一张 jpg
    · **视频 → 均匀抽 `frames` 帧,每帧一个文件,标明第几秒**

    ★视频为什么给你多帧★
      **一帧不是整条视频**,而且"哪一帧能代表这条视频"**本身就是判断,不该由 harness 替你做**。
      库里唯一那条上身视频就是活教训:它被中点那一帧(恰好是个局部特写)代表了,
      备注写成「浅粉色…衣身局部特写」—— **一条上身视频,在系统眼里成了一张特写**。
      补拍单照它去催摄影师"拍上身视频",给的参考却是个特写,人当场懵。

      现在:帧分开给你,你**自己看完这几帧,自己综合出"这条视频是什么"**。
      看不清就要更多帧(`--frames N`)。

    ⚠️ **登记的时候,登记的是这条视频本身**(一条素材,类型=视频类,指针指向 .MP4),
       **不是把每一帧都登记成一张图**。帧只是你用来看懂它的眼睛,不是素材。

    ★视频的下载纪律(物理约束,不是设计选择)★
      百度网盘**没有 range 请求**(实测直链外部被拒 403/503)→ **要看到画面就必须下整包**。
      raw 底片实测 median 511MB / 单条最大 1007MB。所以:

        · **一次只下一个**(视频串行,绝不并发 —— 4 个 GB 级文件同时下会压爆用户笔记本)
        · **抽完帧,原件当场删**,只留下几张几十 KB 的 jpg  ← 峰值 = 一条视频,不是全部
        · **之后再也不下**:选材/出稿看『备注』(画面事实)+ base 里的缩略图,不碰原件。
          只有真要**加工**(剪辑/拼接,那时才真要动像素)才再下一次。
    """
    out = []
    for rp in remote_paths:
        path = netpan.pointer_path(rp) if rp.startswith(netpan.POINTER_SCHEME) else rp
        local = netpan.pull(path, netpan.CACHE)
        kind = media.kind(local)
        if kind == "video":
            fs = media.video_frames(local, str(netpan.CACHE), frames)
            size_mb = round(Path(local).stat().st_size / 1e6, 1) if Path(local).exists() else 0
            dur = media.duration(local)
            Path(local).unlink(missing_ok=True)   # ★抽完帧,GB 级原件当场删★ 只留几张 jpg
            if not fs:
                out.append({"路径": path, "名字": Path(path).name, "形态": "video",
                            "错": "一帧都抽不出来 —— 这条视频看不了(文件坏了?)"})
                continue
            out.append({"路径": path, "名字": Path(path).name, "形态": "video",
                        "时长秒": round(dur, 2) or None, "原件MB": size_mb,
                        "帧": fs,          # [{本地, 秒}] —— **你 Read 这几个路径,自己看**
                        "怎么用": f"这是同一条视频的 {len(fs)} 帧(视频本身 {dur:.1f} 秒)。"
                                  f"**综合起来判断整条视频是什么**,别只描述其中一帧。"
                                  f"登记的是这条**视频**(类型=视频类,指针指向 .MP4),"
                                  f"缩略图用你觉得最能代表它的那一帧(`--thumb-from <帧路径>`)。",
                        "注意": "原件已删,只留帧(网盘无 range,看画面必须下整包;下完就删,不占你的盘)。"
                                "要再看就再调一次。"})
            continue
        view = media.to_jpg(local, str(netpan.CACHE)) if media.needs_jpg(local) else local
        if not Path(view).exists():
            out.append({"路径": path, "名字": Path(path).name,
                        "错": "转码没产出(视图缺失)—— 这个文件看不了"})
            continue
        out.append({"路径": path, "名字": Path(path).name, "本地": view, "形态": kind})
    return out


def thumb_token(view_path: str, name: str) -> str:
    """给素材做个缩略图传进飞书(base 驾驶舱里人瞄一眼就选材,不用点开网盘)。失败返 ""(不拦登记)。"""
    try:
        thumb = str(netpan.CACHE / (Path(view_path).stem + "_thumb.jpg"))
        media.thumbnail(view_path, thumb, 400)
        return feishu_io.upload_media(thumb, name + ".jpg")
    except Exception:  # noqa: BLE001  缩略图不是命根子,失败不拦登记
        return ""
