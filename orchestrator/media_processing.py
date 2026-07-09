"""媒体加工任务 seam:AI剪候选先进入可恢复任务,验收后才回到 Note 状态机。

本模块只管"任务账本"这一层:稳定业务键、状态、输入/输出契约。它不直接调用剪辑引擎,
因为 video-editing 的剪单结构必须先给人过目。真正生成 cutlist/物化成片是后续工位按任务状态推进。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

ASSET_ROOT = Path(os.environ.get("GY_ASSET_ROOT", str(Path.home() / "素材库")))

WAIT_CUTLIST = "待生成剪单"
CUTLIST_REVIEW = "剪单待人确认"
WAIT_MATERIALIZE = "待物化"
FINAL_REVIEW = "成片待验收"
READY_NOTE = "可建 Note"


def task_key(account: str, playbook: str, sku: str, target_types: list[str]) -> str:
    """稳定媒体加工业务键。同一账号/方法论/SKU/目标类型跨天复用一个任务。"""
    target = ",".join(sorted(target_types))
    digest = hashlib.sha1(f"{account}\x1f{playbook}\x1f{sku}\x1f{target}".encode("utf-8")).hexdigest()[:12]
    return f"MEDIA-{digest}"


def _task_path(key: str, root: Path) -> Path:
    return root / "_processing" / f"{key}.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, task: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ensure_task(account: str, playbook: dict, candidate: dict, source_materials: list[dict],
                day: date, root: Path | None = None) -> dict:
    """确保一条 AI剪加工任务存在。返回 `{status, task}`; 重跑不重复创建。

    Interface 约束:
    - 不生成 cutlist,不剪片;初始状态固定为「待生成剪单」。
    - edit_skill/edit_params 来自 playbook data,引擎不硬编码账号特例。
    - output_contract 固定为 video-editing 输出形状,但初始为空。
    """
    root = root or ASSET_ROOT
    playbook_id = playbook.get("id") or candidate.get("方法论") or ""
    target_types = list(candidate.get("剪成") or playbook.get("material_needs") or [])
    key = task_key(account, playbook_id, candidate.get("sku") or "", target_types)
    path = _task_path(key, root)
    if path.exists():
        return {"status": "existing", "task": _read(path)}

    task = {
        "task_key": key,
        "state": WAIT_CUTLIST,
        "account": account,
        "playbook": playbook_id,
        "content_type": playbook.get("content_type") or playbook_id,
        "sku": candidate.get("sku") or "",
        "style": candidate.get("款式") or "",
        "target_types": target_types,
        "source_materials": source_materials,
        "edit_skill": playbook.get("edit_skill") or playbook.get("video_skill") or "video-editing",
        "edit_params": playbook.get("edit_params") or {},
        "created_for_day": day.isoformat(),
        "gates": [CUTLIST_REVIEW, FINAL_REVIEW],
        "output_contract": {
            "final_mp4": "",
            "draft_dir": "",
            "cutlist_path": "",
            "review_rounds": [],
            "segments": [],
            "gaps": [],
            "material_code": "",
        },
    }
    _write(path, task)
    return {"status": "created", "task": task}


def ready_material_code(task: dict) -> str:
    """任务是否已通过成片验收、可建 Note。未就绪返回空字符串。"""
    if task.get("state") != READY_NOTE:
        return ""
    output = task.get("output_contract") or {}
    return str(output.get("material_code") or "")


def approved_material_codes(root: Path | None = None) -> set[str]:
    """所有已通过媒体任务验收、允许进入 Note 状态机的生成素材编号。"""
    root = root or ASSET_ROOT
    processing = root / "_processing"
    if not processing.exists():
        return set()
    out: set[str] = set()
    for path in processing.glob("*.json"):
        try:
            code = ready_material_code(_read(path))
        except (OSError, json.JSONDecodeError):
            continue
        if code:
            out.add(code)
    return out
