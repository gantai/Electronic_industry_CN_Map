# -*- coding: utf-8 -*-
"""现成的 Markdown 转换稿 → 待核记录 + 一份本地 Excel。

`gaz convert`(转换交给 zhiconv)是给扫描件预备的。手里若已经有转好的 .md ——
别处转的、自己抄的、从数字方志库拷出来的 —— 那一步不必走,直接从这里进。

要紧的差别有两处:

**一、编码。** Windows 上存下来的稿子可能是 GB18030、可能带 BOM、也可能是
UTF-16。挨个试,试通了记下来告诉你,别让一堆乱码悄悄流进表里。

**二、页码。** 转换稿多半不留页码。本工具认的是每页正文前的 `<!-- p.123 -->`,
抽取时据以回注出处;别处转来的没有这一手。所以先认一遍常见的页码写法
(`第123页`、`- 123 -`、`[123]` 之类),认出来就归一成 `<!-- p.N -->`;
认不出也不要紧 —— 出处退到篇章节,「北京工业志·电子志·第三章」仍查得回去。
"""

import os
import re
from collections import Counter

from . import cndate
from . import extract as EX
from . import toxlsx

#: 待核本子里那四张要核的表。**四张都要核** —— 从前头一张就叫「待核」,
#: 像是只有它要核;另三张挂着总表的名字(器件 / 整机 / 名称沿革),
#: 看着像成品。四张一律冠「待核·」,一眼看出是一套。
REVIEW_UNITS = "待核·厂所"
REVIEW_SEMI = "待核·器件"
REVIEW_COMP = "待核·整机"
REVIEW_NAMES = "待核·名称沿革"

#: 第五张:已在总表里的单位,这一遍新认出来的**格子**。
#: 重跑一本核过的志书,单位大半早已收进总表 —— 那些行 append 一概跳过,
#: 于是新认出来的隶属、性质也就一并进不去。一家一家重核 126 家,换来的是
#: 九十几个格子,划不来;把格子单摆一张表,核的就只是那九十几格。
REVIEW_FILL = "待核·补格子"

#: 照总表体例摆的那一张,只供看与粘,改它不算数。
#: 从前叫「厂所名录-Shanghai」—— 跟总表那张正表同名,又缀个市名,
#: 两头都误导:像是正表,又像是只收这一市(其实京沪津的行早混在一张里了),
#: 省志跑起来更会写出「厂所名录-Local」这种没头没脑的名字。
PREVIEW = "预览·照总表体例(改它不算数)"

# 旧本子那张预览表,名字末尾带着城市 —— 城市就是从这个名字上取的。
# 旧本子作「Fact and Comp-北京」,读的时候两种都认。
UNITS_PREVIEW = "厂所名录-"
UNITS_PREVIEW_OLD = "Fact and Comp-"

ENCODINGS = ["utf-8-sig", "utf-8", "gb18030", "big5", "utf-16", "latin-1"]

# 统计块:字段名 ↔ 表头。写出去、读回来共用一份,免得两头对不上
STAT_COLS = [("staff", "职工总数"), ("tech", "技术人员"), ("plant", "厂房面积"),
             ("floor", "建筑面积"), ("assets", "固定资产"), ("output", "工业总产值"),
             ("sales", "销售收入"), ("profit", "实现利润")]

# 页码的常见写法。每条给出正则与取数的组号;认哪一条,看谁的数字最像页码。
PAGE_PATTERNS = [
    ("已是本工具的写法", re.compile(r"^[ \t]*<!--\s*p\.(\d{1,4})\s*-->[ \t]*$", re.M)),
    ("HTML 注释", re.compile(r"^[ \t]*<!--\s*(\d{1,4})\s*-->[ \t]*$", re.M)),
    ("第N页", re.compile(r"^[ \t]*第\s*(\d{1,4})\s*页[ \t]*$", re.M)),
    ("方括号", re.compile(r"^[ \t]*\[\[?\s*(\d{1,4})\s*\]?\][ \t]*$", re.M)),
    ("花括号", re.compile(r"^[ \t]*\{\{?\s*(\d{1,4})\s*\}?\}[ \t]*$", re.M)),
    ("破折号夹注", re.compile(r"^[ \t]*[-—–·\*]{1,2}\s*(\d{1,4})\s*[-—–·\*]{1,2}[ \t]*$", re.M)),
    ("锚点", re.compile(r'^[ \t]*<a\s+(?:id|name)="(?:page|p)?(\d{1,4})"\s*/?>(?:</a>)?[ \t]*$',
                        re.M | re.I)),
    ("P123", re.compile(r"^[ \t]*[Pp]\.?\s*(\d{1,4})[ \t]*$", re.M)),
    ("孤零数字", re.compile(r"^[ \t]*(\d{1,4})[ \t]*$", re.M)),
]


# 汉字(含中日韩标点、全角符号)之间的空格一律是转换留下的,没有意义
_CJK = "\u3400-\u4dbf\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"
# 只吃空格,不吃制表符 —— 制表符多半是分栏的(订正表就是 TSV),吃掉就把两列并了
CJK_GAP = re.compile("(?<=[%s]) +(?=[%s])" % (_CJK, _CJK))


# 型号里的连字符被认成了汉字「一」:TQ一16、DJS一131、X一2型、JDK一331。
# 《上海电子仪表工业志》第一章一篇就 117 处。夹在拉丁字母与数字之间的「一」,
# 中文里没有这种写法,一律是连字符认岔了 —— 不改,型号认不出来,更要紧的是
# 跟总表里的 DJS-131 对不上,判重拦不住,同一台机器要收两遍。
DASH_ONE = re.compile(r"(?<=[A-Za-z])[一―−](?=[0-9])")


def fix_model_dash(text):
    """把型号里认成「一」的连字符改回来。返回 (改过的文本, 改了几处)。"""
    return DASH_ONE.subn("-", text)


def squeeze_cjk_spaces(text):
    """去掉汉字中间的空格。

    转换稿常在原书断行处留一个空格,成了「北京计算 机一厂」。空格是找厂名时
    往左走的边界,留着就截出「机一厂」这种鬼名字。标题和表格不动 —— 那里的
    空格是分栏用的。"""
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        out.append(line if s[:1] in ("#", "|") or s.startswith("```")
                   else CJK_GAP.sub("", line))
    return "\n".join(out)


def read_text(path):
    """挨个试编码,返回 (正文, 用的哪一种)。顺手把换行和汉字间的空格归一。"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        # 解出来若满是替换符或几乎没有汉字,多半是解错了,接着试
        if "�" in text[:4000]:
            continue
        if enc == "latin-1" and len(re.findall(r"[一-鿿]", text[:4000])) < 5:
            continue
        return squeeze_cjk_spaces(
            text.replace("\r\n", "\n").replace("\r", "\n")), enc
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n"), "utf-8(有乱码)"


def load_fixes(path):
    """读字形订正表:一行一条「错<TAB>对」,# 开头算注解。

    转换稿总有认错的字,「安徽无线电厂」成了「安做无线电厂」。这种错改不出
    规律,只能一本书一张表,跟着书走。"""
    if not path:
        return []
    text, _enc = read_text(path)
    out = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cell = line.rstrip("\n").split("\t")
        if len(cell) >= 2 and cell[0]:
            out.append((cell[0], cell[1]))
    return out


def apply_fixes(text, fixes):
    """逐条改,并回报每条改了几处 —— 表里写错了字,得看得见,不能默默不改。"""
    ledger = []
    for bad, good in fixes:
        n = text.count(bad)
        if n:
            text = text.replace(bad, good)
        ledger.append((bad, good, n))
    return text, ledger


def _monotonic(nums):
    """页码该是大体递增的;脚注号 [1][2][1] 不是。返回递增的比例。"""
    if len(nums) < 3:
        return 0.0
    ups = sum(1 for a, b in zip(nums, nums[1:]) if b >= a)
    return ups / float(len(nums) - 1)


def detect_page_marks(text):
    """把各种页码写法都试一遍,按「像不像页码」排出来。"""
    out = []
    for name, pat in PAGE_PATTERNS:
        nums = [int(m.group(1)) for m in pat.finditer(text)]
        if len(nums) < 3:
            continue
        mono = _monotonic(nums)
        out.append({"name": name, "pattern": pat, "count": len(nums),
                    "monotonic": mono, "first": nums[0], "last": nums[-1],
                    "ok": mono >= 0.9})
    out.sort(key=lambda d: (d["ok"], d["count"]), reverse=True)
    return out


def normalize_page_marks(text, force=None):
    """把认出来的页码写法归一成 `<!-- p.N -->`。返回 (正文, 用了哪条, 改了几处)。"""
    cands = [c for c in detect_page_marks(text) if c["ok"]]
    if force:
        cands = [c for c in detect_page_marks(text) if c["name"] == force] or cands
    if not cands:
        return text, None, 0
    pick = cands[0]
    if pick["name"] == "已是本工具的写法":
        return text, pick["name"], pick["count"]
    new = pick["pattern"].sub(lambda m: "<!-- p.%s -->" % int(m.group(1)), text)
    return new, pick["name"], pick["count"]


# ---------------------------------------------------------------- 接断行

SENT_END = "。！？；.!?;：:」』】》）)"
_SKIP = re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|\d+[.、)]\s|>|\||```|<!--|---\s*$)")


def hard_wrapped(text):
    """看这份稿子是不是照原书的行宽硬断的。

    转换稿常把版心一行原样存成一行:「北京市半导体」「器件研究所」各一行,
    厂名就断成了两截,怎么认都认不出。判据是「多少行没收在句读上」。"""
    body = [l.strip() for l in text.splitlines()
            if l.strip() and not _SKIP.match(l)]
    if len(body) < 8:
        return False, 0.0
    open_ended = sum(1 for l in body if l[-1] not in SENT_END)
    share = open_ended / float(len(body))
    return share >= 0.3, share


def reflow_soft(text):
    """把硬断的行接回段落:上一行没收在句读上,下一行又不是标题/表格/列表,就接上。

    比 `gaz md` 的那一套轻:那边要对付 OCR 的碎行,这边只接明显断开的。
    已经一段一行的稿子跑一遍也不会有事 —— 每行都收在句号上,一行也不会接。"""
    out = []
    for line in text.splitlines():
        s = line.rstrip()
        if not s.strip() or _SKIP.match(s) or not out or not out[-1].strip():
            out.append(s)
            continue
        prev = out[-1].rstrip()
        if _SKIP.match(prev) or not prev:
            out.append(s)
            continue
        if prev[-1] in SENT_END:
            out.append(s)
        else:
            out[-1] = prev + s.lstrip()
    return "\n".join(out)


# ---------------------------------------------------------------- 看一眼

def inspect(text, path=""):
    """先看看这份稿子长什么样 —— 抽取之前值得花十秒钟。"""
    lines = text.splitlines()
    heads = [l for l in lines if re.match(r"^#{1,6}\s+\S", l)]
    levels = Counter(len(re.match(r"^(#+)", h).group(1)) for h in heads)
    tables = sum(1 for l in lines if l.strip().startswith("|"))

    wrapped, share = hard_wrapped(text)
    scan = reflow_soft(text) if wrapped else text
    units = Counter()
    for l in scan.splitlines():
        for nm in EX.unit_names(l):
            units[nm] += 1

    cues = {k: len(re.findall(v, text)) for k, v in [
        ("前身 / 原名", r"前身|原名|原为|原系"),
        ("改名 / 更名", EX.RENAME),
        ("划归 / 隶属", EX.TRANSFER),
        ("合并 / 并入", EX.MERGE),
        ("始建 / 成立", EX.BIRTH),
        ("撤销 / 停办", EX.DEATH),
        ("试制 / 投产", EX.MADE),
        ("职工 / 产值", r"职工|技术人员|总产值|销售收入|固定资产|利润"),
    ]}

    return {
        "path": path, "chars": len(text), "lines": len(lines),
        "headings": len(heads), "levels": dict(sorted(levels.items())),
        "sample_headings": [h.strip() for h in heads[:12]],
        "table_lines": tables, "wrapped": wrapped, "wrap_share": share,
        "pages": detect_page_marks(text),
        "units": units.most_common(15),
        "unit_total": len(units),
        "cues": cues,
    }


def report(info, log=print):
    log("稿子:%s" % (info["path"] or "(未命名)"))
    log("  %d 字,%d 行,%d 处标题%s" % (
        info["chars"], info["lines"], info["headings"],
        ("(层级 " + "、".join("%d 级×%d" % (k, v) for k, v in info["levels"].items()) + ")")
        if info["levels"] else ""))
    if info["sample_headings"]:
        log("  头几处标题:")
        for h in info["sample_headings"][:8]:
            log("     " + h[:60])
    if info["table_lines"]:
        log("  %d 行像表格 —— 表里的数字本工具不还原,那部分仍要手录" % info["table_lines"])
    if info["wrapped"]:
        log("  %.0f%% 的行没收在句读上 —— 照原书行宽硬断的,抽取前会先接回段落"
            % (info["wrap_share"] * 100))

    if info["pages"]:
        for c in info["pages"][:3]:
            log("  页码写法「%s」%d 处,%d→%d,递增率 %.0f%%%s"
                % (c["name"], c["count"], c["first"], c["last"], c["monotonic"] * 100,
                   "  ← 采用" if c["ok"] and c is info["pages"][0] else ""))
    else:
        log("  没认出页码 —— 出处会退到篇章节(如「…·第三章」),仍查得回去")

    log("  认出 %d 个单位名,最常出现的几个:" % info["unit_total"])
    for nm, n in info["units"][:8]:
        log("     %s ×%d" % (nm, n))

    log("  志书套语的出现次数(抽取全靠这些词):")
    for k, v in info["cues"].items():
        log("     %-12s %d" % (k, v))
    weak = [k for k, v in info["cues"].items() if v == 0]
    if weak:
        log("  注意:%s 一次都没出现 —— 这几类字段多半抽不到。" % "、".join(weak))


# ---------------------------------------------------------------- 抄旧「取否」

#: 每一张认哪几栏作钥匙 —— 重跑一遍时据以认出「这一行上一遍点过头」。
#: 跟 toxlsx 判重用的是同一套钥匙,两头对得上。
KEEP_KEYS = {
    "units": ("Unit",),
    "semi": ("Product", "Factory", "Time"),
    "comp": ("Product", "Time"),
    "names": ("Unit", "Name", "From"),
    "fills": ("Unit", "栏"),
}


def keep_key(tag, row):
    return tuple(re.sub(r"\s+", "", _cell(row.get(k))) for k in KEEP_KEYS[tag])


def read_keeps(path):
    """上一份待核工作簿里,哪几行点过头。{表: {钥匙: 取否}};没有那份文件就空的。

    重跑一本志书会把这份工作簿整个重写 —— 从前重写就把「取否」一列抹平了,
    核到一半的人不声不响从头再来。抄过来的只是那一列:**上一份里改过的字
    抄不过来**,那些字要么早已并进总表,要么随这一份重写没了。所以半道上要
    重跑,先 `gaz xlsx --from` 把核过的并掉。"""
    if not path or not os.path.exists(path):
        return {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception:
        return {}          # 开不了就当没有 —— 这一步是锦上添花,不该拦住重跑
    out = {}
    for tag in KEEP_KEYS:
        name = review_tab(wb, tag)
        if name is None:
            continue
        marks = {}
        for r in _sheet_rows(wb[name]):
            k = keep_key(tag, r)
            if any(k) and _cell(r.get("keep")):
                marks[k] = _cell(r.get("keep"))
        if marks:
            out[tag] = marks
    return out


# ---------------------------------------------------------------- 补格子

#: 哪些栏值得回头补,以及补法。
#:
#: * `字段` 抽出来的行里叫什么;`表头` 总表那张表里叫什么(两处名字历来不一样)
#: * `实录` —— 这一栏是照志书原文誊的(地址、隶属、性质……),还是工具推的
#:   (City、省是按书名/章标题推的)。推的那几栏只信得过有专条的单位:
#:   顺带提到的一家,它的 City 是「这本书讲的那个市」,不是它自己在哪儿 ——
#:   《上海电子仪表工业志》里点到的清华大学,照书推就成了上海。
#: * `或不一` —— 两边都有值而对不上时,报不报。长栏(产品、创办、别名)一概
#:   不报:总表里那一份是人核过、动手改过的,拿同一段原文再机读一遍,不是
#:   新证据,报出来只会引着人把核过的改回机器的样子。
FILL_FIELDS = [
    # 字段,          表头,      实录, 或不一
    ("Industry",    "Industry",   True,  True),
    ("Start Date",  "Start Date", True,  True),
    ("End Date",    "End Date",   True,  True),
    ("Add.",        "Add.",       True,  True),
    ("district",    "区",         True,  True),
    ("City",        "City",       False, True),
    ("省",          "省",         False, True),
    ("隶属",        "隶属",       True,  True),
    ("主管单位",    "主管单位",   True,  True),
    ("性质",        "性质",       True,  True),
    ("Product",     "Product",    True,  False),
    ("Founder",     "Founder",    True,  False),
    ("别名",        "别名",       True,  False),
]


def _cell(v):
    """格子里的字,拿来比对用。日期存成 19560000.0 这种浮点是常事。"""
    t = str("" if v is None else v).strip()
    if re.fullmatch(r"\d+\.0", t):
        t = t[:-2]
    return t


#: 八位日期分三截,每一截「00」就是不知道:19870500 = 1987 年 5 月,日不详。
_DATE_PARTS = ((0, 4), (4, 6), (6, 8))


def _date_rel(old, new):
    """两个八位日期,后来这一个比原来那个细、还是粗、还是两回事。"""
    if not (re.fullmatch(r"\d{8}", old) and re.fullmatch(r"\d{8}", new)):
        return None
    finer = coarser = False
    for a, b in _DATE_PARTS:
        o, n = old[a:b], new[a:b]
        zo, zn = set(o) == {"0"}, set(n) == {"0"}
        if not zo and not zn and o != n:
            return "不一"          # 都写明了而不同 —— 换了个年份,那是两回事
        if zo and not zn:
            finer = True
        if zn and not zo:
            coarser = True
    if finer and not coarser:
        return "细"
    if coarser and not finer:
        return "粗"
    return "同" if old == new else "不一"


def refine(old, new):
    """总表里那一格与这一遍认出的,是「同」「细」(这一遍更具体)「粗」还是「不一」。

    这一条管的是要不要拿去烦人。**粗的一概不报** —— 总表里写着
    「虹桥路951弄2号」,这一遍照同一段原文只认出「虹桥路951弄」(门牌被断行
    切掉了),摆上去问人要不要换,换了就是把已有的门牌号丢掉。同理
    19820100 → 19820000:月份写明的那一份更值钱。

    细的另算一种:19870000 → 19870500 是实打实的长进,报,但不算「对不上」——
    两边说的是一回事,只是这一遍说得更细。"""
    old, new = old.strip(), new.strip()
    if old == new:
        return "同"
    d = _date_rel(old, new)
    if d:
        return d
    # 字面上一个套着另一个:长的那个更具体
    if old.startswith(new) or new in old:
        return "粗"
    if new.startswith(old):
        return "细"
    return "不一"


def _remark_for(remark, label):
    """备注里针对这一栏说的那一句(「隶属据章节标题「…」」);没有就空。"""
    for part in str(remark or "").split("；"):
        if part.strip().startswith(label):
            return part.strip()
    return ""


def master_name(master, kidx, nm):
    """总表里那一行挂的是哪个名字 —— 补格子要照总表的名字写,不然对不上行。"""
    if nm in master:
        return nm
    canon = (kidx or {}).get(nm, nm)
    return canon if canon in master else nm


def in_master(nm, master, kidx=None):
    """这家早已在总表里了么。别名也算 ——「四机部15所」说的就是表里那家。"""
    nm = str(nm or "").strip()
    if not nm or not master:
        return False
    return nm in master or (kidx or {}).get(nm, nm) in master


def plan_fills(units, master, kidx=None):
    """已在总表里的单位,这一遍能往空格子里补什么。

    `master` 是 {单位名: 那一行} —— `toxlsx.read_units_full` 读出来,按 `raw`
    作键。`kidx` 是别名→正名(`extract.known_index`),认得出「四机部15所」
    说的就是表里那家。

    只报两种:

    * **补** —— 总表那一格空着,这一遍认出了值。这是重跑一遍真正的所得。
    * **对不上** —— 两边都有值而不同。只报短栏(见 FILL_FIELDS),且只报
      有专条的单位:顺带提到的一家,凭一句话跟人核过的值争,争不出道理。

    总表没有的单位不在此列 —— 那些照旧走「待核·厂所」那张,该核的是名字。
    """
    kidx = kidx or {}
    out = []
    for r in units:
        nm = str(r.get("Unit", "")).strip()
        if not nm:
            continue
        row = master.get(nm) or master.get(kidx.get(nm, nm))
        if row is None:               # 新单位,不归这张表管
            continue
        entry = r.get("role") == "专条"
        for key, head, literal, may_clash in FILL_FIELDS:
            new = _cell(r.get(key))
            if not new:
                continue
            if not literal and not entry:
                # 推出来的那几栏,只信得过有专条的
                continue
            old = _cell(row.get(key))
            if not old:
                kind = "补"
            elif not entry:
                # 顺带提到的一家,凭一句话跟人核过的值争,争不出道理
                continue
            else:
                rel = refine(old, new)
                if rel in ("同", "粗"):
                    continue
                if rel == "细":
                    kind = "更细"
                elif may_clash:
                    kind = "对不上"
                else:
                    continue
            # 凭据要摆立这一格的那一句 —— 摆整行拼起来的三句,常常不含这一句。
            # 据章节标题定的那几格,原文里压根没有那一句,凭据在备注里
            # (「性质据章节标题「第四章中外合资电子工业企业」…」)—— 那一句
            # 正是核对时最该看见的:标题继承最不可靠,见 affil.py
            why = ((r.get("ev") or {}).get(key)
                   or _remark_for(r.get("Remark", ""), key)
                   or r.get("evidence", ""))
            out.append({"keep": "", "Unit": master_name(master, kidx, nm), "栏": head,
                        "总表现值": old, "值": new, "种类": kind,
                        "evidence": why, "Source": r.get("Source", ""),
                        "role": r.get("role", "")})
    # 一家一家挨着摆,同一家的几格排在一处 —— 一个单位判一回,不必来回翻
    order = {"补": 0, "更细": 1, "对不上": 2}
    out.sort(key=lambda d: (d["Unit"], order.get(d["种类"], 9), d["栏"]))
    return out


# ---------------------------------------------------------------- 本地 Excel

def write_xlsx(path, res, city="", book="", stats_year=1990, log=print,
               master=None, kidx=None):
    """把抽出来的东西写成一份本地工作簿,版式与 CN_Electronic_Industry.xlsx 一致,
    另附几张「待核·」表,把出处、原文、置信一并摆上,好在 Excel 里逐条核对。

    `master` 给了(`{单位名: 总表那一行}`),就替你把重跑一本核过的志书这件事
    办省一点:已在总表里的行标上「已收」,新认出来的格子另摆一张「待核·补格子」。
    不给就照旧,像头一回跑一本新志书那样。"""
    import openpyxl
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    # 这份工作簿上一回的「取否」—— 重写之前先抄下来,不然核到一半的人白干
    keeps = read_keeps(path)
    carried = [0]

    def keep_of(tag, row):
        v = (keeps.get(tag) or {}).get(keep_key(tag, row), "")
        if v:
            carried[0] += 1
        return v

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    stat_labels = [label for _k, label in STAT_COLS]
    stat_keys = [k for k, _ in STAT_COLS]

    def num(v):
        s = str(v if v is not None else "").strip()
        if s == "":
            return None
        if re.fullmatch(r"\d{8}", s):
            return int(s)
        try:
            f = float(s)
            return int(f) if f == int(f) else f
        except ValueError:
            return s

    # ---- 照总表体例的那一张:两行表头,与原表一模一样
    sheet = PREVIEW
    ws = wb.create_sheet(sheet)
    ws.append(["", "Industry", "Product", "Start Date", "End Date", "Founder", "City", "Add.",
               stats_year] + [""] * 7 + ["Remark", "Source", "别名"])
    ws.append([""] * 8 + stat_labels + ["", ""])
    for r in res["units"]:
        ws.append([r.get("Unit", ""), r.get("Industry", ""), r.get("Product", ""),
                   num(r.get("Start Date")), num(r.get("End Date")), r.get("Founder", ""),
                   r.get("City", city), r.get("Add.", "")]
                  + [num(r.get(k)) for k in stat_keys]
                  + [r.get("Remark", ""), r.get("Source", ""), r.get("别名", "")])
    ws.merge_cells(start_row=1, start_column=9, end_row=1, end_column=16)
    ws.cell(row=1, column=19).font = Font(bold=True)
    # 这张表照原表体例生成,好让你一眼看出将来落在地图上是什么样 —— 但读回来
    # 只读「待核」。不写明白,在这儿改半天不算数,还没有一处告诉你。
    note = ws.cell(row=1, column=21,
                   value="↑ 此表照 CN_Electronic_Industry.xlsx 的体例生成,供预览与粘贴。"
                         "改这里不算数 —— 要改请改「" + REVIEW_UNITS + "」那张。")
    note.font = Font(italic=True, color="996600")
    ws.cell(row=1, column=9).alignment = Alignment(horizontal="center")
    for c in range(1, 19):
        ws.cell(row=1, column=c).font = Font(bold=True)
        ws.cell(row=2, column=c).font = Font(bold=True)
    ws.freeze_panes = "A3"

    def flat(name, cols, rows, tag, keys=None):
        w = wb.create_sheet(name)
        w.append(["取否"] + cols)
        for c in range(1, len(cols) + 2):
            w.cell(row=1, column=c).font = Font(bold=True)
        for r in rows:
            w.append([keep_of(tag, r)]
                     + [num(r.get(k)) if k in ("Time", "From") else r.get(k, "")
                        for k in (keys or cols)])
        w.freeze_panes = "B2"
        return w

    flat(REVIEW_SEMI, ["Product", "别名", "Research Insti", "Factory", "产量", "Time",
                          "Personnel", "Remark"], res["semi"], "semi")
    flat(REVIEW_COMP, ["Product", "字长", "内存", "Speed（次秒）", "Research Insti",
                          "Factory", "用户", "产量", "别名", "Time", "Personnel", "Remark"],
         res["comp"], "comp")
    # 待核那份的沿革表也照总表的次序摆:序、单位、名称、起、至、关系
    nh = wb.create_sheet(REVIEW_NAMES)
    # 表头写成中文,把话说死:「Unit」看着像「这一行这家单位叫什么」,而它其实
    # 是钥匙 —— 一家单位的几行都写同一个今名。改叫「单位(今名)」就不会看岔。
    nh.append(["取否", "序", "单位(今名)", "当时名称", "自哪年起", "Remark", "Source"])
    for c in range(1, 8):
        nh.cell(row=1, column=c).font = Font(bold=True)
    # 同一单位的几段挨在一处、按年份排好、编上序号 —— 抽取顺序堆着的话,
    # 一家单位的五个名字散在表里,谁先谁后全靠自己比对那串八位数字
    def _key(r):
        t = re.sub(r"\D", "", str(r.get("From", "")))
        return (str(r.get("Unit", "")), int(t.ljust(8, "0")[:8]) if t else 99999999)

    seq = {}
    for r in sorted(res["names"], key=_key):
        who = str(r.get("Unit", ""))
        seq[who] = seq.get(who, 0) + 1
        nh.append([keep_of("names", r), seq[who], who, r.get("Name", ""),
                   str(r.get("From", "")), r.get("Remark", ""), r.get("Source", "")])
    nh.freeze_panes = "C2"
    for i, wid in enumerate([6, 5, 24, 26, 11, 34, 30], start=1):
        nh.column_dimensions[get_column_letter(i)].width = wid
    # 「序」是这张表最容易看岔的一格 —— 它不是行号,是这家单位的第几个名字。
    # 不写明白,谁也不知道那个 1、2、3 从哪儿来。
    nh_note = nh.cell(row=1, column=9,
                      value="↑ 一行 = 某单位某一段时间里叫什么。念法:"
                            "「自哪年起」那一年起,这家单位叫「当时名称」那个名字,到下一行那年为止。"
                            "「单位(今名)」是它如今的正名,一家单位的几行都写同一个 —— 那是钥匙,"
                            "不是它当时的名字。"
                            "「序」是这家单位的第几个名字,1 最早 —— 不是行号。"
                            "两家单位并成一家,不在这张表里,写进「待核」表的「创办」列。")
    nh_note.font = Font(italic=True, color="996600")

    # ---- 待核:核对用的那一张,原文摆在最后一列
    rv = wb.create_sheet(REVIEW_UNITS)
    # 「已收」紧挨着名字,而且在冻住的那几列之内 —— 它答的是「这一行还要不要看」,
    # 得在动手之前就看见。搁到表尾去,要横拉一趟才知道刚核的这家早已在表里了。
    rv_head = (["取否", "单位", "别名", "已收", "置信", "出处", "据以立论的原文",
                "行业", "产品",
                "始建", "终止", "创办", "地址", "City", "省", "区",
                "隶属", "主管单位", "性质"] + stat_labels
               + ["统计年", "备注", "来路", "页"])
    rv.append(rv_head)
    for c in range(1, len(rv_head) + 1):
        rv.cell(row=1, column=c).font = Font(bold=True)
    for r in res["units"]:
        rv.append([keep_of("units", r), r.get("Unit", ""), r.get("别名", ""),
                   "已在表内" if in_master(r.get("Unit", ""), master, kidx) else "",
                   r.get("confidence", ""), r.get("Source", ""),
                   r.get("evidence", ""), r.get("Industry", ""), r.get("Product", ""),
                   num(r.get("Start Date")), num(r.get("End Date")), r.get("Founder", ""),
                   r.get("Add.", ""), r.get("City", city), r.get("省", ""),
                   r.get("district", ""),
                   r.get("隶属", ""), r.get("主管单位", ""), r.get("性质", "")]
                  + [num(r.get(k)) for k in stat_keys]
                  + [r.get("统计年", ""), r.get("Remark", ""),
                     r.get("role", ""), r.get("page", "")])
    rv.freeze_panes = "E2"
    for i, wid in enumerate([6, 28, 24, 9, 6, 30, 90, 10, 22, 11, 11, 30, 20, 10, 8, 7,
                             9, 20, 9] + [9] * 8 + [8] + [30, 6, 6], start=1):
        rv.column_dimensions[get_column_letter(i)].width = wid
    ev_col = rv_head.index("据以立论的原文") + 1
    for row in rv.iter_rows(min_row=2, min_col=ev_col, max_col=ev_col):
        row[0].alignment = Alignment(wrap_text=False, vertical="top")

    # ---- 待核·补格子:已在总表里的单位,这一遍新认出来的格子
    fills = plan_fills(res["units"], master or {}, kidx) if master else []
    if fills:
        fw = wb.create_sheet(REVIEW_FILL)
        fw.append(["取否", "单位", "栏", "总表现值", "这一遍认出的", "种类",
                   "凭据(原文)", "出处"])
        for c in range(1, 9):
            fw.cell(row=1, column=c).font = Font(bold=True)
        for f in fills:
            fw.append([keep_of("fills", f), f["Unit"], f["栏"], f["总表现值"], f["值"],
                       f["种类"], f["evidence"], f["Source"]])
        fw.freeze_panes = "C2"
        for i, wid in enumerate([6, 26, 12, 34, 34, 8, 90, 30], start=1):
            fw.column_dimensions[get_column_letter(i)].width = wid
        note = fw.cell(row=1, column=10,
                       value="↑ 一行 = 总表里某家的某一个格子。这些单位早已在总表里,"
                             "「待核·厂所」那张不必再核一遍 —— 重跑一本核过的志书,"
                             "所得就是这几格。"
                             "「补」= 总表那一格空着,写 y 就填上去。"
                             "「更细」= 总表里已有,而这一遍说得更具体"
                             "(1987年 → 1987年5月):说的是一回事,不是两说。"
                             "「对不上」= 两边都有值而不同:总表那一份是你核过的,"
                             "写 y 才拿这一遍的盖过去,拿不准就空着。"
                             "并表时只动写了 y 的那几格,别的一格不碰。")
        note.font = Font(italic=True, color="996600")

    widths = {sheet: [26, 10, 20, 11, 11, 40, 9, 22] + [9] * 8 + [40, 26],
              REVIEW_SEMI: [6, 28, 20, 26, 24, 8, 11, 14, 30],
              REVIEW_COMP: [6, 30, 8, 12, 14, 30, 24, 26, 8, 20, 14, 16, 34],
              REVIEW_NAMES: [6, 26, 30, 11, 40, 26]}
    for nm, ws_widths in widths.items():
        w = wb[nm]
        for i, wid in enumerate(ws_widths, start=1):
            w.column_dimensions[get_column_letter(i)].width = wid

    # 要核的排在前头,预览那张垫底,打开就停在「待核·厂所」上 —— 从前它排在
    # 最末,一开文件停在预览表上:那张 A 列是一列光秃秃的单位名,表头空着,
    # 又没有「取否」列。要核对的人第一眼看见的,恰恰是唯一改了不算数的那张。
    #
    # 次序**按名单摆**,不按位移算。从前写的是
    # `move_sheet(REVIEW_UNITS, offset=-(len(sheetnames) - 1))`,那句只在
    # 「待核·厂所」恰好是最后一张时才对 —— 后头添出「待核·补格子」之后,
    # 它算出来的位移把表挪到了倒数第二张,一开文件又停回预览表上。
    want = [REVIEW_UNITS, REVIEW_FILL, REVIEW_SEMI, REVIEW_COMP, REVIEW_NAMES, sheet]
    order = [n for n in want if n in wb.sheetnames]
    wb._sheets = ([wb[n] for n in order]
                  + [w for w in wb.worksheets if w.title not in order])
    wb.active = wb.sheetnames.index(REVIEW_UNITS)
    for w in wb.worksheets:
        w.sheet_view.tabSelected = (w.title == REVIEW_UNITS)

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    try:
        wb.save(path)
    except PermissionError:
        # Windows 上 Excel 开着文件就锁住它。抽了半天全在内存里,不能到末了
        # 一句 PermissionError 全丢了 —— 换个名字先存下来。
        stem, ext = os.path.splitext(path)
        alt, n = stem + "-新" + ext, 2
        while os.path.exists(alt):
            alt, n = "%s-新%d%s" % (stem, n, ext), n + 1
        wb.save(alt)
        log("！写不进 %s —— 多半正开在 Excel 里,文件被锁着。"
            % os.path.basename(path))
        log("  这一份改存到 %s;关掉 Excel 再跑一遍,才会写回原名。"
            % os.path.basename(alt))
        return alt
    log("Excel 已写到 %s" % path)
    tabs = [REVIEW_UNITS, REVIEW_SEMI, REVIEW_COMP, REVIEW_NAMES]
    if fills:
        tabs.append(REVIEW_FILL)
    log("  要核的%d张:%s" % (len(tabs), "、".join(tabs)))
    log("  **%d张都要核** ——「取否」都在 A 列,写 y 的行才收,一张漏了那一张就全不进表。"
        % len(tabs))
    log("  打开停在「%s」上头。" % REVIEW_UNITS)
    log("  另有「%s」一张,只供看与粘,改它不算数。" % sheet)
    if carried[0]:
        log("")
        log("上一份里点过头的 %d 行,「取否」照抄过来了 —— 核到一半重跑,不必从头再点。"
            % carried[0])
        log("  **上一份里改过的字没抄过来。** 抄得过来的只有「取否」那一列:"
            "改过的字这一遍是照稿子重认的,谁对谁错不该由工具替你定。")
        log("  半道上要重跑,稳妥的次序是:先 `xlsx --from` 把核过的并进总表,再重跑。")
    if master:
        seen = sum(1 for r in res["units"] if in_master(r.get("Unit", ""), master, kidx))
        log("")
        log("这一本是**重跑**:%d 家里有 %d 家早已在总表里,标着「已收」。"
            % (len(res["units"]), seen))
        log("  那 %d 家不必再核一遍 —— 核过的记录在总表里,并表时也一概跳过。" % seen)
        if fills:
            add = sum(1 for f in fills if f["种类"] == "补")
            fine = sum(1 for f in fills if f["种类"] == "更细")
            log("  重跑一遍的所得摆在「%s」那张:%d 格总表空着可补、"
                "%d 格这一遍说得更细、%d 格两边对不上。"
                % (REVIEW_FILL, add, fine, len(fills) - add - fine))
        else:
            log("  这一遍没认出总表里缺的格子 —— 那就是说,这一本已经榨干了。")
    return path


# ---------------------------------------------------------------- 核过再读回来

KEEP_YES = {"y", "yes", "true", "1", "是", "要", "✓", "√"}

# 「待核」表头 → 抽取时用的字段名
REVIEW_COLS = {"取否": "keep", "来路": "role", "置信": "confidence", "页": "page",
               "序": None,
               "单位(今名)": "Unit", "当时名称": "Name", "自哪年起": "From",
               "别名": "别名",
               "单位": "Unit", "行业": "Industry", "产品": "Product",
               "始建": "Start Date", "终止": "End Date", "创办": "Founder",
               "地址": "Add.", "省": "省", "区": "district",
               "City": "City", "城市": "City", "市": "City",
               "隶属": "隶属", "主管单位": "主管单位", "性质": "性质",
               # 补格子那张。「已收」只是给人看的记号,不是字段
               "已收": None, "栏": "栏", "总表现值": "总表现值",
               "这一遍认出的": "值", "种类": "种类", "凭据(原文)": "evidence",
               "备注": "Remark", "出处": "Source", "统计年": "统计年",
               "据以立论的原文": "evidence"}
REVIEW_COLS.update({label: key for key, label in STAT_COLS})


DATE_COLS = ("Start Date", "End Date", "Time", "From")


def date_cell(v):
    """把手填的日期归到八位整数上。

    核对时是要直接改字的,不会有人记得「1958年建厂」该写成 19580000。
    四位年补成 19580000,六位补成 19580300,「1958年3月」照样认;Excel 把
    1958-03-01 存成了日期对象,也认。认不出就原样留着,不猜。"""
    if v is None or str(v).strip() == "":
        return ""
    if hasattr(v, "year") and hasattr(v, "month"):        # Excel 的日期格
        return "%04d%02d%02d" % (v.year, v.month, getattr(v, "day", 0) or 0)
    t = str(v).strip()
    if re.fullmatch(r"\d{8}", t):
        return t
    if re.fullmatch(r"\d{6}", t):
        return t + "00"
    if re.fullmatch(r"\d{4}", t) and 1800 <= int(t) <= 2100:
        return t + "0000"
    return cndate.parse(t) or t


def _yes(v):
    return str("" if v is None else v).strip().lower() in KEEP_YES


def _sheet_rows(ws):
    """一张表读成 [{表头: 值}],整行空的跳过。"""
    head = [c.value for c in ws[1]]
    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        r = {}
        for h, v in zip(head, row):
            if not h:
                continue
            # 表头行末尾那句以「↑」起头的话是写给人看的注,不是一列数据
            if str(h).startswith("↑"):
                continue
            k = REVIEW_COLS.get(h, h)
            if k is None:      # 「序」是给人看的次序,不是字段
                continue
            r[k] = date_cell(v) if k in DATE_COLS else ("" if v is None else v)
        out.append(r)
    return out


def merge_by_name(rows):
    """核过之后名字写成一样的,就当同一家,合成一行。

    这正是核名字要干的事:「四机部15所」「电子部15所」「电子部第15所」本是
    一个所,随部委改制换了牌子。在表里把它们都改成一个名字,这里就并起来,
    各自的出处一并留着 —— 并了以后仍要查得回去是哪一节说的。"""
    out, idx, merged = [], {}, 0
    for r in rows:
        nm = str(r.get("Unit", "")).strip()
        if not nm:
            continue
        if nm not in idx:
            idx[nm] = dict(r, Unit=nm)
            out.append(idx[nm])
            continue
        merged += 1
        base = idx[nm]
        for k, v in r.items():
            if v not in ("", None) and base.get(k) in ("", None):
                base[k] = v
        for k in ("Source", "Remark"):
            a, b = str(base.get(k, "") or ""), str(r.get(k, "") or "")
            if b and b not in a:
                base[k] = (a + "；" + b) if a else b
        # 并进来的那些名字要留着 —— 挑一个当正名,不等于别的就不算数了
        alias = [x.strip() for x in
                 (str(base.get("别名", "") or "") + "、" + str(r.get("别名", "") or "")).split("、")]
        base["别名"] = "、".join(dict.fromkeys(
            x for x in alias if x and x != nm))
    return out, merged


#: 读回来的时候,每一张认哪些标签 —— 新名在前,从前用过的跟在后头。
#: 改名那天谁手上正核着一章,那一章的工夫不能白费。
REVIEW_TABS = {
    "fills": (REVIEW_FILL,),
    "units": (REVIEW_UNITS, "待核"),
    "semi": (REVIEW_SEMI, toxlsx.SHEET_SEMI, toxlsx.OLD_NAMES[toxlsx.SHEET_SEMI]),
    "comp": (REVIEW_COMP, toxlsx.SHEET_COMP, toxlsx.OLD_NAMES[toxlsx.SHEET_COMP]),
    "names": (REVIEW_NAMES, toxlsx.SHEET_NAMES, toxlsx.OLD_NAMES[toxlsx.SHEET_NAMES]),
}


def review_tab(wb, tag):
    """这一张在这本待核工作簿里挂的什么标签;一个也不在就 None。"""
    for name in REVIEW_TABS[tag]:
        if name in wb.sheetnames:
            return name
    return None


def book_city_of(wb):
    """旧本子的城市:预览表名末尾缀的那一截(「厂所名录-北京」/「Fact and Comp-北京」)。

    新本子的预览表不缀城市了 —— 城市写在待核表自己的 City 列里,一行一个。
    这个函数只为读旧本子留着。"""
    for name in wb.sheetnames:
        for prefix in (UNITS_PREVIEW, UNITS_PREVIEW_OLD):
            if name.startswith(prefix):
                return name[len(prefix):]
    return ""


def read_review(path):
    """把核过的工作簿读回来:四张表里「取否」写了 y 的行。

    落笔的地方只有一处 —— Excel。keep 在那儿打,认错的字也在那儿改,读回来
    的就是你改过的样子。TSV 只当留底,不再回头去读:两处都能改,改了哪一处
    算数就说不清了。

    返回 (各表的行, 城市, 各表看过几行)。重跑一本核过的志书时另有一张
    「待核·补格子」,读回来挂在 `fills` 上 —— 那几行不新增单位,只往总表
    已有的行里填格子(见 `toxlsx.apply_fills`)。

    城市认的是**每一行自己的 City 列**。从前认的是预览表名末尾那一截
    (「厂所名录-北京」),那等于认定「一本志只有一个市」—— 省志一本里十几个
    市,这条就不成立了。市志那一列整列写着同一个市,认出来的还是那一个,
    不受影响。旧本子的待核表没有 City 列,这才退回去照表名认。"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    book_city = book_city_of(wb)

    bundle, seen = {}, {}
    for tag in ("units", "semi", "comp", "names", "fills"):
        name = review_tab(wb, tag)
        if name is None:
            bundle[tag], seen[tag] = [], 0
            continue
        rows = _sheet_rows(wb[name])
        seen[tag] = len(rows)
        kept = []
        for r in rows:
            if not _yes(r.pop("keep", "")):
                continue
            r.pop("evidence", None)
            if tag == "units" and book_city and not r.get("City"):
                r["City"] = book_city
            if tag == "names" and r.get("From") != "":
                r["From"] = str(r["From"])
            kept.append(r)
        if tag == "units":
            kept, seen["merged"] = merge_by_name(kept)
        bundle[tag] = kept

    # 报出来的那一个城市:各行写的都是同一个,才说得上「这本志是哪个市的」。
    # 省志各行不同,就不报 —— 宁可不说,不好说错。
    cities = set(str(r.get("City", "")).strip() for r in bundle["units"])
    cities.discard("")
    city = cities.pop() if len(cities) == 1 else book_city
    return bundle, city, seen
