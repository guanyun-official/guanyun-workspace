"""Action Interface —— **agent 的手伸出来的地方**。

    python3 -m orchestrator <动词> [参数]

★纪律:一个动词 = 一件事,零判断★
这里**没有**「跑完一天」「自动派活」「一键出稿」这种动词 —— 那些是**流程**,
而流程 = 我替 agent 排好的步骤 = 导轨。动词只有原子:看一眼、拉一个、写一行、过一道门。
**先干什么后干什么、干不干、干几条 —— 全是 agent 的判断。**

★这里**故意没有**的动词★
  · `approve`(批准)—— **审批是人在 base 里做的**(人和 agent 看同一张表,不搞两套真源)。
    给 agent 一个"批准"动词,它就能**自己批自己的稿**,人审就成了摆设。
  · `publish`(发布)—— 红线焊死。发布是人的动作,系统止于『待发布』。
  · `tag`(打标)/ `draft`(出稿)—— 那是**你自己看图、自己写字**,不是调一个函数。
    harness 只给你:把网盘的东西变成你能看的(`material.view`)、把你写的字落库(`note.draft`)。
  · `schedule`(定时)—— **那是运行时给的手**(`hermes cron create/list/edit/pause`),不是我们造的。
    我一度在这里造了一份 crontab 读写 —— **harness 重新实现了一遍运行时已经会做的事**(两份真源)。
    几点醒、醒来干什么、要不要改自己的作息 —— 一直都是**你的判断**,用运行时那只手去做。
"""
from __future__ import annotations

import argparse
import json
import sys


def _out(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=1, default=str))


def _kv(pairs: list[str]) -> dict:
    """--set 字段=值 … → dict。"""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--set 要写成 字段=值,你给的是「{p}」")
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _csv(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m orchestrator", description=__doc__)
    ap.add_argument("--brand", default="巧荷")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # ── 眼睛(Observation)────────────────────────────────────────────────
    sub.add_parser("board", help="【眼】世界现在什么样(账号/在途/素材/灵感/回流/作息/红线)。纯读")
    c = sub.add_parser("card", help="【眼·人面】今日卡片(运营看的)。--send 推到飞书")
    c.add_argument("--send", action="store_true")
    c = sub.add_parser("report",
                       help="【眼·人面】周报(老板看的)。**harness 只摆事实,结论你自己说**"
                            "(`--say`)。没数据就是没数据 —— 别用零数据编")
    c.add_argument("--say", default="",
                   help="**你要跟老板说的话**(结论/判断/风险)。不给就只有一张干数据表 —— "
                        "harness 一个结论都不会替你写")
    c.add_argument("--needs", default="",
                   help='这周卡在素材上的事(JSON):[{"account":.., "类型":.., "缺":N}]。不给就没这一段')
    c.add_argument("--send", action="store_true")
    c = sub.add_parser("shotlist", help="【眼·人面】补拍单(摄影师看的)。**内容你给** --items '<json>'")
    c.add_argument("--items", required=True,
                   help='[{"账号":.., "类型":.., "缺":N, "拍摄要求":"写给拿相机的人看的人话", '
                        '"参考":[{"画面":"一句画面描述", "链接":"能点开的图"}]}] '
                        '—— 催谁、催几条、怎么说,你判断。**参考是列表,不是字符串**')
    c.add_argument("--send", action="store_true")

    # ── 素材(手 + 眼)──────────────────────────────────────────────────
    c = sub.add_parser("material.inbox", help="【眼】待入库箱里有什么(名字/形态/是否已登记过同名)")
    c.add_argument("--dir", default="")
    c = sub.add_parser("material.view", help="【手】网盘文件 → 拉下来转成能看的本地图 → **你自己 Read 它看**")
    c.add_argument("paths", nargs="+")
    c.add_argument("--frames", type=int, default=5,
                   help="视频抽几帧(默认5,均匀分布)。**一帧不是整条视频** —— 看不清就多要几帧")
    c = sub.add_parser("material.list", help="【眼】素材事实(类型/来源/画面备注/被引用次数/适用账号)。不排序不替你挑")
    c.add_argument("--type", default="", help="**内容**(上身/商品/面料·纹理…),逗号分隔;给了就服务端过滤")
    c.add_argument("--form", default="", help="**形态**:图 | 视频(内容和形态是两维,别混)")
    c.add_argument("--status", default="", help="拍摄状态,如 已拍")
    c.add_argument("--account", default="")
    c = sub.add_parser("material.register", help="【手】登记一条素材。**类型/来源/备注是你看图后自己给的**")
    c.add_argument("--path", required=True, help="网盘路径(会转成耐久指针)")
    c.add_argument("--type", required=True,
                   help="**内容**:上身/商品/形象/搭配/细节/面料·纹理/工艺/制作过程/空镜·场景/文物原件/文物对照"
                        "(board 里有词汇表)。**名字里不带『图』『视频』——那是形态,自动从文件推**")
    c.add_argument("--source", default="实拍", help="实拍 | AI生成 ——(落 02-AI生成/ 目录的会被强制标 AI生成)")
    c.add_argument("--note", required=True, help="画面备注:颜色/形制/场景/光线/姿势/细节。**这是文案的事实底座**")
    c.add_argument("--style", default="",
                   help="**这是哪一套衣服**(你自己起个名,同一套写同一个,如『粉上衣+白纱裙』)。"
                        "没有它,『这套衣服已经被几条稿用过』就算不出来 —— **撞衫只能靠肉眼**")
    c.add_argument("--thumb-from", default="",
                   help="缩略图用哪张本地图(视频**必给**:你挑一张最能代表它的帧;"
                        "静图不给则用它自己)。**哪一帧代表这条视频,是你的判断**")
    c.add_argument("--no-thumb", action="store_true", help="别做缩略图(默认做,base 里人瞄一眼选材用)")
    c = sub.add_parser("material.store",
                       help="【手】**你在本地做好的成片 → 回传网盘 03-成片 + 登记素材**。"
                            "剪辑是你的操作(ffmpeg / VectCutAPI 都在),harness 只负责把产物落进世界")
    c.add_argument("path", help="本地成片路径(你自己剪好的)")
    c.add_argument("--type", required=True, help="**内容**(上身/商品/形象/…)。你看着判")
    c.add_argument("--note", required=True, help="画面备注(下一个人出稿时只看得见这句话)")
    c.add_argument("--from-materials", default="",
                   help="**这条成片是从哪几条素材剪出来的**(record_id 逗号分隔)。"
                        "★provenance 靠它★:输入里只要有一条『AI生成』,产物就**强制**是 AI生成"
                        "(发布前人必须勾 AI 声明)—— 你说了不算")
    c.add_argument("--used-ai", action="store_true",
                   help="剪的过程中**用 AI 合成了新画面**(不是纯剪辑/拼接/调色)。"
                        "→ 产物强制 AI生成。**漏报 = 合规事故**")
    c = sub.add_parser("material.update", help="【手】改素材字段")
    c.add_argument("id")
    c.add_argument("--set", nargs="+", required=True)
    # 打标就是判断,判断就会错。**能撤销,才敢判断** —— 没有回退的手,它只会靠"不敢动"来保证不出错。
    c = sub.add_parser("material.delete", help="【手】删一条素材(登记错了能撤)。删前如实报出谁在用它")
    c.add_argument("id")

    # ── 笔记(手 + 眼;写稿的门在这)────────────────────────────────────
    c = sub.add_parser("note.new", help="【手】建一行笔记(派活占位等)。**派不派、派给谁,你判断**")
    c.add_argument("--account", required=True)
    c.add_argument("--content-type", required=True)
    c.add_argument("--title", default="")
    c.add_argument("--status", default="待出文案")
    c = sub.add_parser("note.draft", help="【手·过门】把**你写的稿**落成『草稿待发』(待人审)。出口过防搬运门")
    c.add_argument("--account", required=True)
    c.add_argument("--content-type", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--body", required=True, help="正文(不含标题)。**只要能发的成稿** —— 剪辑要点/分镜别混进来")
    c.add_argument("--materials", default="", help="挂哪几条素材(record_id 逗号分隔)——你选的")
    c.add_argument("--keywords", default="", help="**文案里真正出现的**关键词(不是喂进去的词)")
    c.add_argument("--playbook", default="")
    c.add_argument("--qc", default="", help="你自己看出的问题,想让运营重点看的(会显示在卡片上)")
    c.add_argument("--note-id", default="", help="指定推进某一行(不给则找该号该模式的在途占位)")
    c = sub.add_parser("note.get", help="【眼】**把一条笔记整个读回来(含正文)** —— 写完之后拿它自证")
    c.add_argument("id")
    # 撞衫最要命的是"这套上周发过了",而**已发的稿不在任何一只眼睛里**。board 只给在途。
    c = sub.add_parser("note.list", help="【眼】笔记事实(含**已发**):穿的哪套款式 · 哪天发的 · 数据")
    c.add_argument("--status", default="", help="只看某个状态(不给=全部,含已发/已回流)")
    c.add_argument("--account", default="")
    c.add_argument("--limit", type=int, default=0)
    c = sub.add_parser("note.update", help="【手】改笔记字段(状态推进等)。**AI声明字段写不了 —— 人勾**")
    c.add_argument("id")
    c.add_argument("--set", nargs="+", required=True)
    c = sub.add_parser("note.link-materials", help="【手】给笔记挂素材")
    c.add_argument("id")
    c.add_argument("--materials", required=True)

    # ── 发布侧(**绝不自动发布**;这里只到『待发布』)──────────────────
    c = sub.add_parser("publish.advance", help="【手·过门】『已批准』→『待发布』,过零素材/AI声明/控量三道门。**绝不发布**")
    c.add_argument("--write", action="store_true", help="不给 = 干跑(告诉你实跑会发生什么,且与实跑一致)")
    c = sub.add_parser("publish.stamp", help="【手】给『已发但没有发布日』的补上发布日(控量红线的命根子)")
    c.add_argument("--write", action="store_true")
    c = sub.add_parser("publish.link", help="【手】人发来了小红书链接 → 认领填进那条笔记")
    c.add_argument("key", help="record_id 或 标题/账号片段")
    c.add_argument("url")
    c.add_argument("--write", action="store_true")

    # ── 灵感 / 回流 / 加工 ──────────────────────────────────────────────
    c = sub.add_parser("idea.add", help="【手】把抓到的爆款落灵感库。**items 是你抓的**")
    c.add_argument("--items", required=True,
                   help='[{"标题":必填, "文案":原帖正文(学结构用), "可借鉴":它凭什么火, "源链接":溯源}]'
                        ' —— **只认这四个键;写错的键会当场报错,不会静默吞掉**')
    c.add_argument("--write", action="store_true", help="不给 = 干跑(返回值里 `写库了: false`)")
    c = sub.add_parser("idea.update", help="【手】改灵感库的一行(补『可借鉴』『源链接』『文案』)")
    c.add_argument("id")
    c.add_argument("--set", nargs="+", required=True,
                   help="键=值。**键和 idea.add 完全一样**:标题 / 文案 / 可借鉴 / 源链接。"
                        "例:--set 可借鉴='标题堆检索标签' 源链接=https://...")
    c = sub.add_parser("idea.converted", help="【手】灵感转化成笔记了 → 回填灵感库(闭环)")
    c.add_argument("idea_id")
    c.add_argument("note_id")
    c = sub.add_parser("note.metrics",
                       help="【手】**把你抓到的回流数写回**(+ 推 已发→已回流)。"
                            "『去抓』是你的操作(你有采集技能),『信不信』是你的判断 —— "
                            "**没抓到的就别传,不传的一个字都不写**(写 0 = 往库里灌假话)")
    c.add_argument("id")
    c.add_argument("--liked", type=int)
    c.add_argument("--collected", type=int)
    c.add_argument("--comments", type=int)
    c.add_argument("--shared", type=int)
    c = sub.add_parser("compose", help="【手】加工执行:拼图 / AI封面。**要不要加工是你的判断**")
    c.add_argument("--kind", required=True, choices=["拼图", "AI封面"])
    c.add_argument("--inputs", required=True, help="素材 record_id 逗号分隔")
    c.add_argument("--prompt", default="", help="AI封面用:中文文生图提示词(须贴合真实素材,不许编别的衣服)")
    c.add_argument("--type", default="", help="产物登记成什么**内容**(上身/商品/形象/搭配/…)。"
                                              "**你看图判**;不给则拼图=搭配、AI封面=形象")
    c.add_argument("--note", default="", help="产物的画面备注(下一个人出稿时只看得见这句话)")

    # ── 留痕 ────────────────────────────────────────────────────────────
    c = sub.add_parser("log", help="【手】写运行日志(你干了什么,人事后在 base 查得到)")
    c.add_argument("--summary", required=True)
    c.add_argument("--action", required=True)
    c.add_argument("--table", required=True, help="动的是哪张表(**没有默认值** —— 默认值会把'忘了传'变成'静默记错')")
    c.add_argument("--result", default="成功")
    c.add_argument("--detail", default="")
    c.add_argument("--cost", type=float, default=None, help="这次花了多少钱(元)。**没有硬闸** —— 钱花超了要不要停手,是你看事实自己判断")
    return ap


def main(argv: list[str] | None = None) -> int:
    from . import (alerts, board, cockpit, compose, feishu_io, guard, ingest, materials,
                   netpan, notes, publish, report, shotlist, trends)

    a = build().parse_args(argv)
    try:
        if a.cmd == "board":
            _out(board.view(a.brand))
        elif a.cmd == "card":
            card = cockpit.today_card(a.brand)
            _out({"投递": alerts.send_card(card) if a.send else {"已发": False, "说明": "干跑,没发(加 --send 才推飞书)"},
                  "card": card})
        elif a.cmd == "report":
            f = report.facts(a.brand)
            card = report.card(f, a.say, json.loads(a.needs) if a.needs else None)
            _out({"事实": f,
                  "投递": alerts.send_card(card) if a.send
                          else {"已发": False, "说明": "干跑,没发(加 --send 才推飞书)"},
                  "card": card})
        elif a.cmd == "shotlist":
            card = shotlist.card(json.loads(a.items))
            _out({"投递": alerts.send_card(card) if a.send else {"已发": False, "说明": "干跑,没发(加 --send 才推飞书)"},
                  "card": card})

        elif a.cmd == "material.inbox":
            _out(materials.inbox(a.dir))
        elif a.cmd == "material.view":
            _out(materials.viewable(a.paths, a.frames))
        elif a.cmd == "material.list":
            _out(materials.facts(_csv(a.type) or None, a.status, a.account, a.form))
        elif a.cmd == "material.register":
            # **登记的是这个文件本身**(视频 → 一条素材,指针指向 .MP4;不是把每帧登记成一张图)。
            name = a.path.rsplit("/", 1)[-1]
            code = ingest.gen_code(a.__dict__["type"], name, materials.used_codes())
            token = ""
            if not a.no_thumb:
                # 缩略图 = **一张代表帧**(视频必须由 agent 挑:哪一帧能代表这条视频是它的判断)。
                src = a.thumb_from
                if not src:
                    v = materials.viewable([a.path], frames=1)
                    src = (v[0].get("本地") or (v[0].get("帧") or [{}])[0].get("本地", "")) if v else ""
                if src:
                    token = materials.thumb_token(src, name)
            rid = ingest.register(code, a.__dict__["type"], netpan.pointer(a.path), a.note,
                                  a.source, thumb_token=token, style=a.style)
            _out({"素材编号": code, "record_id": rid, "类型": a.__dict__["type"], "来源": a.source,
                  "指针": netpan.pointer(a.path),
                  "自证": f"python3 -m orchestrator material.list --type {a.__dict__['type']} | grep {code}"})
        elif a.cmd == "material.store":
            from pathlib import Path as _P
            if not _P(a.path).exists():
                raise ValueError(f"本地成片不存在:{a.path}")
            srcs = [m["来源"] for m in materials.by_ids(_csv(a.from_materials))] \
                if a.from_materials else []
            # ★provenance 焊死:来源随像素出处,agent 说了不算★
            src = guard.derive_source(srcs, used_ai_generation=a.used_ai)
            rid, ptr = ingest.store_produced(a.path, a.__dict__["type"], source=src, note=a.note)
            _out({"登记了": rid, "网盘": ptr, "来源": src,
                  "说明": ("**来源=AI生成** → 这条素材挂上笔记后,发布前**人必须勾 AI 声明**"
                           if src == "AI生成" else "纯剪辑/拼接,像素都来自实拍 → 免勾 AI 声明"),
                  "自证": f"python3 -m orchestrator material.list --type {a.__dict__['type']}"})
        elif a.cmd == "material.update":
            feishu_io.update_record("素材表", a.id, _kv(a.set))
            _out({"改了": a.id, "字段": _kv(a.set)})
        elif a.cmd == "material.delete":
            _out(materials.delete(a.id))

        elif a.cmd == "note.new":
            _out({"note_id": notes.new(a.account, a.content_type, a.title, a.status)})
        elif a.cmd == "note.draft":
            _out(notes.write_draft(a.account, a.content_type, a.title, a.body,
                                   material_ids=_csv(a.materials), keywords=_csv(a.keywords),
                                   playbook=a.playbook, qc=a.qc,
                                   note_id=a.note_id))
        elif a.cmd == "note.get":
            _out(notes.get(a.id))
        elif a.cmd == "note.list":
            _out(notes.listing(status=a.status, account=a.account, limit=a.limit))
        elif a.cmd == "note.update":
            notes.update(a.id, _kv(a.set))
            _out({"改了": a.id, "字段": _kv(a.set)})
        elif a.cmd == "note.link-materials":
            notes.link_materials(a.id, _csv(a.materials))
            _out({"挂上了": a.id, "素材": _csv(a.materials)})

        elif a.cmd == "publish.advance":
            _out(publish.review_approved(a.brand, a.write))
        elif a.cmd == "publish.stamp":
            _out(publish.stamp_published_at(a.write))
        elif a.cmd == "publish.link":
            _out(publish.fill_publish_link(a.key, a.url, a.write))

        elif a.cmd == "idea.add":
            _out(trends.harvest_trends(json.loads(a.items), a.brand, a.write))
        elif a.cmd == "idea.update":
            trends.update_idea(a.id, _kv(a.set))
            _out({"改了": a.id, "字段": _kv(a.set),
                  "自证": "python3 -m orchestrator board  → 看『灵感库(未转化的爆款)』"})
        elif a.cmd == "idea.converted":
            trends.mark_converted(a.idea_id, a.note_id)
            _out({"回填了灵感": a.idea_id, "笔记": a.note_id})
        elif a.cmd == "note.metrics":
            _out(notes.write_metrics(a.id, a.liked, a.collected, a.comments, a.shared))
        elif a.cmd == "compose":
            plan = {"kind": a.kind, "inputs": _csv(a.inputs), "封面提示词": a.prompt,
                    "类型": a.__dict__.get("type", ""), "备注": a.note}
            rid = compose.execute(plan)
            _out({"加工": a.kind, "产出素材": rid,
                  "说明": "产物已回传网盘 03-成片 并登记;AI 生成的像素来源=AI生成 → 发布前人必须勾 AI 声明"
                          if rid else "**没做成** —— 如实报告,绝不假装加好了"})

        elif a.cmd == "log":
            feishu_io.log_run(summary=a.summary, action=a.action, table=a.table,
                              result=a.result, detail=a.detail, cost=a.cost)
            _out({"记下了": a.summary})
    except guard.GuardError as e:
        # **拦住 ≠ 说清楚**:红线拒了,必须告诉它是哪道门、为什么、出路在哪。别甩堆栈。
        print(f"\n🚦 红线拦下了:\n{e}\n", file=sys.stderr)
        return 3
    except notes.DraftPending as e:
        print(f"\n✋ 停手:\n{e}\n", file=sys.stderr)
        return 4
    except notes.SkillMissing as e:
        print(f"\n🧩 技能装不上(防搬运门会瞎,不能放行):\n{e}\n", file=sys.stderr)
        return 5
    except ValueError as e:
        # 参数写错了(键名不对/枚举越界…)。**拦住 + 说明白 + 给出路** —— 别甩 traceback。
        # (2026-07-14:传错键时它原样抛 ValueError,人/agent 拿到的是一屏堆栈。
        #  "拦住 ≠ 说清楚" 这条,门自己也得守。)
        print(f"\n✋ 参数不对:\n{e}\n", file=sys.stderr)
        return 2
    return 0
