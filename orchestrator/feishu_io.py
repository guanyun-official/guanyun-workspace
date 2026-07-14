"""飞书 IO(推进器专用薄层):单 writer 串行、429 指数退避、显式报错(绝不静默 {})。
所有写操作先过 guard.assert_base_allowed —— TEST_MODE 下物理到不了生产。
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime

from . import config, guard
from .bitable import RunLogFields as RLF


class FeishuIOError(RuntimeError):
    pass


def _call(method: str, path: str, params: dict | None = None, data: dict | None = None) -> dict:
    # ★守卫必须在**任何 IO 之前** —— 读也不许碰生产库★
    #
    # 老实现只在写路径守(`_guard_write`)。真跑复现:把 BASE_TOKEN 指向生产库,
    # `list_records` / `search_records` / `get_record` **全部放行**,请求已经构造到 N9IVbi 了。
    # 而 `board` 正把「生产库**读也不许碰**,守卫在任何 IO 之前」**当红线印给 agent 看** ——
    # **门是漏的,话是假的。**
    #
    # 这是这个仓里所有飞书 IO 的**唯一出口**,所以守卫就该在这。
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    args = ["lark-cli", "api", method, path, "--as", "bot"]
    if params:
        args += ["--params", json.dumps(params, ensure_ascii=False)]
    if data:
        args += ["--data", json.dumps(data, ensure_ascii=False)]
    # ★lark-cli 把**报错写在 stderr**,成功才写 stdout★(2026-07-15 查笔记本发烫时撞出来的)
    #
    # 老实现只看 `r.stdout`。出错时 stdout 是**空的** → `"{" in out` 为假 → 落到最后两行
    # → **睡 1s、2s、4s、8s,重跑 5 次** → 抛 `5 次重试未成功`。
    #
    # 后果两条,都在骗人(**真跑量过**):
    #  ① **任何一个错都烧 36 秒 + 5 个进程**。而这种错重试毫无意义 —— 表 id 错,重试 5 次还是错。
    #  ② **真话被扔了。** lark-cli 在 stderr 明明白白说了 `[1254041] TableIdNotFound`,
    #     而数字生命收到的是「5 次重试未成功」—— 它不知道自己表 id 写错了,只知道"重试没成功"。
    #     **于是它会去重试,而不是去改。**
    #
    # 修完:错 → **1 秒 · 1 个进程 · 说真话**。
    # 真读一遍 API 返回(连 stderr 一起读),别猜形态 —— 同一个坑栽过第五次。
    delay = 1.0
    last = ""
    for _ in range(5):
        r = subprocess.run(args, capture_output=True, text=True, cwd=str(config.WORKSPACE), env=env, timeout=60)
        blob = r.stdout.strip() or r.stderr.strip()     # ★成功在 stdout,报错在 stderr。两个都得看★
        last = r.stderr.strip()
        if "{" in blob:
            try:
                d = json.loads(blob[blob.find("{"):])
            except json.JSONDecodeError:
                raise FeishuIOError(f"非 JSON 响应: {blob[:200]}")
            code = d.get("code", d.get("error", {}).get("code"))
            if code == 0:
                return d.get("data", {})
            # **只有"等一下会好"的错才配重试。** 其余的重试 5 次只是把同一个错犯 5 遍。
            if code in (99991400, 1254290, 429) or "frequency" in str(d)[:300].lower():
                time.sleep(delay)
                delay = min(delay * 2, 16)
                continue
            msg = d.get("error", {}).get("message") or d.get("msg") or ""
            raise FeishuIOError(f"{method} {path} code={code} {msg}: {str(d)[:300]}")
        time.sleep(delay)                               # 连 JSON 都没有(网络/进程挂了)→ 这才值得重试
        delay = min(delay * 2, 16)
    raise FeishuIOError(f"{method} {path} 连续 5 次拿不到任何 JSON(网络?lark-cli 挂了?)"
                        f" 最后一次 stderr: {last[:200] or '(空)'}")


def _guard_write() -> None:
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)


def upload_media(local_path: str, file_name: str = "") -> str:
    """上传媒体到飞书(bitable 附件用),返回 file_token。用于素材缩略图。
    lark-cli 沙盒只认 workspace 内路径 → 先拷进 workspace 临时目录再传(--file multipart),传完清理。"""
    import shutil
    import uuid
    from pathlib import Path
    src = Path(local_path)
    if not src.exists():
        raise FeishuIOError(f"上传媒体:文件不存在 {local_path}")
    tmpdir = config.WORKSPACE / ".media_upload"
    tmpdir.mkdir(exist_ok=True)
    staged = tmpdir / f"{uuid.uuid4().hex}{src.suffix or '.jpg'}"
    shutil.copy(src, staged)
    rel = staged.relative_to(config.WORKSPACE)
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    data = json.dumps({"file_name": file_name or src.name, "parent_type": "bitable_image",
                       "parent_node": config.BASE_TOKEN, "size": src.stat().st_size}, ensure_ascii=False)
    try:
        r = subprocess.run(["lark-cli", "api", "POST", "/open-apis/drive/v1/medias/upload_all",
                            "--data", data, "--file", f"file={rel}", "--as", "bot"],
                           capture_output=True, text=True, cwd=str(config.WORKSPACE), env=env, timeout=120)
        out = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else ""
        d = json.loads(out) if out else {}
        if d.get("code") == 0:
            return d["data"]["file_token"]
        raise FeishuIOError(f"上传媒体失败: {str(d)[:200] or r.stderr[:200]}")
    finally:
        staged.unlink(missing_ok=True)


def list_records(table_name: str, page_size: int = 100) -> list[dict]:
    tid = config.tables()[table_name]
    items, token = [], None
    while True:
        params = {"page_size": page_size}
        if token:
            params["page_token"] = token
        d = _call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records", params)
        items += d.get("items") or []
        if not d.get("has_more"):
            return items
        token = d.get("page_token")


def search_records(table_name: str, conditions: list[dict], conjunction: str = "and",
                   page_size: int = 100) -> list[dict]:
    """服务端过滤查询(飞书 records/search API):按字段条件**下推**,只拉命中行(不全表拉)。
    conditions=[{"field_name":.., "operator":"is"/"isNot"/"isEmpty"/.., "value":[...]}];conjunction="and"/"or"。
    返回 record 列表,形态经 bitable 收窄 seam(text/link_record_ids)与 list_records **等价**
    (search 返回字段是富文本数组,bitable.text 已归一化;调用点一律走 bitable seam,不裸取字段)。
    **空 conditions → 退化 list_records(全表)**,语义不变。"""
    if not conditions:
        return list_records(table_name, page_size)
    tid = config.tables()[table_name]
    body = {"filter": {"conjunction": conjunction, "conditions": conditions}}
    items, token = [], None
    while True:
        params = {"page_size": page_size}
        if token:
            params["page_token"] = token
        d = _call("POST", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/search",
                  params, body)
        items += d.get("items") or []
        if not d.get("has_more"):
            return items
        token = d.get("page_token")


_SEARCH_COND_CHUNK = 45   # 飞书 filter conditions 有上限(~50),分块防超限


def search_in(table_name: str, field_name: str, values, page_size: int = 100) -> list[dict]:
    """便捷:『field ∈ values』服务端过滤(飞书 is 单选只收单值 → 每值一条件、conjunction=or 合并)。
    真跑验证与 list_records+内存筛等价。**空 values → 返回 []**(∈空集=无命中,不退化全表)。
    values 很多时**分块**(每块≤45,防超飞书 filter 条件上限);块间结果合并(每行只匹配一个值,不重)。"""
    vals = [v for v in (values or []) if v]
    if not vals:
        return []
    out: list[dict] = []
    for i in range(0, len(vals), _SEARCH_COND_CHUNK):
        conds = [{"field_name": field_name, "operator": "is", "value": [v]}
                 for v in vals[i:i + _SEARCH_COND_CHUNK]]
        out += search_records(table_name, conds, conjunction="or", page_size=page_size)
    return out


def name_map(table_name: str, name_field: str) -> dict[str, str]:
    """{record_id: 该行显示名} 映射(小表 账号表/内容类型表 用)。
    **为什么需要**:records/search 返回 link 字段只给 id 不给 text(与 list_records/get_record 形态不同),
    所以从 search 结果显示/匹配『账号名/内容类型名』必须靠这个把 id 还原成名(dogfood 实测:不还原→全空)。
    小表(≤数十行)一次全拉,可接受。"""
    from . import bitable
    return {r["record_id"]: bitable.text(r["fields"].get(name_field)) for r in list_records(table_name)}


RECORD_NOT_FOUND = 1254043      # 飞书真码,三种写法(格式非法/同长不存在/乱编)全回它 —— 2026-07-15 真问过


def get_record(table_name: str, record_id: str) -> dict | None:
    """按 record_id 取**单条**(GET,不全表扫)。**只有"这条记录不存在"→None**,其余错一律抛。

    ★老实现是 `except FeishuIOError: return None`★ —— 表 id 写错、没权限、网络断,
    **全都被吞成"找不到"**。数字生命拿到 None,只会以为"这条素材不在库里",
    然后接着往下走。**静默吞数据,仓里记过的病。**
    """
    tid = config.tables()[table_name]
    try:
        d = _call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{record_id}")
        return d.get("record")
    except FeishuIOError as e:
        if f"code={RECORD_NOT_FOUND}" in str(e):
            return None                                  # 真的没这条 —— 这才是 None 的意思
        raise                                            # 别的错:**说出来**,别装作"没找到"


def update_record(table_name: str, record_id: str, fields: dict) -> None:
    _guard_write()
    tid = config.tables()[table_name]
    _call("PUT", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{record_id}",
          data={"fields": fields})


def create_record(table_name: str, fields: dict) -> str:
    _guard_write()
    tid = config.tables()[table_name]
    d = _call("POST", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records",
              data={"fields": fields})
    return d["record"]["record_id"]


def log_run(summary: str, action: str, result: str = "成功", *, skill: str = "", note_ref: str = "",
            table: str, detail: str = "", cost: float | None = None) -> None:
    """写运行日志表。日志失败只打印不阻断主流程。
    cost 给定则写结构化 成本_元 数值字段。**没有月度硬闸** —— agent 看日志事实自己判断。

    **table 必填,没有默认值**(2026-07-14 全体系对齐审查):原来它默认 `"笔记表"`,而 9 个调用点
    **一个都没传** → 全部静默落进默认值。于是日志里写着:
        动作=自动打标  摘要=自动打标入库 1 条 · /巧荷素材/待入库  **涉及表=笔记表**  ← 假的,是素材表
        动作=找热点    摘要=找热点落灵感库 N 条                **涉及表=笔记表**  ← 假的,是灵感库
    **出事时排障,日志会告诉你"打标在操作笔记表"——它在撒谎。**
    默认值就是陷阱:它把"忘了传"变成"静默记错"。去掉默认值,调用点必须说清自己在动哪张表。
    """
    try:
        fields = {
            RLF.SUMMARY: summary,
            RLF.TIME: int(datetime.now().timestamp() * 1000),
            RLF.EXECUTOR: "orchestrator",
            RLF.SKILL: skill,
            RLF.ACTION: action,
            RLF.TABLE_REF: table,
            RLF.RECORD_REF: note_ref,
            RLF.RESULT: result,
            RLF.DETAIL: detail[:800],
        }
        if cost is not None:
            fields[RLF.COST] = cost
        create_record("运行日志表", fields)
    except Exception as e:  # noqa: BLE001
        print(f"[log_run 降级] {e}")
