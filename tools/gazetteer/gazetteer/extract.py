# -*- coding: utf-8 -*-
"""Markdown 志书 → 可核对的候选记录。

抽出来的东西对着 CN_Electronic_Industry.xlsx 的四张表:

    units  -> Fact and Comp-Shanghai   厂所名录
    semi   -> Semi-Product             器件投产
    comp   -> Comp-Product             整机研制
    names  -> Name-History             名称沿革

**规矩与本仓库一致:凡推定必标依据,凡入表必经人眼。** 每条记录都带着
`page`(原书页码)、`evidence`(据以立论的那句原文)、`confidence`(信号多寡),
`keep` 一栏留白作 `?` —— 你在 TSV 里改成 `y` 的行,才会写进 xlsx。

## 一句话归谁

志书的体例帮了大忙:厂所各占一节,标题即厂名。所以每句话分三种身份 ——

    专条(owner)  这句话落在某厂的标题底下,讲的就是它,可据以立字段
    点名(named)  不在任何厂的标题底下,但句中点了名,同样可据以立字段
    提及(ref)    这句话讲的是甲厂,只是顺带说到乙厂 —— **不可**据以立乙厂的字段

第三条最要紧。「上海元件十四厂……1985年12月撤销,并入上海无线电十九厂」
一句里,撤销的是元件十四厂;若不分身份,十九厂便平白多了个终止年。
"""

import re
from collections import OrderedDict, defaultdict

from . import cndate

# ---------------------------------------------------------------- 词表

UNIT_TAIL = (r"(?:研究所|研究院|设计院|实验室|试验室|工厂|电子厂|仪器厂|机械厂|无线电厂|"
             r"器材厂|电器厂|电工厂|灯泡厂|制造厂|修配厂|公司|工场|制造所|计算所|大学|学院|"
             r"[0-9]+所|厂)")
# 「厂」「所」后头跟这些字的,是「厂房」「所长」一类的词,不是名字的收尾
TAIL_RE = re.compile(UNIT_TAIL + r"(?![房址长区部内外里方家矿商牌史志属在有以需谓工人员级])")

# 名字里绝不会出现、却常常紧挨在名字前头的字 —— 往左找名字的起点,到此为止
# 数字不入 BOUND —— 军工厂就叫「国营738厂」「四机部15所」,拿数字断名字等于
# 把这类厂名全丢了;年月日已在表里,日期照样断得住
BOUND = (set("、，,。；;：:（）()[]「」『』《》〈〉“”\"'　 \t\r\n")
         | set("与及由为在于将把向从并入该本其此又遂乃旋等是即之年月日归属送的"))
# 「和」不入 BOUND —— 「和平电器厂」这类名字太多,截断的代价比留点噪音大
SOFT_BOUND = set("和")
# 起头像个正经名号的写法,用来在被「和」「与」截断时把全名捞回来
STRONG = re.compile(r"^(?:上海|北京|天津|南京|中国|中央|华东|华北|国营|地方国营|"
                    r"公私合营|私营|合营|人民|第[一二三四五六七八九十百]+(?![个次届批台条种])|沪)")

# 名字前头黏着的日期与动词,逐层剥掉
LEAD_NOISE = re.compile(
    r"^(?:[0-9〇一二三四五六七八九十]{1,4}\s*年)?(?:[0-9一二三四五六七八九十]{1,3}\s*月)?"
    r"(?:[0-9一二三四五六七八九十]{1,3}\s*[日号])?\s*"
    r"(?:由|与|和|同|系|即|在|于|为|将|把|经|向|从|自(?!动)|其|该|本|原|后|又|并|遂|乃|旋|对|了)?\s*"
    r"(?:前身(?:为|是|系)?|原名(?:为)?|原(?:为|系|名)|改名为|改名|更名为|更名|改称为|改称|"
    r"易名为|易名|定名为|定名|并入|划归|划入|归属|隶属|合并|合组|组建|组成|成立|建立|创办|"
    r"创建|筹建|设立|撤销|撤消|接管|接收|投资|开办|接受|承接|接产|接办|引进|"
    r"组织|完成|通过|移交|审查|开设|采用|选用|委托|订购|承担|支援|会同)?(?:了|过)?\s*")
# 名字当中还夹着动词的,多半是两截连在一起:「四机部6所承接了大庆石油化工总厂」。
# 从最后一个动词后头切开 —— 切出来像个名字就用它,不像才整条丢掉。这比一见
# 动词就丢强:承接的那一头正是用机器的人家,是要留的。
# 「开发」「生产」不在其列 ——「北京华海新技术开发公司」是正经名号,切不得。
MID_VERB = re.compile(r"^.*(?:承接|承担|接受|引进|完成|通过|移交|审查|召开|开设|"
                      r"组织|交付|交给|销往|采用|订购|委托)[了过]?")
# 剥完之后还带这些字样的,是句子不是名字
NAME_JUNK = re.compile(r"[年月日,,。;;::、?!!]|移交|承接|接受|引进|完成|通过|审查|召开|"
                       r"开设|组织|承担|试制|前身|原名|改名|更名|改称|并入|划归|合并|"
                       r"组建|撤销|成立|建立|创办|等|其中|以及")
UNIT_STOP = re.compile(r"^(?:该|本|全|各|我|上述|这|那|同|其|此|以上|下属|所属|有关|不少|许多|"
                       r"部分|两|[三四五六七八九十](?!机部)|几|一批|若干|校|主要|全国)")
UNIT_BAD = {"工厂", "该厂", "本厂", "全厂", "分厂", "工场", "公司", "研究所", "实验室",
            "总厂", "母厂", "老厂", "新厂", "小厂", "大厂", "电子厂", "无线电厂", "各厂",
            "兄弟厂", "协作厂", "本所", "该所", "该公司", "本公司", "试验室", "上级主管部门",
            "电子公司", "计算机厂", "主要生产厂", "生产厂"}

BIRTH = r"(?:建立|成立|创建|创办|创设|筹建|始建|开办|设立|建成|组建|开工|投产|定名|诞生)"
DEATH = r"(?:撤销|撤消|撤并|停办|关闭|解散|停产|终止|歇业|倒闭|结束)"
RENAME = r"(?:改名为|更名为|改称为|改名|更名|改称|易名为|易名|定名为|定名)"
TRANSFER = r"(?:划归|划入|划出|归属|隶属|移交|下放|上收)"
MERGE = r"(?:并入|合并|归并|组建|合组|抽调|析出|分出|分立)"
MADE = r"(?:试制|研制|研发|生产|投产|制成|定型|鉴定|问世|开发|出产)"

# Industry 一列的四个取值,见 src/consts.js
INDUSTRY_VOTES = [
    ("电子计算机", r"电子计算机|计算机|电脑|微机|运算器|控制机|数字机"),
    ("半导体", r"半导体|晶体管|二极管|三极管|集成电路|晶闸管|可控硅|硅片|外延|管芯|器件"),
    ("外围设备", r"外围设备|外部设备|打印机|磁盘|磁带机|终端|显示器|绘图机|穿孔|读带机|键盘"),
    ("研究所", r"研究所|研究院|设计院"),
]

# 1990 年统计块的八项,key 与 src/consts.js 的 STAT_FIELDS 对齐
STAT_PATTERNS = [
    ("staff",  r"(?:职工总数|职工人数|全厂职工|全所职工|在册职工|职工)\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(人|名)"),
    ("tech",   r"(?:工程技术人员|技术人员|科技人员)\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(人|名)"),
    ("plant",  r"(?:厂房面积|生产面积)\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(平方米|万平方米)"),
    ("floor",  r"(?:建筑面积|占地面积)\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(平方米|万平方米)"),
    ("assets", r"(?:固定资产)(?:原值|净值)?\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(万元|元|亿元)"),
    ("output", r"(?:工业总产值|总产值|产值)\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(万元|元|亿元)"),
    ("sales",  r"(?:销售收入|销售额)\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(万元|元|亿元)"),
    ("profit", r"(?:实现利润|利润总额|利税|利润)\D{0,6}?([0-9]+(?:\.[0-9]+)?)\s*(万元|元|亿元)"),
]

# 地址照原表体例,只取路名门牌(如「虹桥路951弄2号」),不带区名
ADDR_MARK = re.compile(r"(?:厂址|所址|地址|位于|坐落|设|迁至|迁往|迁入)\s*(?:在|于)?\s*")
# 路名里不会有「区」「址」「在」这些字,逐字排除,免得把「厂址在闸北区中华新路」整段抓走
ADDR_RE = re.compile(r"((?:(?![区县址在于设迁坐落位])[一-鿿A-Za-z0-9]){1,10}"
                     r"(?:路|街|大道|弄|巷|里|村|浜|桥|坊)(?:[0-9]{1,4}弄)?(?:[0-9]{1,4}号)?)")
# 区名单独记一栏 —— 地址照原表体例不带区,但 src/geocode.js 的落点表要用
DISTRICT_RE = re.compile(r"((?:(?![址在于设迁坐落位厂所地市省的和与至往到入自从由近])[一-鿿]){2,3}?)(?:区|县)"
                         r"(?![^,,。;;]{0,4}(?:政府|工业局|人民政府))")

# 产品:一律从「试制/研制/生产」之后取,免得把动词连着抓进名字
PROD_TAIL = (r"(?:计算机|电子计算机|电脑|微机|控制机|运算器|"
             r"晶体管|二极管|三极管|集成电路|电路|整流器|电池|器件|管|机)")
PROD_RE = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9\-/]{0,11}(?:型|号)?)?[一-鿿A-Za-z0-9]{0,14}"
                     + PROD_TAIL + r"$")
PROD_LEAD = re.compile(r"^(?:成功|出|了|过|有|的|各种|多种|大量|首批|第一批|我国|国内|上海)+")

PERSON_RE = re.compile(r"(?:由|经)?([一-鿿、·]{2,24}?)(?:等)?(?:主持|负责人|负责|领导|任组长|"
                       r"带队|主管|牵头)")
ROLE_STRIP = re.compile(r"^(?:由|经|该厂|该所|本厂|本所|工程技术人员|总工程师|副总工程师|"
                        r"高级工程师|工程师|技术员|研究员|副?厂长|副?所长|副?主任|副?院长|"
                        r"组长|科长|处长|同志|技术|工人)+")

WORD_RE = re.compile(r"字长\D{0,4}?([0-9]{1,3})\s*位")
MEM_RE = re.compile(r"(?:内存|存储容量|主存|存储器容量)\D{0,4}?([0-9]+)\s*(K|KB|B)?")
SPEED_RE = re.compile(r"(?:运算)?速度\D{0,6}?(?:每秒\D{0,4})?([0-9]+(?:\.[0-9]+)?)\s*(亿|万|千)?\s*次")
COLLAB = re.compile(r"(?:协作|合作|协同|联合|共同|配合)")

# 用机的人家,不是造机的人家。「承接唐山陡河发电总厂」「交付唐山基地应用」
# 「完成了新疆水泥厂的过程控制改造」—— 这些单位是机器的去处,不是研制方。
# 先前一律记进 Factory,站点便据以画出一条「协作」连线:水泥厂成了计算机的
# 共同研制单位。分不清的仍算协作 —— 宁可少认一个用户,不可把用户说成研制方。
USER_LEAD = re.compile(r"(?:承接|承担|交付|交给|移交|供|销往|用于|装备|应用于|"
                       r"为(?!主)|给)[了过]?\s*$")
USER_TAIL = re.compile(r"^\s*的?(?:过程控制|生产控制|调度|管理|监测|监控|自动化)")

SENT_SPLIT = re.compile(r"(?<=[。！？；])")
PAGE_MARK = re.compile(r"<!--\s*p\.(\d+)\s*-->")
HEAD_MARK = re.compile(r"^(#{1,6})\s+(.*)$")

# 别处转来的稿子常把 篇/章/节/一、 一律压成 `##`,井号就数不出层级了。
# 志书的层级本来写在标题文字里,认字比数井号可靠。
HEAD_RANK = [(re.compile(r"^第[〇零一二三四五六七八九十百]+篇"), 1),
             (re.compile(r"^第[〇零一二三四五六七八九十百]+章"), 2),
             (re.compile(r"^第[〇零一二三四五六七八九十百]+节"), 3),
             (re.compile(r"^[一二三四五六七八九十]+[、.．]"), 4),
             (re.compile(r"^[（(][一二三四五六七八九十]+[)）]"), 5)]


def head_rank(text, fallback):
    """这条标题该算第几层:先认「第三章」「一、」的字面,认不出才回去数井号。"""
    for rx, lvl in HEAD_RANK:
        if rx.match(text):
            return lvl
    return fallback



# ---------------------------------------------------------------- 读 Markdown

def read_blocks(md_text):
    """拆成 [{page, heads, text}]。标题按**层级**入栈 —— 同级标题要顶掉前一个,
    不然「二、乙厂」下面的话会连着「一、甲厂」一起算,张冠李戴。"""
    blocks, stack, page = [], [None] * 7, None
    for line in md_text.splitlines():
        m = PAGE_MARK.search(line)
        if m:
            page = int(m.group(1))
            continue
        m = HEAD_MARK.match(line)
        if m:
            txt = m.group(2).strip()
            lvl = head_rank(txt, len(m.group(1)))
            stack[lvl] = txt
            for j in range(lvl + 1, 7):
                stack[j] = None
            continue
        s = line.strip()
        if not s or s.startswith("<!--") or s.startswith(">") or s.startswith("```"):
            continue
        blocks.append({"page": page, "heads": [h for h in stack[1:] if h], "text": s})
    return blocks


def sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]


# ---------------------------------------------------------------- 找单位名

def clean_unit_name(raw):
    """把「1966年3月改名为上海无线电十九厂」剥回「上海无线电十九厂」。
    剥不干净(还带年月、动词)的一律弃掉 —— 真名字在别处总会再出现一次。"""
    s = str(raw or "").strip()
    for _ in range(4):
        t = LEAD_NOISE.sub("", s, count=1)
        if t == s:
            break
        s = t
    s = s.strip("　 ·、,,")
    m = MID_VERB.search(s)
    if m:
        s = s[m.end():].strip("　 ·、,,")
    if not s or len(s) < 4 or len(s) > 20:
        return ""
    if NAME_JUNK.search(s) or UNIT_STOP.match(s) or s in UNIT_BAD:
        return ""
    if not re.search(UNIT_TAIL + r"$", s):
        return ""
    m = re.match(r"^[0-9]+所(.+)$", s)
    if m and len(m.group(1)) >= 4 and re.search(UNIT_TAIL + r"$", m.group(1)):
        s = m.group(1)
    return s


TAIL_END = re.compile(UNIT_TAIL + r"$")


def _merges_two(name):
    """「华北计算技术研究所和哈尔滨军事工程学院」是两家,不是一个名字。

    判据:「和」左边已经收在「研究所」这类字样上,那这个「和」就是连词。
    「和平电器厂」的「和」在开头,左边什么也没有,照收不误。"""
    return any(ch in SOFT_BOUND and TAIL_END.search(name[:i])
               for i, ch in enumerate(name))


def _walk_left(text, end, limit=18, bound=BOUND):
    i = end
    while i > 0 and (end - i) < limit and text[i - 1] not in bound:
        i -= 1
    return i


def unit_names(text):
    """先找「厂」「研究所」一类收尾字样,再往左走到句读或连接词为止。

    从左往右扫是行不通的:「该机与上海无线电十三厂协作生产」里,正则从句首
    起手就会把「该机与」一并吞下。倒着走才拿得准名字的起点。"""
    out = []
    for m in TAIL_RE.finditer(text):
        end = m.end()
        cand = clean_unit_name(text[_walk_left(text, end, bound=BOUND | SOFT_BOUND):end])
        if not cand or not STRONG.match(cand):
            # 也许是被「和」「与」截短了,放宽一格再找一个像样的全名
            wide = text[_walk_left(text, end, limit=22, bound=BOUND):end]
            # wide 从左往右扫,第一个带字头的就是最长的正名。这里不比长短 ——
            # cand 本来就没认出字头,再长也是「生产厂家有…」这种连着谓语的脏名字
            for k in range(len(wide)):
                alt = clean_unit_name(wide[k:])
                if alt and STRONG.match(alt) and not _merges_two(alt):
                    cand = alt
                    break
        if cand and cand not in out:
            out.append(cand)
    return out


def known_index(known):
    """已在 xlsx / geocode.js 里的名字与简称 → 规范名,用来认出「旧识」。"""
    idx = {}
    for canon, aliases in (known or {}).items():
        for a in set([canon] + list(aliases or [])):
            if a and len(a) >= 3:
                idx[a] = canon
    return idx


def known_in(text, kidx):
    """认简称:「上无十三」这类不合 UNIT_RE 体例的写法,靠对照表认。"""
    out = []
    for alias in sorted(kidx, key=len, reverse=True):
        if alias in text and kidx[alias] not in out:
            out.append(kidx[alias])
    return out


# ---------------------------------------------------------------- 各字段

def _stat_value(num, unit):
    """量纲一律以原表为准:面积作平方米,金额作万元,人数作人。"""
    v = float(num)
    if unit == "万平方米":
        return v * 10000
    if unit == "元":
        return round(v / 10000.0, 4)
    if unit == "亿元":
        return v * 10000
    return v


def pick_industry(name, text):
    for label, pat in INDUSTRY_VOTES:
        if re.search(pat, name):
            return label, "据单位名"
    scores = [(len(re.findall(pat, text)), label) for label, pat in INDUSTRY_VOTES[:3]]
    scores = [s for s in scores if s[0]]
    if scores:
        scores.sort(reverse=True)
        return scores[0][1], "据正文用词"
    return "", ""


def find_district(sents):
    for s in sents:
        m = DISTRICT_RE.search(s)
        if m:
            return re.sub(r"新$", "", m.group(1))
    return ""


def find_address(sents):
    for want_mark in (True, False):
        for s in sents:
            hay = s
            if want_mark:
                m = ADDR_MARK.search(s)
                if not m:
                    continue
                hay = s[m.end():]
            m = ADDR_RE.search(hay)
            if m and (not want_mark or "号" in m.group(1) or "弄" in m.group(1)):
                return m.group(1), s
    return "", ""


def find_products(sents):
    """一律从「试制/研制/生产」之后取,再按顿号拆开并列的几样。"""
    out = []
    for s in sents:
        for m in re.finditer(MADE, s):
            tail = re.split(r"[，,。；;：:（(]", s[m.end():])[0]
            for piece in tail.split("、"):
                p = PROD_LEAD.sub("", piece.strip()).strip("的等")
                if 3 <= len(p) <= 24 and PROD_RE.match(p) and p not in out:
                    out.append(p)
    return out


def find_persons(text):
    names = []
    for run in PERSON_RE.findall(text):
        for piece in re.split(r"[、·]", run):
            p = ROLE_STRIP.sub("", piece.strip())
            if 2 <= len(p) <= 4 and p not in names:
                names.append(p)
    return names


ANAPHOR = re.compile(r"^(?:该机|该型|该机型|此机|该产品|该计算机|该系统|同机|它)")


def user_units(scope, names):
    """这句里哪些单位是拿机器去用的。

    靠名字前后那几个字分辨:前头是「承接」「交付」「为…」,或后头跟着
    「的过程控制系统」,就是用户。"""
    out = []
    for nm in names:
        i = scope.find(nm)
        if i < 0:
            continue
        if USER_LEAD.search(scope[max(0, i - 6):i]) or USER_TAIL.match(scope[i + len(nm):]):
            out.append(nm)
    return out


def collab_scope(para, sent):
    """协作单位只在这一句里找;下一句若以「该机」一类指代词起头,才算它的续文。

    「……由某某主持。该机与甲厂协作生产。1980年研制成功乙机……」—— 协作说的是
    前一台机器,不是后一台。段落整个儿拿来找,就会张冠李戴。"""
    parts = sentences(para)
    try:
        i = parts.index(sent)
    except ValueError:
        return sent
    scope = parts[i]
    if i + 1 < len(parts) and ANAPHOR.match(parts[i + 1]):
        scope += parts[i + 1]
    return scope


def renames_this(sent, at, unit, owner=False):
    """这句话里的「改名为」,说的是不是它。

    一句话常同时点到好几家:「北京控制机厂为兰州炼油厂研制过程控制系统,
    同年改名为北京自动化设备厂」—— 改名说的是控制机厂,炼油厂不过是顺带
    提到的用户。可按归户这句话算在两家名下,于是两家各记一笔曾用名,炼油厂
    平白多了个曾用名「北京自动化设备厂」,而它压根没改过名。

    志书行文,一句话的主语在最前头,后头那些是宾语、是用户、是协作方。所以
    认第一家,不认最后一家 —— 「为兰州炼油厂」正夹在主语与动词之间。
    有专条的单位另说:那一节整节都在讲它,改名自然是它的事。
    前头一家也没点到(「该厂改名为…」),那也是它,照收。"""
    if owner:
        return True
    others = unit_names(sent[:at])
    return not others or others[0] == unit


def chain_from(sents, start=None, unit="", owner=False):
    """把「前身」「改名」「划归」串成本仓库 Founder 列的写法:
       `华通电器厂->19660300改名上海无线电十九厂->19700000划归第四机械工业部`。"""
    steps = []
    for s in sents:
        if not re.search(r"前身|原名|原为|原系|系由|改组|" + RENAME + "|" + TRANSFER + "|" + MERGE, s):
            continue
        date = cndate.parse(s)
        # 动词照原文录 ——「由某厂某车间划出组建」录成「划出组建」,不可一律写作
        # 「合并」:站点据措辞分辨分立与合并(见 src/xlsxio.js 的 founderEventType),
        # 改了词就改了事件的性质。
        m = re.search(r"由\s*([一-鿿A-Za-z0-9、和与同]{4,44}?)\s*(合并|合组|组建|组成)", s)
        if m and re.search(UNIT_TAIL, m.group(1)):
            steps.append((date, m.group(1) + m.group(2), "合并", s))
            continue
        m = re.search(r"(?:前身(?:为|是|系)?|原名(?:为)?|原(?:为|系))\s*"
                      r"([一-鿿A-Za-z0-9]{4,20}" + UNIT_TAIL + r"|[一-鿿]{4,20}(?:室|部|组|站|馆))", s)
        if m:
            if unit and not renames_this(s, m.start(), unit, owner):
                continue
            steps.append((date, m.group(1), "前身", s))
            continue
        m = re.search(RENAME + r"\s*([一-鿿A-Za-z0-9]{4,24})", s)
        if m:
            if unit and not renames_this(s, m.start(), unit, owner):
                continue
            steps.append((date, "改名" + m.group(1).rstrip("。,、,"), "更名", s))
            continue
        m = re.search(r"(" + TRANSFER + r")\s*([一-鿿A-Za-z0-9]{2,20})", s)
        if m:
            steps.append((date, m.group(1) + m.group(2).rstrip("。,、,领导管理"), "划归", s))
            continue
        m = re.search(r"(?:与|同|和)\s*([一-鿿A-Za-z0-9]{4,20}" + UNIT_TAIL + r")\s*(合并|合组)", s)
        if m:
            steps.append((date, m.group(1) + m.group(2), "合并", s))
            continue
        m = re.search(r"(" + MERGE + r")\s*([一-鿿A-Za-z0-9]{4,20}" + UNIT_TAIL + r")", s)
        if m:
            steps.append((date, m.group(1) + m.group(2), "合并", s))
    dated = sorted([x for x in steps if x[0]], key=lambda x: x[0])
    ordered = [x for x in steps if not x[0]] + dated
    seen, parts, evid, terminal = set(), [], [], []
    for date, body, kind, s in ordered:
        if (date, body) in seen:
            continue
        seen.add((date, body))
        # 「1985年撤销,并入某厂」讲的是这家单位的终局,不是它的来历。
        # 写进 Founder,站点会把它当成前身、连出一条方向相反的沿革线
        # (见 src/xlsxio.js 的 deriveEvents),故另存到备注里。
        if kind == "合并" and body.startswith("并入") and re.search(DEATH, s):
            terminal.append((date, body, s))
            continue
        # 前身那一步的日期就是始建年,与 Start Date 重复,依原表体例省去
        show = "" if (date and date == start and kind in ("前身", "合并")) else (date or "")
        parts.append(show + body)
        evid.append(s)
    return "->".join(parts), evid, ordered, terminal


def name_history(ordered, unit, page, head, src):
    """沿革里凡「改名为 X」的一步,单独登记成 Name-History 的一行。
       与从 Founder 列推定不同,这里的出处是志书原文,可以直接写页码。"""
    rows = []
    for date, body, kind, s in ordered:
        if kind == "更名" and date:
            rows.append(dict(Unit=unit, Name=body.replace("改名", "", 1).strip(), From=date,
                             Remark=s[:120], Source=src(page, head), page=page,
                             evidence=s, confidence=0.7, keep="?"))
        elif kind == "前身" and date:
            rows.append(dict(Unit=unit, Name=body, From=date,
                             Remark="始建时名称。" + s[:100], Source=src(page, head),
                             page=page, evidence=s, confidence=0.6, keep="?"))
    return rows


# ---------------------------------------------------------------- 主抽取

def make_source(book, page, head=""):
    """出处:有页码就写页码,没有就退到篇章节。

    别处转来的 Markdown 往往不留页码。此时「北京工业志·电子志·第三章 半导体器件」
    仍是查得回去的出处 —— 总强过一个 `p.0`。"""
    if page:
        return ("%s·p.%d" % (book, page)) if book else ("p.%d" % page)
    head = re.sub(r"^#+\s*", "", str(head or "")).strip()
    if head:
        return ("%s·%s" % (book, head)) if book else head
    return book or ""


def extract(md_text, book="", known=None, stats_year=1990, city="Shanghai",
            min_mentions=2, auto_keep=None):
    blocks = read_blocks(md_text)
    kidx = known_index(known)

    def src(page, head=""):
        return make_source(book, page, head)

    # 一、归户:每句话记下页码、所在段落、以及它对这个单位是什么身份
    dossier = defaultdict(list)
    for b in blocks:
        owners = []
        for h in b["heads"]:
            for nm in unit_names(h) + known_in(h, kidx):
                nm = kidx.get(nm, nm)
                if nm not in owners:
                    owners.append(nm)
        for s in sentences(b["text"]):
            named = [kidx.get(n, n) for n in unit_names(s) + known_in(s, kidx)]
            for nm in dict.fromkeys(named + owners):
                if nm in owners:
                    role = "owner"
                elif owners:
                    role = "ref"          # 这段讲的是别人,只是顺带提到它
                else:
                    role = "named"
                dossier[nm].append({"page": b["page"], "sent": s, "para": b["text"],
                                    "role": role, "head": "·".join(b["heads"])})

    units, semi, comp, names = [], [], [], []

    for nm, hits in dossier.items():
        roles = [h["role"] for h in hits]
        has_entry = "owner" in roles
        if not has_entry and len(hits) < min_mentions and nm not in (known or {}):
            continue

        facts = [h for h in hits if h["role"] in ("owner", "named")]
        sents = [h["sent"] for h in facts]
        text = "".join(sents)
        pages = sorted({h["page"] for h in hits if h["page"]})
        page0 = (sorted({h["page"] for h in facts if h["page"]}) or pages or [0])[0]
        head0 = next((h["head"] for h in (facts or hits) if h.get("head")), "")
        ev = OrderedDict()
        signals = 0

        # —— 只在专条 / 点名的句子里立字段;仅被提及的单位不立,只留线索
        start = end = ""
        for s in sents:
            if not start and re.search(BIRTH, s):
                d = cndate.parse(s)
                if d:
                    start, ev["Start Date"] = d, s
            if not end and re.search(DEATH, s):
                d = cndate.parse(s)
                if d:
                    end, ev["End Date"] = d, s
        signals += bool(start) + bool(end)

        industry, ibasis = pick_industry(nm, text)
        signals += bool(industry)

        addr, addr_ev = find_address(sents)
        if addr:
            ev["Add."] = addr_ev
            signals += 1

        founder, fev, ordered, terminal = chain_from(sents, start=start, unit=nm, owner=has_entry)
        if founder:
            ev["Founder"] = fev[0] if fev else ""
            signals += 1
        names.extend(name_history(ordered, nm, page0, head0, src))

        stats, offyear = {}, []
        for key, pat in STAT_PATTERNS:
            for s in sents:
                m = re.search(pat, s)
                if not m:
                    continue
                y = cndate.year(s)
                if y and stats_year and y != stats_year:
                    offyear.append("%s=%s(%d年)" % (key, m.group(1), y))
                    break
                stats[key] = _stat_value(m.group(1), m.group(2))
                ev[key] = s
                break
        signals += min(len(stats), 3)

        prods = find_products(sents)
        signals += bool(prods)

        conf = min(1.0, signals / 6.0) if has_entry or facts else 0.1
        remark = []

        for date, body, _s in terminal:
            remark.append((cndate.fmt(date) + " " if date else "") + body)
        if not has_entry and not facts:
            remark.append("志中未见专条,仅由他条提及")
        elif not has_entry:
            remark.append("未见专条,据行文点名")
        if ibasis:
            remark.append("行业%s" % ibasis)
        if offyear:
            remark.append("非%d年数字:%s" % (stats_year, "；".join(offyear[:4])))
        if len(pages) > 1:
            remark.append("见 p.%d–%d" % (pages[0], pages[-1]))

        row = OrderedDict()
        row["keep"] = "y" if (auto_keep and conf >= auto_keep) else "?"
        row["confidence"] = round(conf, 2)
        row["role"] = "专条" if has_entry else ("点名" if facts else "提及")
        row["page"] = page0
        row["Unit"] = nm
        row["Industry"] = industry
        row["Product"] = "、".join(prods[:4])
        row["Start Date"] = start
        row["End Date"] = end
        row["Founder"] = founder
        row["City"] = city
        row["Add."] = addr
        row["district"] = find_district([addr_ev] if addr_ev else sents)
        for key, _ in STAT_PATTERNS:
            row[key] = stats.get(key, "")
        row["Remark"] = "；".join(remark)
        row["Source"] = src(page0, head0)
        row["known"] = "已在表内" if nm in (known or {}) else ""
        pick = list(dict.fromkeys(ev.values())) or [h["sent"] for h in hits[:2]]
        row["evidence"] = " ⏐ ".join(pick[:3])[:400]
        units.append(row)

        # —— 产品记录:同样只认专条 / 点名的句子
        for h in facts:
            s = h["sent"]
            if not re.search(MADE, s):
                continue
            date = cndate.parse(s)
            persons = "、".join(find_persons(s))[:40]
            for p in find_products([s]):
                is_comp = bool(re.search(r"计算机|电脑|微机|控制机|运算器", p))
                base = OrderedDict(keep="?", confidence=round(0.4 + 0.3 * bool(date), 2),
                                   page=h["page"])
                base["Product"] = p
                if is_comp:
                    w, mem, sp = WORD_RE.search(s), MEM_RE.search(s), SPEED_RE.search(s)
                    mult = {"亿": 100000000, "万": 10000, "千": 1000, None: 1}
                    # 同一段里点到的别家单位,多半是协作研制 —— 记进 Factory,
                    # 站点据以推定「协作」连线(见 src/xlsxio.js 的 deriveEvents)
                    scope = collab_scope(h["para"], s)
                    others = [x for x in (unit_names(scope) + known_in(scope, kidx))
                              if kidx.get(x, x) != nm]
                    others = list(dict.fromkeys(kidx.get(x, x) for x in others))
                    users = user_units(scope, others)
                    others = [x for x in others if x not in users]
                    is_inst = bool(re.search(r"研究所|研究院|大学|学院|设计院", nm))
                    base["字长"] = w.group(1) if w else ""
                    base["内存"] = (mem.group(1) + (mem.group(2) or "")) if mem else ""
                    base["Speed（次秒）"] = (str(int(float(sp.group(1)) * mult[sp.group(2)]))
                                          if sp else "")
                    base["Research Insti"] = nm if is_inst else "、".join(
                        x for x in others if re.search(r"研究所|研究院|大学|学院", x))
                    base["Factory"] = "、".join(
                        ([] if is_inst else [nm])
                        + [x for x in others if not re.search(r"研究所|研究院|大学|学院", x)])
                    base["用户"] = "、".join(users)
                    base["Time"] = date or ""
                    base["Personnel"] = persons
                    base["Remark"] = (("协作:" + "、".join(others) + "。")
                                      if others and COLLAB.search(scope) else "") \
                        + src(h["page"], h.get("head"))
                    base["evidence"] = h["para"][:300]
                    comp.append(base)
                else:
                    base["Factory"] = nm
                    base["Time"] = date or ""
                    base["Personnel"] = persons
                    base["Remark"] = src(h["page"], h.get("head"))
                    base["evidence"] = s[:300]
                    semi.append(base)

    # —— 无主的产品。志书写机器,不一定顺带写谁造的:「104机的仿制与103机同时
    # 进行,共有机柜32个」——整句没有一个单位名,上头那一轮按单位归户,就整条
    # 漏掉了。产品名录该有它,研制单位空着就是空着,不硬派给谁。
    have = {r["Product"] for r in semi} | {r["Product"] for r in comp}
    for b in blocks:
        for s in sentences(b["text"]):
            if not re.search(MADE, s):
                continue
            date = cndate.parse(s)
            for p in find_products([s]):
                if p in have:
                    continue
                have.add(p)
                base = OrderedDict(keep="?", confidence=0.3, page=b["page"])
                base["Product"] = p
                head = "·".join(b["heads"])
                if re.search(r"计算机|电脑|微机|控制机|运算器", p):
                    w, mem, sp = WORD_RE.search(s), MEM_RE.search(s), SPEED_RE.search(s)
                    mult = {"亿": 100000000, "万": 10000, "千": 1000, None: 1}
                    base["字长"] = w.group(1) if w else ""
                    base["内存"] = (mem.group(1) + (mem.group(2) or "")) if mem else ""
                    base["Speed（次秒）"] = (str(int(float(sp.group(1)) * mult[sp.group(2)]))
                                          if sp else "")
                    base["Research Insti"] = ""
                    base["Factory"] = ""
                    base["用户"] = ""
                    base["Time"] = date or ""
                    base["Personnel"] = "、".join(find_persons(s))[:40]
                    base["Remark"] = "研制单位未详。" + src(b["page"], head)
                    base["evidence"] = s[:300]
                    comp.append(base)
                else:
                    base["Factory"] = ""
                    base["Time"] = date or ""
                    base["Personnel"] = "、".join(find_persons(s))[:40]
                    base["Remark"] = "生产单位未详。" + src(b["page"], head)
                    base["evidence"] = s[:300]
                    semi.append(base)

    units.sort(key=lambda r: (r["role"] != "专条", -r["confidence"], r["page"]))
    return {
        "units": units,
        "semi": drop_undated(dedupe(semi, ("Product", "Factory", "Time")),
                             ("Product", "Factory")),  # 无主的 Factory 为空,自成一组
        "comp": dedupe(comp, ("Product", "Time")),
        "names": dedupe(names, ("Unit", "Name", "From")),
    }


def drop_undated(rows, keys):
    """同一厂同一产品,既有写明年份的一条、又有没年份的一条,只留前者。"""
    dated = {tuple(str(r.get(k, "")) for k in keys) for r in rows if r.get("Time")}
    return [r for r in rows if r.get("Time") or tuple(str(r.get(k, "")) for k in keys) not in dated]


def dedupe(rows, keys):
    seen, out = set(), []
    for r in rows:
        k = tuple(str(r.get(x, "")) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out
