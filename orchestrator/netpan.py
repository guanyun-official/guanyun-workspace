"""百度网盘薄桥(媒体字节唯一真身仓的 IO 边界)。ADR-0004:网盘=真身仓、本地=按需缓存、链接存耐久指针。

薄执行器同 llm/collect:一个 subprocess seam(BaiduPCS-Go)+ stub 零真操作。
- **stub(默认)**:零真操作——list 返空、pull/upload 拒绝、share 退化成指针串。离线测试/verify 不触网、不需 BDUSS。
- **real**:走 BaiduPCS-Go(全盘/BDUSS),真跑需先 `login -bduss=…`(凭证人工,机器不碰)。

只读/按需拉/回传/mint 分享链接;**不做全盘镜像**——agent 要哪条拉哪条。纯函数(pointer/解析)与 IO(_run)分离,前者可测,后者 stub 挡住。
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import config

MODE = os.environ.get("GY_NETPAN_MODE", "stub")            # stub 零真操作 / real 走 BaiduPCS-Go
BIN = os.environ.get("GY_NETPAN_BIN", "BaiduPCS-Go")        # CLI 可执行名/路径
ROOT = os.environ.get("GY_NETPAN_ROOT", "/观云素材")        # 网盘素材根(投递+归档)
INBOX = f"{ROOT}/待入库"   # 人拍完/AI生成后统一往这丢的单一扁平投递箱(别人好弄+容错;归类交打标技能事后做)
CACHE = Path(os.environ.get("GY_NETPAN_CACHE", str(config.WORKSPACE / ".netpan_cache")))
POINTER_SCHEME = "baidupan:"   # 素材记录『链接』存的耐久指针(网盘路径,不过期);分享链接用时再 mint


class NetpanError(RuntimeError):
    """网盘操作失败/被 stub 拒绝。message 面向告警可读。"""


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
    if MODE != "real":
        raise NetpanError(f"netpan MODE={MODE}(非 real):拒绝真操作 {args[:1]}")
    r = subprocess.run([BIN, *args], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise NetpanError(f"BaiduPCS-Go {args[:1]} 失败(rc={r.returncode}): {r.stderr[:200]}")
    return r.stdout


def logged_in() -> bool:
    """BDUSS 是否有效(增量入库前置)。stub 恒 False(无真登录);过期→cron 该告警重登(凭证人工)。"""
    if MODE != "real":
        return False
    try:
        out = _run(["who"])
    except NetpanError:
        return False
    return bool(re.search(r"uid|用户名|用户ID", out))


def list_dir(remote_path: str = "") -> list[dict]:
    """列网盘目录(增量 diff 用)。stub 返 []。返回 [{name, path, size, is_dir}]。"""
    if MODE != "real":
        return []
    path = remote_path or ROOT
    return _parse_ls(path, _run(["ls", path]))


def pull(remote_path: str, dest: Path | None = None) -> str:
    """按需拉一个网盘文件到本地缓存(要编辑/分析才拉,不镜像全盘)。返回本地路径。stub 拒绝。"""
    d = dest or CACHE
    d.mkdir(parents=True, exist_ok=True)
    _run(["download", remote_path, "--saveto", str(d)])   # stub 在 _run 里抛
    return str(d / Path(remote_path).name)


def upload(local_path: str, remote_dir: str) -> str:
    """回传本地文件到网盘(AI 成片/加工产物落 03-成片/)。返回网盘路径。stub 拒绝。"""
    _run(["upload", local_path, remote_dir])              # stub 在 _run 里抛
    return f"{remote_dir.rstrip('/')}/{Path(local_path).name}"


def share_link(remote_path: str) -> str:
    """给网盘文件 mint 分享链接(发布态给人取素材;用时 mint 不入库,避免过期)。
    stub 退化成耐久指针串(离线可用、语义不误导)。"""
    if MODE != "real":
        return pointer(remote_path)
    return _parse_share(_run(["share", "set", remote_path])) or pointer(remote_path)


def take_link(link: str) -> str:
    """人取素材的可开链接(发布态用):网盘耐久指针 → 用时 mint 分享链接;本地 file://、其它 URL → 原样。
    这样 待发布 时人拿到的是能点开的素材地址,而库里存的是不过期的指针(ADR-0004:分享链接不入库)。"""
    if link.startswith(POINTER_SCHEME):
        return share_link(pointer_path(link))
    return link
