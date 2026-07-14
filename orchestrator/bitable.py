"""Bitable 记录适配器(候选A深化:6份重复的字段取值逻辑 + 90+裸字符串 塌成一个 seam)。
纯模块,零 IO——只把飞书那颗多形态 record dict 收进窄接口。runbook 等纯函数可放心 import。

字段形态(飞书 record.fields 的值):
- 文本/单选/超链: str 或 {"text":..,"link":..}
- 关联/lookup/富文本: list[{"text":..,"record_ids":[..]}]
- 日期: 毫秒时间戳 int(或上述 list/dict 包裹)
- checkbox: bool
"""
from __future__ import annotations

from datetime import datetime


class NoteFields:
    """笔记表字段词汇(取代散落 90+ 裸字符串;飞书改名只改这里)。"""
    TABLE = "笔记表"
    TITLE = "标题"
    STATUS = "状态"
    AI_DECLARED = "AI声明"
    ACCOUNT = "账号"
    CONTENT_TYPE = "内容类型"
    DRAFT = "文案草稿"        # **最终发布的那一版** —— 运营在 base 里直接改它,改完就发(他不用多做事)
    ORIGINAL = "原始生成稿"   # **agent 出稿那一刻的原文**,之后不动
    # ★『原始生成稿』和『文案草稿』的差 = **人改了什么** = 这个系统里最值钱的信号★
    # (2026-07-14 用户点破)老实现只有一个『文案草稿』字段:
    #   · 运营在 base 里改了 → **原始生成稿被覆盖,没了**
    #   · agent 重新出稿   → **运营的修改被覆盖,没了**
    #   · 发出去的到底是哪一版 —— **没人知道**
    # 而"人把哪句话改掉了"**直接告诉技能该怎么改**(不用猜、不用复盘会)。
    # 这个信号原来**一落地就被抹掉**。现在留住了:agent 写稿时同时落一份原文,人改的是草稿。
    PUBLISH_LINK = "发布链接"
    PUBLISHED_AT = "实际发布日"
    LINKED_MATERIALS = "关联素材"   # #32 薄执行器选素材挂这里(link→素材表)
    PLAYBOOK = "方法论"        # 显式所属方法论 id(为空则回退 content_type 解析)
    LIKED = "点赞"            # 效果采集写回;热度分是 formula 由 Bitable 自算,不写
    COLLECTED = "收藏"
    COMMENTS = "评论"
    SHARED = "转发"
    OWNERSHIP = "内容归属"   # 本号原创 | 外部参考
    # ★『外部参考』= **这一行不是我们发的**★(2026-07-14 加,为了验证回流链路)
    # 回流采集是从**笔记表**读『发布链接』去抓数的。要真跑通这条链路,就得有一行带真实链接的笔记。
    # 可我们一条帖都还没发出去(红线焊死"绝不自动发布",这一截卡在人手里)。
    # 于是拿**一条公开的他人笔记**当验证桩 —— 数据是真抓的,**但"这是我们发的"就是一句谎**。
    # 而周报的「🏆 单条最佳」是从所有已发里挑最高赞的 → 它会指着别人的爆款说"我们本周最佳"。
    # **零数据编结论换了个马甲。**
    # 所以世界得能说清"**这一行不是我们发的**"。复盘一律排除『外部参考』,并在周报里如实提一句。
    QC = "质检"   # 出稿即评的问题标记(零素材/篇幅不达技能规格/混入制作说明…)。**必须落库**:
                  # 算出来却不写库 = 运营在 base 和卡片上都看不见 = 等于没检(2026-07-14 建了字段忘接线)
    KEYWORDS = "标签·关键词"   # link→关键词库。**回填的是"文案里真正出现的词",不是"喂进 prompt 的词"**
                              # (prompt 里明写着"别硬堆、调性优先" → 进 prompt ≠ 真用了)。
                              # 2026-07-14:这个 link 从来没有任何东西写过 → 反向链接永远 0
                              # → 关键词库的『被引用数』formula 永远 0 → 「热词排行」视图排一列全 0。
                              # **一个承诺"哪些词热"却结构性答不出来的视图。** 现在回程接上了。


class MaterialFields:
    TABLE = "素材表"
    CODE = "素材编号"
    TYPE = "类型"     # **纯内容**(拍的是什么):上身/商品/形象/搭配/细节/面料·纹理/工艺/制作过程/空镜·场景/文物原件/文物对照
    FORM = "形态"     # **图 还是 视频**。见下面 MaterialForm
    LINK = "链接"          # url 字段:人点开的分享链(投手一点直达该图/视频)
    REL_PATH = "相对路径"   # text 字段:系统耐久指针(baidupan:/... 或 file://);寻址用,不被 url 改写
    SHOT_STATUS = "拍摄状态"
    SOURCE = "来源"
    STYLE = "款式"   # **这是哪一套衣服**(agent 打标时自己起个名,同一套写同一个)
    # ★为什么必须有(2026-07-14 数字生命上班时点破)★
    # board 说「上身·图 已拍可用 **132**」—— **真数字,假印象**。
    # 它翻完发现:132 张里只有**约 4 套衣服**(粉+白纱裙 / 浅蓝+阔腿裤 / 藕荷紫紫藤罩衫 / 浅蓝+团扇),
    # 其余全是同一套的连拍。出完当天那批稿,**4 套已经被 9 条笔记用遍** ——
    # **再出稿就是同一件衣服换个角度再发一遍。**
    #
    # 而"这套衣服被几条稿用过"**它算不出来**:世界里没有"哪一套"这个位置,
    # 它只能一张张读备注人肉比对。**撞衫是它肉眼发现的,不是系统告诉它的。**
    #
    # 补上位置之后:board 能报「每套款式被几条笔记用过」,选材/补拍才有真依据。
    NOTE = "备注"
    THUMB = "缩略图"        # 附件字段:降采样预览图(base 驾驶舱瞄一眼选材,不用点开网盘)
    ACCOUNTS = "适用账号"   # 赛道(账号×模式)投影;打标留空,分发选材时按类型+备注语义现选并回填(消费即记录)
    # 『被引用次数』formula 字段已于 2026-07-14 从测试库**删除**:它是 formula,而 COUNTA/COUNT 对
    # DuplexLink 在飞书里都算不出来 → 282 条素材里,13 条被真引用过的全报错(其余"对"只因都是 0)。
    # 只要素材真被用过它就说谎,而它提供的信息 BACKLINK 本来就有(base 里点开即见哪几篇笔记在用)。
    # 后果曾是致命的:`#36 少用优先` 按它排序 → 全 0 → 排序 stable → 永远只用表序前 3 条素材。
    OTHER_BRAND = "画面有他牌"   # ★画面里有别家品牌的 logo(Checkbox)★
    # **这是事实,不是判断** —— 有没有 Dior 在画面里,你看得见;能不能发,**运营定**。
    # 为什么必须是**字段**,不能只写进『质检』(2026-07-15 数字生命抓到):
    #   三条**已经在『待发布』**的稿,质检**完全空白**,而图里全是 Dior 藤格纹托特
    #   (金色 D-I-O-R 挂饰正对镜头)—— **运营会把"质检空白"读成"这条没问题"**。
    #   同样的风险,有的稿写了满满一段,有的稿一个字没有。**靠每次记得写,就一定有忘的那次。**
    # 280 条素材里,**116 条备注提到包/首饰却只给泛称**(41%)。逐条核出 4 个品牌 7 件单品。
    # 有了这个位置,卡片就能**每次都提**,不靠谁的记性。
    BACKLINK = "笔记表-关联素材"   # 反向 link:哪些笔记引用了这条素材。**数它才是真被引用次数**(见 draft._cited_count)


class AccountFields:
    """账号表字段词汇(AccountKernel 对齐 Base 账号行与 workspace Account data 用)。"""
    TABLE = "账号表"
    NAME = "账号名"


class AutoSched:
    """账号表「自动排产」select 取值:base 侧运营开关(暂停/跟随workspace 的唯一真相)。"""
    FIELD = "自动排产"
    PAUSED = "暂停"          # base 强制停(覆盖 md,谁接手都读得到)
    FOLLOW_WS = "跟随workspace"  # 按 workspace 账号 md 的 cadence 节奏派(默认)


class MaterialForm:
    """素材『形态』取值 —— **图 还是 视频**(2026-07-14 加的字段,世界原来缺这个位置)。

    ★为什么必须把形态从『类型』里拆出来★

    老『类型』的 12 个值**把内容和形态焊在一个字段里**:
    「上身图」/「上身视频」是同一内容的两种形态;而「面料·纹理特写」「细节图」「空镜·场景」
    **只有图这一档** —— 一条 1.5 秒的**面料特写视频,在这套词汇里没有地方放**。

    于是老 tagger 里长出了这条钳制:

        if kind == "video":
            return raw if raw in _VIDEO_TYPES else "上身视频"   # 视频文件强制落视频类

    看图模型多半判对了(那就是个面料特写),**harness 把它的正确答案覆盖成了「上身视频」**。
    后果:库里唯一那条"上身视频"真身是 1.5 秒的糊布料特写 → board 报「上身视频可用 1 条」
    (**真实可用 0 条**)→ 补拍单少催一条 → 还有一条待审稿就是配着它出的。
    **一个字段的形状不对,凭空造出了一条不存在的库存。**

    **这不是代码 bug,是世界缺了个位置。** 位置补上了,那条钳制就再也长不回来。
    """
    TABLE = "素材表"
    FIELD = "形态"
    IMAGE = "图"
    VIDEO = "视频"


class MaterialStatus:
    """素材拍摄状态取值(素材表 拍摄状态 select 枚举)。「已拍」= 真有这份素材,能用。"""
    TABLE = "素材表"
    FIELD = "拍摄状态"
    SHOT = "已拍"


class MaterialSource:
    """素材来源取值(素材表 来源 select 枚举)。生成媒体标 AI生成、拍摄标 实拍。"""
    TABLE = "素材表"
    FIELD = "来源"
    REAL = "实拍"
    AI = "AI生成"


class RunLogFields:
    """运行日志表字段词汇(9 字段契约;log_run 写、_monthly_cost_cny 读)。"""
    TABLE = "运行日志表"
    SUMMARY = "摘要"
    TIME = "时间"
    EXECUTOR = "执行体"
    SKILL = "技能"
    ACTION = "动作"
    TABLE_REF = "涉及表"
    RECORD_REF = "涉及记录"
    RESULT = "结果"
    DETAIL = "详情"
    COST = "成本_元"  # 这次花了多少钱(元)。**没有硬闸** —— agent 看它自己判断要不要停手


class ContentTypeFields:
    """内容类型表字段词汇(引擎格式感知:内容类型名→格式 查表)。"""
    TABLE = "内容类型表"
    NAME = "内容类型名"


class InspirationFields:
    """灵感库字段词汇(爆款灵感=trend_imitate 出稿原料;此前散在 dispatch 用裸中文串,飞书改名会漏改)。"""
    TABLE = "灵感库"
    TITLE = "标题"
    MERITS = "优点"           # 可借鉴优点
    BODY = "文案"             # 爆款正文——防搬运门比对源(出稿逐字搬这个即拒);出稿时传 generate_draft(source_text=)
    LINK = "链接"             # 爆款源链接
    CONVERTED = "转化为笔记"   # link 字段(写 record_id 列表);非空=已转化,跳过


class KeywordFields:
    """关键词库字段词汇(选题/SEO 池;此前散在 draft.load_keywords 用裸中文串)。"""
    TABLE = "关键词库"
    KEYWORD = "关键词"
    ENABLED = "启用状态"      # 取值≠"停用"(下方 DISABLED)即视为启用
    DISABLED = "停用"         # 「启用状态」的停用取值(select 值,非字段名;飞书实际枚举=启用/停用,曾误写"禁用"致停用词漏筛——schema契约抓出)


class NoteStatus:
    """笔记状态机取值(状态列 select 枚举;写回只能用声明过的值,否则飞书拒写/静默落空)。
    状态机: 想法储备→待拍素材→待出文案→草稿待发(=待审)→已批准→待发布→已发→已回流;暂缓归档旁路。"""
    TABLE = "笔记表"
    FIELD = "状态"
    IDEA = "想法储备"
    NEED_SHOOT = "待拍素材"
    NEED_COPY = "待出文案"
    DRAFT_PENDING = "草稿待发"  # =待审:人审卡点
    APPROVED = "已批准"
    TO_PUBLISH = "待发布"
    PUBLISHED = "已发"
    LOOPED_BACK = "已回流"
    ON_HOLD = "暂缓归档"


# 元属性(定位 schema 用,非字段/取值本身),契约收集时排除
_META_ATTRS = frozenset({"TABLE", "FIELD"})


def declared_field_names(fieldset: type) -> list[str]:
    """字段词汇/取值类里声明的常量值(UPPERCASE,排除 TABLE/FIELD 元属性)——供 schema 契约校验:
    代码消费 ⊆ 声明。飞书 UI 改字段名/删 select 选项而代码没跟上 → 契约测试红,不静默漂移。"""
    return [v for k, v in vars(fieldset).items()
            if k.isupper() and k not in _META_ATTRS and isinstance(v, str)]


def url_value(url: str, text: str = "") -> dict:
    """url 字段值:URL → {link, text} dict(url 字段写纯字符串会炸)。"""
    return {"link": url, "text": text or url}


def text(v) -> str:
    """任意字段值 → **给人看的文本**。list[dict]→逗号连;dict→text/link;标量→str。
    ⚠️ url 字段(`{"link": …, "text": …}`)走这里回的是 **text(显示名)**,**不是能点的 href**。
    要 href 用 `url()`。"""
    if isinstance(v, list):
        return ",".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
    if isinstance(v, dict):
        return str(v.get("text") or v.get("link") or "")
    return str(v or "")


def multi(v) -> list[str]:
    """多选字段 → **值的列表**(不是拼起来的字符串)。

    ★为什么单独有这个函数★ 多选字段是 `["A", "B"]`。
    `text()` 会把它**逗号连成 `"A,B"`** —— 于是「一张图两套衣服」在分桶时变成了
    **第三套叫「A,B」的衣服**。真事:9 张双人同框图 → board 报出三个桶,
    「浅蓝」明明撞了 5 条稿,读出来只有 3 条。**而这个数字唯一的用途就是判撞衫。**
    (这是第三个被手写拆错的字段形态了 —— link / url / 多选。**形态只该拆一遍,拆在这。**)
    """
    if isinstance(v, list):
        return [x if isinstance(x, str) else str(x.get("text") or x.get("name") or "")
                for x in v if x]
    return [str(v)] if v else []


def url(v) -> str:
    """url 字段 → **能点开的 href**(不是显示名)。

    ★为什么单独有这个函数★ 飞书 url 字段是 `{"link": "https://…", "text": "文件名.heic"}`。
    `text()` 是 **text 优先** —— 对 url 字段就**恰好把唯一有用的那半扔了**。
    这个形态被手写拆解过三处(materials / board / publish),**其中一处拆错**,
    运营卡片上就出现了「🖼 ST-260702-004 → 2026-07-02 175621.heic」这种点不开的东西。
    形态只该被拆一遍,拆在这。"""
    if isinstance(v, dict):
        return str(v.get("link") or "")
    return str(v or "")


def day_start_ms(d) -> int:
    """某日 0 点的毫秒时间戳(飞书日期窗服务端过滤 value=['ExactDate', str(ms)] 用;冷热分离查询共用)。"""
    return int(datetime(d.year, d.month, d.day).timestamp() * 1000)


def link_names(v, id_name: dict | None = None) -> str:
    """link 字段 → 显示名(逗号连)。**三形态通吃**(dogfood 坑:search 回 id 无 text):
    - records/search:`{link_record_ids:[id..]}` → 用 id_name({id:名})还原;
    - list_records/get_record:`[{text,record_ids}]` / 纯文本 → id_name 取不到时回退 text。
    id_name 一般来自 feishu_io.name_map(小表 账号表/内容类型表 的 {record_id:名})。"""
    id_name = id_name or {}
    resolved = ",".join(n for n in (id_name.get(i, "") for i in link_record_ids(v)) if n)
    return resolved or text(v)


def link_record_ids(v) -> list[str]:
    """关联字段 → 目标 record_id 列表。**飞书两套 API 形态不同,必须都认**(否则 search 读 link 全空):
    - list_records / get_record:`list[{record_ids:[...], text:..}]`
    - records/search:`{link_record_ids:[...]}`(dict,无 text!)——只认前者会让 search 路径素材/账号全断(dogfood 实测坑)。
    这几个自由函数 text/link_record_ids = 飞书多形态 record dict 的**唯一收窄 seam**。"""
    if isinstance(v, dict):                       # records/search 形态:{'link_record_ids': [...]}
        return list(v.get("link_record_ids") or v.get("record_ids") or [])
    out = []
    if isinstance(v, list):                       # list_records/get_record 形态:[{record_ids:[...]}]
        for x in v:
            if isinstance(x, dict):
                out += x.get("record_ids", []) or x.get("link_record_ids", []) or []
    return out
