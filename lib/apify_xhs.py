"""
apify_xhs.py — 小红书**零封号取数**统一出入口(Apify `socialdatax/socialdatax-xhs-data-api`)。

全程不用我方小红书账号/cookie → **零封号**(数据由 Apify/socialdatax 侧基建抓)。
env `APIFY_TOKEN`(apify_api_…);按结果计费(约 $4.99/千条)。各技能共用本模块,别各写一份。

socialdatax operations:
  get_note_detail(note_url|note_id)  单篇详情(含正文全文 content/全互动/topic_tags/ip_location/图片)
  list_user_notes(profile_url, max_items)  账号近 N 篇
  get_user_info(profile_url|user_id)  账号资料
  search_notes(keyword, ...)         关键词搜笔记(真实搜索,非仅热门)
  get_note_comments / get_note_sub_comments / search_hot_list

换源:Actor 由 `.env` 的 `APIFY_XHS_ACTOR` 配置(默认 socialdatax)。Apify=平台,Actor=平台上某开发者
发布的爬虫应用;换 Actor 只改这一处 env、token 不变。⚠️ 不同 Actor 的**输入参数 schema 不一样**
(socialdatax 用 operation/profile_url/note_url;easyapi 用 profileUrls/maxItems…),换源时调用方参数要跟着适配。

用法:
  from apify_xhs import run
  items, err = run("get_note_detail", note_url="<链接>")
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_ACTOR = "socialdatax~socialdatax-xhs-data-api"


def _env(key: str) -> str:
    """读环境变量,缺则从 WORKSPACE/.env 兜底(只读未设置的键)。"""
    v = os.environ.get(key, "")
    if not v:
        f = WORKSPACE / ".env"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{key}="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
    return v


def _actor() -> str:
    """跑哪个 Apify Actor(.env: APIFY_XHS_ACTOR;默认 socialdatax)。统一成 username~actorname。"""
    return (_env("APIFY_XHS_ACTOR") or DEFAULT_ACTOR).replace("/", "~")


def run(operation: str, timeout: int = 240, **params) -> tuple[list, str | None]:
    """调当前 Actor 的一个 operation,返回 (items, error)。error 为 None 表示成功。
    不抛异常(入口层友好);失败/无 token → ([], "原因")。"""
    token = _env("APIFY_TOKEN")
    if not token:
        return [], "缺 APIFY_TOKEN(放 .env)"
    run_sync = f"https://api.apify.com/v2/acts/{_actor()}/run-sync-get-dataset-items?token={token}"
    body = {"operation": operation, **params}
    req = urllib.request.Request(
        run_sync, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            items = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return [], f"Apify 调用失败: {e}"
    if isinstance(items, dict):
        items = items.get("items", []) or []
    return (items if isinstance(items, list) else []), None
