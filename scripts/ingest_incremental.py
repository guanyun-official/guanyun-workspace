"""素材增量入库(投递箱→拆解→待打标队列)。ADR-0004 / EPIC #40。

**源可换**——同一条拆解链,换个源就能真跑:
- `--from netpan`  真网盘投递箱 `观云素材/待入库/`(需 `GY_NETPAN_MODE=real` + BDUSS)
- `--from local <目录>`  本地目录(本地样片真跑拆解链,**不需网盘**)

**职责边界**(机械 vs 判断分离):
- **本脚本(机械)**:列源 → diff 已入库(按 key 去重) → 按需拉 → 转码(livp/heic→jpg) → 产出**待打标清单**。视频不切文件(ADR-0004 §4 段指针优先)。
- **agent + tagging-material 技能(判断)**:看清单里每份素材 → 打标(类型/来源/赛道/衣服/内容) → `ingest.register` 落素材表。**本脚本绝不替 agent 打标**(看不见内容不瞎标)。

  python3 -m scripts.ingest_incremental --from local brands/观云/materials/拍摄批次-20260701-手机拍
  python3 -m scripts.ingest_incremental --from netpan
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import media, netpan  # noqa: E402
from scripts.ingest import ASSET_ROOT  # noqa: E402

SEEN = ASSET_ROOT / "_incremental_seen.jsonl"     # 已入库 key 台账(增量 diff 靠它)
QUEUE = ASSET_ROOT / "_待打标.json"                 # 机械拆解完的待打标清单(交打标 agent)


class LocalSource:
    """本地目录源(样片真跑;不需网盘)。key/指针都用 file:// 本地路径。"""

    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not p.name.startswith(".") and media.kind(str(p)) != "other":
                out.append({"name": p.name, "key": f"file://{p}", "_local": str(p)})
        return out

    def fetch(self, item: dict, cache: Path) -> str:
        return item["_local"]                          # 本地已在盘上,不复制

    def pointer(self, item: dict) -> str:
        return f"file://{item['_local']}"


class NetpanSource:
    """百度网盘投递箱源(真网盘;需 BDUSS)。key/指针用 netpan 耐久指针,fetch 按需拉。"""

    def __init__(self, remote: str | None = None):
        self.remote = remote or netpan.INBOX

    def list(self) -> list[dict]:
        return [{"name": e["name"], "key": netpan.pointer(e["path"]), "_remote": e["path"]}
                for e in netpan.list_dir(self.remote)
                if not e["is_dir"] and media.kind(e["name"]) != "other"]

    def fetch(self, item: dict, cache: Path) -> str:
        return netpan.pull(item["_remote"], cache)     # 按需拉,不镜像全盘

    def pointer(self, item: dict) -> str:
        return netpan.pointer(item["_remote"])


def _load_seen() -> set[str]:
    if not SEEN.exists():
        return set()
    return {json.loads(l)["key"] for l in SEEN.read_text(encoding="utf-8").splitlines() if l.strip()}


def plan(items: list[dict], seen: set[str]) -> list[dict]:
    """只留没入过库的(按 key 去重)——增量的核心,幂等重跑不重复拉。"""
    return [it for it in items if it["key"] not in seen]


def process(source, item: dict, cache: Path) -> dict:
    """一份素材的机械拆解:拉→转码→形态。返回待打标条目(不含内容标签,那交打标 agent)。"""
    local = source.fetch(item, cache)
    if media.needs_jpg(local):
        local = media.to_jpg(local, out_dir=str(cache))
    return {"素材编号": Path(item["name"]).stem, "形态": media.kind(local),
            "链接指针": source.pointer(item), "本地": local, "待打标": True}


def run(source, cache: Path, write_seen: bool = True) -> list[dict]:
    """跑增量:列源→plan 去重→逐个 process。返回待打标清单。write_seen 才记台账(幂等)。"""
    new = plan(source.list(), _load_seen())
    cache.mkdir(parents=True, exist_ok=True)
    done = []
    for it in new:
        try:
            done.append(process(source, it, cache))
        except media.MediaError as e:
            print(f"  ⚠️ 跳过 {it['name']}: {e}", file=sys.stderr)
            continue
        if write_seen:
            SEEN.parent.mkdir(parents=True, exist_ok=True)
            with open(SEEN, "a", encoding="utf-8") as f:
                f.write(json.dumps({"key": it["key"]}, ensure_ascii=False) + "\n")
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, choices=["netpan", "local"])
    ap.add_argument("path", nargs="?", help="--from local 时的本地目录")
    ap.add_argument("--no-seen", action="store_true", help="不记台账(试跑;默认记,幂等)")
    a = ap.parse_args()

    if a.src == "netpan":
        if not netpan.logged_in():
            print(f"❌ 网盘未登录(MODE={netpan.MODE})。真跑需 GY_NETPAN_MODE=real 且 BaiduPCS-Go 已 login -bduss=…", file=sys.stderr)
            return 2
        source = NetpanSource()
        print(f"源=网盘 {netpan.INBOX}")
    else:
        if not a.path:
            print("❌ --from local 需给本地目录", file=sys.stderr)
            return 2
        source = LocalSource(a.path)
        print(f"源=本地 {a.path}")

    cache = netpan.CACHE
    done = run(source, cache, write_seen=not a.no_seen)
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n拆解完 {len(done)} 份新素材(待打标清单→ {QUEUE}):")
    for d in done:
        print(f"  · {d['素材编号']}（{d['形态']}）  {d['链接指针']}")
    if done:
        print("\n下一步:agent 按 local-skills/tagging-material 看这些素材→打标→ingest.register 落素材表。")
    else:
        print("\n(无新素材;都入过库了)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
