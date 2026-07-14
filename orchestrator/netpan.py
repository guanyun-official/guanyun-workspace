"""百度网盘(媒体唯一真身仓,「媒体唯一真身仓=网盘」)—— **它的手**。

BaiduPCS-Go 的 subprocess seam:列目录 / 按需拉一个 / 回传 / mint 分享链接。
**不做全盘镜像** —— agent 要哪条拉哪条。纯函数(指针/解析)与 IO(_run)分离。

**没有 stub 模式**:没登录就炸(NetpanError),**绝不静默返回空**。
真跑需人工一次 `BaiduPCS-Go login -bduss=<BDUSS>`;BDUSS 会过期。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import config

# ★没有 stub 模式★(2026-07-14 架构审查删)
# 老实现:`MODE = os.environ.get("GY_NETPAN_MODE", "stub")`,而 `list_dir()` 在非 real 下
# **静默返回 []** —— 服务器上少配一行 env,「待入库箱」就**永远是空的,而且不报错**。
# 摄影师传了片子,系统说"箱子里没东西"。这就是"把读不到变成 0"。
# 死规矩:**不搞 mock、不搞 stub。** 网盘没登录就**炸**,别假装箱子是空的。
BIN = os.environ.get("GY_NETPAN_BIN", "BaiduPCS-Go")        # CLI 可执行名/路径
ROOT = os.environ.get("GY_NETPAN_ROOT", "/巧荷素材")        # 网盘素材根(投递+归档)
INBOX = f"{ROOT}/待入库"   # 人拍完/AI生成后统一往这丢的单一扁平投递箱(别人好弄+容错;归类交打标技能事后做)
CACHE = Path(os.environ.get("GY_NETPAN_CACHE", str(config.WORKSPACE / ".netpan_cache")))
POINTER_SCHEME = "baidupan:"   # 素材记录『链接』存的耐久指针(网盘路径,不过期);分享链接用时再 mint


class NetpanError(RuntimeError):
    """网盘操作失败(没登录 / BDUSS 过期 / 网盘挂了)。message 面向告警可读。"""


# ── 纯函数:指针 <-> 路径、CLI 输出解析(零 IO,可测) ──────────────────────

def pointer(remote_path: str) -> str:
    """网盘路径 → 耐久指针串(素材『链接』字段存这个)。不存分享链接(会过期),用时 mint。"""
    return f"{POINTER_SCHEME}{remote_path}"


def pointer_path(s: str) -> str:
    """指针串 → 网盘路径(逆 pointer)。非本方案指针(file://http…)原样返回。"""
    return s[len(POINTER_SCHEME):] if s.startswith(POINTER_SCHEME) else s


def _parse_ls(base: str, out: str) -> list[dict]:
    """BaiduPCS-Go `ls` 输出 → [{name, path, size, is_dir}](纯解析,真跑按实际输出校准)。
    典型行:  『  1      1.5MB    2020-01-01 00:00:00   照片.jpg 』;目录名以 / 结尾。
    容错:跳过表头/分隔/统计行;认不出的行忽略而非炸(增量 diff 宁可漏不可错)。"""
    items: list[dict] = []
    base = base.rstrip("/")
    for line in out.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        # 取行尾文件名:表格最后一列。表头/统计行没有像文件名的尾段,靠下面判据过滤
        m = re.match(r"\s*\d+\s+(\S.*?\S|\S)\s{2,}\d{4}-\d{2}-\d{2}[ \d:]+\s+(.+)$", line)
        if not m:
            continue
        size_raw, name = m.group(1).strip(), m.group(2).strip()
        is_dir = name.endswith("/")
        name = name.rstrip("/")
        if not name:
            continue
        items.append({"name": name, "path": f"{base}/{name}",
                      "size": 0 if size_raw == "-" else size_raw, "is_dir": is_dir})
    return items


def _parse_share(out: str) -> str:
    """BaiduPCS-Go `share set` 输出 → 分享链接(带提取码则拼 ?pwd=)。认不出返 ''。"""
    link = ""
    pwd = ""
    lm = re.search(r"https?://pan\.baidu\.com/\S+", out)
    if lm:
        link = lm.group(0).rstrip("，。,. ")
    pm = re.search(r"(?:提取码|pwd|密码)[:：\s]*([0-9a-zA-Z]{4})", out)
    if pm:
        pwd = pm.group(1)
    if link and pwd and "pwd=" not in link:
        link = f"{link}{'&' if '?' in link else '?'}pwd={pwd}"
    return link


# ── IO seam:唯一真调用点,stub 一律挡在门外 ───────────────────────────────

def _run(args: list[str]) -> str:
    """BaiduPCS-Go subprocess seam(唯一真调用点,可 mock)。stub 绝不真跑。"""
    r = subprocess.run([BIN, *args], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise NetpanError(f"BaiduPCS-Go {args[:1]} 失败(rc={r.returncode}): {r.stderr[:200]}")
    return r.stdout


def list_dir(remote_path: str = "") -> list[dict]:
    """列网盘目录。返回 [{name, path, size, is_dir}]。
    **没登录/网盘挂了 → 炸**(NetpanError),**绝不静默返回 []** —— 那会让"箱子是空的"和
    "我看不见箱子"变成同一句话,而摄影师明明传了片子。"""
    path = remote_path or ROOT
    return _parse_ls(path, _run(["ls", path]))


def pull(remote_path: str, dest: Path | None = None) -> str:
    """按需拉一个网盘文件到本地缓存。返回本地路径。

    ★★ 缓存必须按**完整远端路径**落盘,绝不能按文件名 ★★
    (2026-07-14 数字生命上班时抓到 —— **这是整个系统里最毒的一个 bug**)

    老实现:`download <远端路径> --saveto <CACHE>` → 落成 `CACHE/<basename>`,返回那个路径。

    真跑复现:

        /巧荷素材/待入库/二次_DSC6680.jpg        5,308,416 字节(而且是**截断的坏图**,下半张全灰)
        /巧荷/图片底片剪裁/二次_DSC6680.jpg     17,358,046 字节(完整的那张)

    **两个完全不同的文件,同一个 basename。** 第一次下 A → 落 `CACHE/二次_DSC6680.jpg`;
    第二次拉 B → BaiduPCS-Go 看见同名文件**直接跳过下载**,`pull` **把 A 原样返回给你** ——
    返回值里 `形态: still`、路径正常、**退出码 0**。

    后果:**它会对着 A 的图,写 B 的文案。**
    而"货不对板"正是这个系统花了两次事故去防的东西 —— 备注写得再准也挡不住,**根子在工具里**。
    (相机是循环编号,`DSC6680.jpg` 这种名字在不同批次里**必然重现**。)

    现在:每个远端路径落进**自己的子目录**(路径 hash),物理上撞不了名。
    """
    import hashlib
    d = dest or CACHE
    # 用远端路径的 hash 做子目录 —— **同名不同源的文件再也不会互相覆盖**
    sub = d / hashlib.sha1(remote_path.encode("utf-8")).hexdigest()[:12]
    sub.mkdir(parents=True, exist_ok=True)
    local = sub / Path(remote_path).name
    if not local.exists():
        _run(["download", remote_path, "--saveto", str(sub)])
    if not local.exists():
        raise NetpanError(f"下下来了但文件不在:{local}(网盘路径:{remote_path})")
    return str(local)


def upload(local_path: str, remote_dir: str) -> str:
    """回传本地文件到网盘(加工产物落 03-成片/)。返回网盘路径。"""
    _run(["upload", local_path, remote_dir])
    return f"{remote_dir.rstrip('/')}/{Path(local_path).name}"


def cache_usage_mb(cache: Path | None = None) -> float:
    """当前本地缓存占用(MB)。本地是按需临时缓存,应保持很小。"""
    d = cache or CACHE
    if not d.exists():
        return 0.0
    total = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
    return round(total / 1024 / 1024, 2)


def clear_cache(cache: Path | None = None) -> float:
    """清空本地缓存(处理完一批就清——原件在网盘,本地 copy 用完即删,不占地)。返回释放的 MB。"""
    import shutil
    d = cache or CACHE
    freed = cache_usage_mb(d)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return freed


def share_link(remote_path: str) -> str:
    """给网盘文件 mint 分享链接(**人点开就能看到那张图/那条视频**;用时 mint 不入库,避免过期)。
    mint 不出来 → 退回耐久指针串(**语义不误导**:那不是个能点的链接,但也不是假链接)。"""
    return _parse_share(_run(["share", "set", remote_path])) or pointer(remote_path)


def take_link(link: str) -> str:
    """人取素材的可开链接(发布态用):网盘耐久指针 → 用时 mint 分享链接;本地 file://、其它 URL → 原样。
    这样 待发布 时人拿到的是能点开的素材地址,而库里存的是不过期的指针(分享链接不入库)。"""
    if link.startswith(POINTER_SCHEME):
        return share_link(pointer_path(link))
    return link
