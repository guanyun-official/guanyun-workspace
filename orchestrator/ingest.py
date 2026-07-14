"""素材登记原子(Tools · 它的手)。**零判断**:类型/来源/备注由 agent 看图后自己给,这里只负责落库。

原本住在 `scripts/ingest.py`,和一条导轨(`tag_materials.py` 的 12 类分类法 + 类型钳制)住在一起。
现在导轨拆了,登记原子归位到 harness —— **全景图里没有"脚本"这一层**。

**这里绝不判断"这张图是什么"**(那是 agent 看图的事)。它只做三件确定性的事:
  · gen_code   —— 按类型+批次日期生成可排序的素材编号(纯机械)
  · register   —— 写素材表一行(过红线门)
  · store_produced —— 加工产物回传网盘 03-成片 + 登记(provenance 焊死)
"""
from __future__ import annotations

import re
from pathlib import Path

from . import feishu_io, netpan
from .bitable import MaterialFields as MF
from .bitable import MaterialSource as MSrc
from .bitable import MaterialStatus as MS


def _as_pointer(link_path: str) -> str:
    """素材『相对路径』值:已是指针/URL 原样;裸本地路径→file://(向后兼容本地样片)。
    网盘素材传 netpan.pointer(远端路径)=耐久指针;分享链接用时再 mint,不入库。"""
    if "://" in link_path or link_path.startswith(netpan.POINTER_SCHEME):
        return link_path
    return f"file://{link_path}"


def _resolve_link(link_path: str) -> str:
    """素材『链接』**存能点开的值**:网盘指针(real 模式)→ mint 永久分享链接(投手一点直达该图/视频);
    本地/stub → 退化成指针/file://。失败兜底存指针(不丢)。"""
    if link_path.startswith(netpan.POINTER_SCHEME):
        try:
            return netpan.share_link(netpan.pointer_path(link_path))   # 永久分享(share set --period 0)
        except netpan.NetpanError:
            return link_path
    return _as_pointer(link_path)


# 系统编码前缀:素材表『类型』各一(拼音缩写,互不撞;沿用旧值不破坏已入库编号)。
# **这是 schema 常量(Knowledge),不是分类法** —— "这份素材是什么"由 agent 看图判断
# (判据在技能 `tagging-material` 里,那是唯一真源)。这里只回答"这一类的编号前缀是什么"。
# 认不出的类型 → SC(素材),**绝不冒充别的类**。
#
# 2026-07-14 词汇归位:『类型』= **纯内容**(名字里不许再带"图"/"视频"——那是形态,归『形态』字段)。
# 旧值 上身图/上身视频 → 上身;商品图 → 商品;制作过程视频 → 制作过程;面料·纹理特写 → 面料·纹理…
# 为什么:见 bitable.MaterialForm 的注释(一个字段的形状不对,凭空造出过一条不存在的库存)。
_TYPE_PREFIX = {
    "上身": "ST", "商品": "SP", "形象": "XX", "细节": "XJ", "搭配": "DP",
    "面料·纹理": "ML", "工艺": "GY", "制作过程": "ZZ",
    "空镜·场景": "KJ", "文物原件": "WW", "文物对照": "WD",
}

MATERIAL_TYPES = tuple(_TYPE_PREFIX)   # 素材表『类型』select 的合法值(世界的事实,board 报给 agent 看)


def _batch_date(name: str) -> str:
    """从文件名抽拍摄批次日期 YYMMDD(如 '2026-07-02 175646.heic'→'260702');抽不到用 000000。"""
    m = re.search(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})", name)
    return f"{m.group(1)[2:]}{m.group(2)}{m.group(3)}" if m else "000000"


def gen_code(mtype: str, name: str, existing: set) -> str:
    """系统化素材编号 <类型>-<批次日期>-<序号>(如 ST-260702-001)。可排序、不混。
    existing=已用编号集合,同(类型,批次)取最大序号+1;调用方每登记一个把返回值加进 existing。"""
    pre = _TYPE_PREFIX.get(mtype, "SC")   # 未知类型→SC(素材),不冒充形象图 XX
    date = _batch_date(name)
    stem = f"{pre}-{date}-"
    nums = [int(m.group(1)) for c in existing if (m := re.match(rf"^{pre}-{date}-(\d+)$", c))]
    return f"{stem}{(max(nums) + 1 if nums else 1):03d}"


def register(code: str, mtype: str, link_path: str, note: str = "",
             source: str = MSrc.REAL, accounts: list | None = None,
             thumb_token: str = "", form: str = "") -> str:
    """登记一条素材进素材表(素材按赛道存,不挂衣服)。字段归位:
    - 链接(url)= 能点开的分享链(投手一点直达);相对路径(text)= 系统耐久指针(baidupan:/...),寻址用。
    ⚠️ 没有『生成参数』字段了(0/280,**从来没有任何调用方传过它**)——
      AI 像素的 provenance 由『来源=AI生成』承载,生成提示词写进『备注』。
    accounts=适用账号 record_id 列表——**打标时留空**(消费在分发选材时决定并回填)。

    ★合规红线:来源由**落点/元数据**定,不靠视觉猜★(漏判 AI → 漏勾 AI 声明 = 合规硬伤)。
    素材落在 02-AI生成/ 目录 或 带生成参数 → **强制** AI生成(就低不就高,宁可让人往下摘)。
    agent 看图说"实拍"也覆盖不掉这条 —— 它是法律,不是判断。"""
    if "02-AI生成" in link_path or "/AI生成/" in link_path:
        source = MSrc.AI
    # **形态由文件本身定,不猜也不问**(.MP4 就是视频,.jpg 就是图 —— 这是事实,不是判断)。
    # 显式传了就用传的(段素材等特殊情况);没传就从扩展名推。
    from . import media
    from .bitable import MaterialForm as MFm
    if not form:
        k = media.kind(netpan.pointer_path(link_path) if link_path.startswith(netpan.POINTER_SCHEME)
                       else link_path)
        form = {"video": MFm.VIDEO, "still": MFm.IMAGE}.get(k, "")
    fields = {
        MF.CODE: code,
        MF.TYPE: mtype,        # **纯内容**(上身/商品/面料·纹理…),agent 看图判的
        MF.LINK: {"link": _resolve_link(link_path), "text": Path(netpan.pointer_path(link_path)).name},
        MF.REL_PATH: _as_pointer(link_path),   # 系统指针(text 字段,不被 url 改写)
        MF.SHOT_STATUS: MS.SHOT,
        MF.SOURCE: source,
        MF.NOTE: note,
    }
    if form:
        fields[MF.FORM] = form   # 图 / 视频 —— 从文件形态推,**不再靠"视频文件强制落视频类"那条钳制**
    if thumb_token:
        fields[MF.THUMB] = [{"file_token": thumb_token}]   # 缩略图(附件),base 驾驶舱瞄一眼
    if accounts:
        fields[MF.ACCOUNTS] = accounts
    return feishu_io.create_record(MF.TABLE, fields)   # feishu_io 内部过 assert_base_allowed(只写测试库)


def store_produced(local_path: str, mtype: str, source: str = MSrc.AI, note: str = "",
                   accounts: list | None = None, remote_dir: str | None = None) -> tuple[str, str]:
    """加工产出(拼图/AI 封面/成片)**回传网盘 03-成片** + 登记素材。
    **来源随像素出处**:纯剪辑实拍=`实拍`(免声明)、含 AI 合成=`AI生成`(需声明)——调用方按事实传 source。
    需 netpan real+STOKEN(写)。返回 (record_id, 网盘耐久指针)。"""
    remote = remote_dir or f"{netpan.ROOT}/03-成片"
    remote_path = netpan.upload(local_path, remote)   # 真上传(写,需 STOKEN)
    ptr = netpan.pointer(remote_path)
    rid = register(Path(local_path).stem, mtype, ptr, note, source, accounts)
    return rid, ptr
