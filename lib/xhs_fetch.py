"""
xhs_fetch.py — 「取数口」(CONTEXT.md):读小红书的**统一收口**,与飞书工位对称(工位收"往哪写",这收"从哪取")。

对外只两个:`account(ident)` / `note(ref)` → **统一契约 dict**(+ `data_gaps` + `provenance` 每字段来源)。
背后多个 **adapter**(redfox / apify(socialdatax) / browser(小号) / mock),按 `.env` 的 **`XHS_FETCH_CHAIN`**
(默认 `apify,redfox,browser`)**逐字段合并**:按链序,先到的非空值占位,后面的只补空缺。一个源都不弃用。
**零封号**:redfox/apify 不用我方账号;browser=专用小号兜底(有封号风险)。换源/排序 = 改一行 env。

统一契约:
  account → {account_name, account_url, red_id, followers, avg_liked, total_works, note_count_30d,
             account_attribute, bio, audience:{gender}, recent_notes:[{title,liked,collected,comments,url,...}],
             representative_notes, note_texts, data_gaps, provenance}
  note    → {source_text(正文全文), title_raw, author, metrics:{liked,collected,comments,shared},
             cover_url, ip_location, topic_tags, image_count, url, data_gaps, provenance}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(WORKSPACE / "lib"))
import apify_xhs  # noqa: E402  零封号 Apify(socialdatax)统一入口

DEFAULT_CHAIN = ["apify", "redfox", "browser"]
REDFOX_QUERY = "https://redfox.hk/story/api/xhsUser/query"


def _find_collector() -> Path:
    """browser adapter 的采集脚本 collect.mjs 定位(迁移自 AI-marketing 的耦合点):
    1) env XHS_COLLECTOR_SCRIPT 显式指定;
    2) 本仓库 skills/xhs-collector/(若日后装进 skills.lock);
    3) 回落 AI-marketing 源仓库(xhs-collector 尚未迁出,P3 拆分时归位)。
    找不到也不报错——browser adapter 会因 COLLECTOR.exists()=False 自动跳过。"""
    env_p = os.environ.get("XHS_COLLECTOR_SCRIPT", "")
    candidates = [Path(env_p).expanduser()] if env_p else []
    candidates += [
        WORKSPACE / "skills" / "xhs-collector" / "scripts" / "collect.mjs",
        Path.home() / "Githubs" / "AI-marketing" / "skills" / "xhs-collector" / "scripts" / "collect.mjs",
    ]
    return next((p for p in candidates if p.exists()), candidates[-1])


COLLECTOR = _find_collector()
_EMPTY = (None, "", [], {})


def _env(k: str, default: str = "") -> str:
    v = os.environ.get(k, "")
    if not v:
        f = WORKSPACE / ".env"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{k}="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
    return v or default


def _chain() -> list:
    v = _env("XHS_FETCH_CHAIN")
    return [a.strip() for a in v.split(",") if a.strip()] if v else list(DEFAULT_CHAIN)


def _cn_num(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v or "").strip().replace(",", "").replace("+", "").replace("约", "").replace(" ", "")
    if not s:
        return 0
    try:
        if s.endswith("万"):
            return int(float(s[:-1]) * 10_000)
        if s.endswith("亿"):
            return int(float(s[:-1]) * 100_000_000)
        return int(float(s))
    except ValueError:
        return 0


def _bare_profile(u: str) -> str:
    m = re.search(r"/user/profile/([0-9a-zA-Z]+)", u or "")
    return f"https://www.xiaohongshu.com/user/profile/{m.group(1)}" if m else (u or "")


def _ident(x) -> dict:
    """str → {url / nickname / red_id}(链接优先;统一都给链接)。dict 原样。"""
    if isinstance(x, dict):
        return x
    s = str(x or "").strip()
    if "xiaohongshu.com" in s:
        return {"url": s}            # 主页/笔记链接(保留 token 给 browser/apify)
    if re.fullmatch(r"[0-9]{4,}", s):
        return {"red_id": s}
    return {"nickname": s}


# ───────────────────────── redfox adapter(仅账号;需昵称/redId)─────────────────────────
def _redfox_account(ident: dict, rec: dict) -> dict:
    key = _env("REDFOX_API_KEY")
    if not key:
        return {}
    name = rec.get("account_name") or ident.get("nickname")   # 红狐认昵称/redId,不认主页URL
    redid = ident.get("red_id") or rec.get("red_id")
    if not (name or redid):
        return {}
    body = {"userIds": [redid]} if redid else {"nicknames": [name]}
    try:
        r = subprocess.run(["curl", "-sS", "--noproxy", "*", "--max-time", "40", "-X", "POST", REDFOX_QUERY,
                            "-H", "Content-Type: application/json", "-H", f"X-API-KEY: {key}",
                            "-d", json.dumps(body, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=50)
        d = json.loads(r.stdout[r.stdout.find("{"):])
    except Exception:  # noqa: BLE001
        return {}
    data = d.get("data")
    a = (data[0] if isinstance(data, list) and data else data) or {}
    if not isinstance(a, dict) or not a.get("nickname"):
        return {}
    # 昵称模糊查询防串号:按昵称查时必须精确匹配(红狐 nicknames 是模糊的)
    if name and not redid and a.get("nickname") != name:
        return {}
    g = a.get("fansGender") or {}
    out = {
        "account_name": a.get("nickname", ""),
        "red_id": str(a.get("redId", "")),
        "followers": _cn_num(a.get("fans")),
        "total_works": _cn_num(a.get("totalWork")),
        "note_count_30d": _cn_num(a.get("noteCountThirty")),
        "interactive_30d": _cn_num(a.get("interactiveCountThirty")),
        "account_attribute": a.get("userAttribute", ""),
        "bio": a.get("desc", ""),
        # 红狐画像只取性别可信;省份/年龄模板化不可信 → 弃(见 data-source-skill-alignment)
        "audience": {"gender": g} if g else {},
    }
    return {k: v for k, v in out.items() if v not in _EMPTY}


# ───────────────────────── apify(socialdatax)adapter ─────────────────────────
def _apify_account(ident: dict, rec: dict) -> dict:
    url = ident.get("url")
    if not url:
        return {}
    n = int(_env("XHS_RECENT", "5") or 5)
    items, err = apify_xhs.run("list_user_notes", profile_url=url, max_items=n, auto_paginate=True)
    if err or not items:
        return {}
    notes = [{"id": it.get("note_id", ""), "title": it.get("title", ""),
              "liked": _cn_num(it.get("like_count")), "collected": _cn_num(it.get("collect_count")),
              "comments": _cn_num(it.get("comment_count")), "url": it.get("note_url") or ""}
             for it in items if isinstance(it, dict) and it.get("title")]
    likes = [x["liked"] for x in notes if x["liked"]]
    avg = round(sum(likes) / len(likes), 1) if likes else 0
    out = {
        "account_name": items[0].get("author_name", ""),
        "account_url": _bare_profile(url),
        "avg_liked": avg,
        "recent_notes": notes,
        "representative_notes": [x["url"] for x in sorted(notes, key=lambda z: z["liked"], reverse=True)[:3] if x["url"]],
        "note_texts": "\n".join(x["title"] for x in notes),
    }
    return {k: v for k, v in out.items() if v not in _EMPTY}


def _apify_note(ref: dict, rec: dict) -> dict:
    url = ref.get("url")
    if not url:
        return {}
    items, err = apify_xhs.run("get_note_detail", note_url=url)
    if err or not items:
        return {}
    n = items[0]
    if not (n.get("content") or n.get("title")):
        return {}
    out = {
        "source_text": n.get("content", ""),
        "title_raw": n.get("title", ""),
        "author": n.get("author_name", ""),
        "metrics": {"liked": _cn_num(n.get("like_count")), "collected": _cn_num(n.get("collect_count")),
                    "comments": _cn_num(n.get("comment_count")), "shared": _cn_num(n.get("share_count"))},
        "cover_url": n.get("cover_image_url", ""),
        "ip_location": n.get("ip_location", ""),
        "topic_tags": [t.get("name") for t in (n.get("topic_tags") or []) if isinstance(t, dict)],
        "image_count": len(n.get("image_items") or []),
        "url": n.get("note_url") or url,
    }
    return {k: v for k, v in out.items() if v not in _EMPTY}


# ───────────────────────── browser adapter(collect.mjs · 专用小号兜底)─────────────────────────
def _collect(mode: str, arg: str, count: int = 20) -> dict:
    if not COLLECTOR.exists():
        return {}
    try:
        p = subprocess.run(["node", str(COLLECTOR), mode, arg, str(count)],
                           capture_output=True, text=True, timeout=120, cwd=str(COLLECTOR.parent))
        return json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 and p.stdout.strip() else {}
    except Exception:  # noqa: BLE001
        return {}


def browser_login() -> dict:
    """引导小号登录:跑 collect.mjs login —— 连采集 Chrome 并打开小红书;没登录就把登录页
    留在那个窗口给小号扫码。返回 {chrome_up, logged_in, hint}。供 fetch 脚本在浏览器取空时调用。"""
    if not COLLECTOR.exists():
        return {"chrome_up": False, "logged_in": False, "hint": "采集器缺失"}
    try:
        p = subprocess.run(["node", str(COLLECTOR), "login"], capture_output=True, text=True,
                           timeout=80, cwd=str(COLLECTOR.parent))
        d = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
        return {"chrome_up": d.get("chromeRunning", False), "logged_in": d.get("loggedIn", False),
                "hint": d.get("hint", "")}
    except Exception:  # noqa: BLE001
        return {"chrome_up": False, "logged_in": False,
                "hint": "先 bash skills/xhs-collector/scripts/launch-chrome.sh 起采集 Chrome"}


def _browser_account(ident: dict, rec: dict) -> dict:
    url = ident.get("url")
    if not url:
        return {}
    pay = _collect("user", url, int(_env("XHS_RECENT", "20") or 20))
    u = pay.get("user", {}) if pay.get("loggedIn") else {}
    if not u.get("nickname"):
        return {}
    notes = [{"id": x.get("id", ""), "title": x.get("title", ""), "liked": _cn_num(x.get("likedText")),
              "url": x.get("url", "")} for x in u.get("notes", [])]
    likes = [x["liked"] for x in notes if x["liked"]]
    out = {
        "account_name": u.get("nickname", ""), "account_url": _bare_profile(pay.get("profileUrl", url)),
        "red_id": u.get("redId", ""), "followers": _cn_num(u.get("fans")), "bio": u.get("desc", ""),
        "avg_liked": round(sum(likes) / len(likes), 1) if likes else 0, "recent_notes": notes,
        "representative_notes": [x["url"] for x in sorted(notes, key=lambda z: z["liked"], reverse=True)[:3] if x["url"]],
        "note_texts": "\n".join(x["title"] for x in notes),
    }
    return {k: v for k, v in out.items() if v not in _EMPTY}


def _browser_note(ref: dict, rec: dict) -> dict:
    url = ref.get("url")
    if not url:
        return {}
    payload = _collect("note", url, 1)
    n = payload.get("note", {}) if isinstance(payload, dict) else {}   # collect.mjs note 返回 {loggedIn, note:{…}}
    if not (n.get("desc") or n.get("title")):
        return {}
    return {k: v for k, v in {
        "source_text": n.get("desc", ""), "title_raw": n.get("title", ""), "author": n.get("author", ""),
        "metrics": {"liked": _cn_num(n.get("liked")), "collected": _cn_num(n.get("collected")),
                    "comments": _cn_num(n.get("comments")), "shared": _cn_num(n.get("share_count"))},
        "cover_url": n.get("cover_url", ""), "url": n.get("url", url),
    }.items() if v not in _EMPTY}


# ───────────────────────── mock adapter(离线测试)─────────────────────────
def _mock_account(ident: dict, rec: dict) -> dict:
    return {"account_name": "示例账号", "account_url": ident.get("url", ""), "followers": 12345,
            "avg_liked": 100, "recent_notes": [{"title": "示例笔记", "liked": 100, "url": ""}],
            "audience": {"gender": {"female_ratio": 0.8, "male_ratio": 0.2}}}


def _mock_note(ref: dict, rec: dict) -> dict:
    return {"source_text": "示例正文(mock)", "title_raw": "示例标题", "author": "示例作者",
            "metrics": {"liked": 100, "collected": 50, "comments": 10, "shared": 5},
            "topic_tags": ["示例"], "url": ref.get("url", "")}


ADAPTERS = {
    "redfox": {"account": _redfox_account},
    "apify": {"account": _apify_account, "note": _apify_note},
    "browser": {"account": _browser_account, "note": _browser_note},
    "mock": {"account": _mock_account, "note": _mock_note},
}

# 账号统一契约的全部字段(用于算 data_gaps)
_ACCOUNT_FIELDS = ["account_name", "account_url", "red_id", "followers", "avg_liked", "total_works",
                   "note_count_30d", "account_attribute", "bio", "audience", "recent_notes"]
_NOTE_FIELDS = ["source_text", "title_raw", "author", "metrics", "cover_url", "topic_tags", "url"]


def _compose(entity: str, ident: dict, chain: list) -> dict:
    """按链序逐字段合并:先到的非空占位,后面只补空缺。记 provenance + data_gaps。"""
    rec: dict = {}
    prov: dict = {}
    tried = []
    for a in chain:
        fn = ADAPTERS.get(a, {}).get(entity)
        if not fn:
            continue
        tried.append(a)
        partial = fn(ident, rec) or {}
        for k, v in partial.items():
            if v not in _EMPTY and rec.get(k) in _EMPTY:
                rec[k] = v
                prov[k] = a
    fields = _ACCOUNT_FIELDS if entity == "account" else _NOTE_FIELDS
    gaps = {k: "未取到(链路各源均空/不支持)" for k in fields if rec.get(k) in _EMPTY}
    rec["provenance"] = prov
    rec["data_gaps"] = gaps
    rec["_chain_tried"] = tried
    return rec


def account(ident, chain=None) -> dict:
    return _compose("account", _ident(ident), chain or _chain())


def note(ref, chain=None) -> dict:
    return _compose("note", _ident(ref), chain or _chain())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="取数口自测")
    ap.add_argument("kind", choices=["account", "note"])
    ap.add_argument("ident")
    ap.add_argument("--chain", default=None, help="逗号分隔覆盖 XHS_FETCH_CHAIN")
    args = ap.parse_args()
    ch = [a.strip() for a in args.chain.split(",")] if args.chain else None
    out = account(args.ident, ch) if args.kind == "account" else note(args.ident, ch)
    print(json.dumps(out, ensure_ascii=False, indent=2))
