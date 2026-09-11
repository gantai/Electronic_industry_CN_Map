# -*- coding: utf-8 -*-
"""省志:这一家在哪个市。

市志好办 —— 一本书一个市,`--city Beijing` 一给,全书都是它。省志不行:
一本《江苏省志》里有南京、苏州、无锡、常熟……照市志那套办,`city_of` 会把
全省的厂都记成省会那一个市,图上叠成一坨,而且**一声不吭**。

**市名不必事先备好一张表** —— 志书自己就说了有哪几个市。这个模块干两件事:

1. `harvest` 把这一本讲到的市县认出来,只认两处:**章节标题**里的,与
   **厂址字样紧后头**的。「获得北京市科技进步奖」那种不算 —— 那是奖项,
   不是厂在哪儿;而「厂址位于苏州市人民路45号」里的算,哪怕整本只出现一次。
2. `city_for` 给一家定一个市,取信次序 **标题 > 厂址 > 厂名**,
   三处都定不下来就**空着**(由调用方记下省份)。

两种编法都照顾得到,这是量出来的:按市编的稿子,标题里就写着市名,六家全中;
按行业编的稿子标题里一个市名也没有,靠厂址仍中五家 —— 剩下那一家是
「省电子器件研究所」,通篇没说它在哪个市,空着才是实话。

顺带说一句为什么不去弄一份全国市县表:那样每添一个省都要改一次表,还得
时时提防漏一处(见《流程》附《添一个新城市》里那句「少一处那个市的厂就
落到上海人民广场去了」)。让志书自报家门,添省就不必改代码。
"""

import re
from collections import Counter

from . import affil

# 「市」「县」后头跟这些字的,说的不是地方:市场、市区、市政、县级……
KIND = (r"(?:市(?![场区郊政委府局长办属级内外面民容])"
        r"|县(?![级委府政办属内外])"          # 「县」后头**不**排除「城」——
        r"|地区(?![经])|自治州|自治县)")      # 常熟县城关镇是常熟县+城关镇

# 标题里的:整条标题都作数(志书自己的分法)
IN_HEAD = re.compile(r"([一-龥]{2,4}?)" + KIND)

#: 截出来是这些的,不是地名
BAD = re.compile(r"(?:城|都|上|集|超|夜|门|闹|墟|股|菜|早|本|全|该|各|新|旧|省|中小|全国)$")


# 正文里的市名,只认**厂址字样紧后头**那一个。
# 字样可以连着写 ——「厂址位于」是「厂址」加「位于」两个,要一并吃掉,不然
# 截出来的市名成了「位于北京」;中间还可能隔着省名(「江苏省常熟县」),一并跳过。
#
# 字样的写法跟 extract.ADDR_MARK 一处定义,不另抄一份 —— 那边添一种说法,
# 这边跟着就认得。用时才去取,是因为 extract 反过来要 import 这个模块。
_ADDR_CITY = None


def addr_city_re():
    global _ADDR_CITY
    if _ADDR_CITY is None:
        from .extract import ADDR_MARK
        _ADDR_CITY = re.compile(
            r"(?:" + ADDR_MARK.pattern + r")+(?:[一-龥]{2,4}省)?([一-龥]{2,4}?)" + KIND)
    return _ADDR_CITY


def _ok(stem):
    return len(stem) >= 2 and not BAD.search(stem)


def in_head(text):
    """一条标题里点到的市县。「第二节 苏州市」→ ['苏州']"""
    return [m.group(1) for m in IN_HEAD.finditer(str(text or "")) if _ok(m.group(1))]


def in_address(sent):
    """一句话里**厂址字样后头**的市县。奖项、荣誉那类句子进不来。"""
    return [m.group(1) for m in addr_city_re().finditer(str(sent or "")) if _ok(m.group(1))]


#: 名录表里,这几个表头底下写的是「在哪儿」
LOC_HEADS = ("所在地", "地址", "厂址", "所在市", "驻地", "地点")


def in_roster(md_text):
    """名录表的「所在地」一栏 → {单位正名: 市县}。

    省志的名录表往往比专条收得全 —— 北京那一篇,表里 106 家,有专条的才 60 家。
    按行业编的省志尤其要靠它:标题不说市,没专条的那些又没有厂址句子。"""
    out = {}
    for title, head, body in affil.iter_tables(md_text):
        col = next((i for i, h in enumerate(head)
                    if any(w in h for w in LOC_HEADS)), None)
        if col is None:
            continue
        for cells in body:
            if not cells or col >= len(cells):
                continue
            name = re.sub(r"[（(].*?[)）]", "", cells[0]).strip()
            if len(name) < 5:
                continue
            # 「所在地」那一格多半只写市名,没有「厂址」字样,故按标题那套认
            for p in in_head(cells[col]):
                out.setdefault(name, p)
                break
    return out


def harvest(blocks, md_text=""):
    """这一本讲了哪几个市县。

    回 (认下来的一套, 标题里各几次, 厂址里各几次)。
    **不设出现次数的门槛** —— 按行业编的省志里,一个市往往只在一句厂址里
    出现一次;设了门槛,真市名全被滤掉。滤噪音靠的是「只认这两处」。"""
    heads, addrs = Counter(), Counter()
    from .extract import head_name, sentences
    for b in blocks:
        for h in b["heads"]:
            for p in in_head(head_name(h)):
                heads[p] += 1
        for s in sentences(b["text"]):
            for p in in_address(s):
                addrs[p] += 1
    vocab = set(heads) | set(addrs)
    if md_text:
        vocab |= set(in_roster(md_text).values())
    return vocab, heads, addrs


def city_for(unit, head_path, sents, vocab, roster=None):
    """这一家归哪个市。回 (市, 据什么)。定不下来回 ("", "")。

    次序是**标题 > 厂址 > 名录表 > 厂名**:
    * 标题是志书自己的分法,最直截 —— 但转换稿页序会乱(见 affil.py 篇首),
      所以调用方要把「据标题」这件事记进备注,由人回稿子上核;
    * 厂址是明写的;
    * 名录表那一栏同样是明写的,只是离得远些;
    * 厂名冠的市名最弱 ——「江苏电视机厂」冠的是省名不是市名,
      「吴县半导体厂」冠的是县名而它归苏州,都指望不上,故排在最后。
    """
    from .extract import head_name
    for h in (head_path or "").split("·"):
        for p in in_head(head_name(h)):
            if p in vocab:
                return p, "标题「%s」" % h
    for s in sents or ():
        for p in in_address(s):
            if p in vocab:
                return p, "厂址"
    if roster:
        p = roster.get(unit) or roster.get(re.sub(r"[（(].*?[)）]", "", unit))
        if p and p in vocab:
            return p, "名录表"
    for p in sorted(vocab, key=len, reverse=True):
        if unit.startswith(p):
            return p, "厂名"
    return "", ""
