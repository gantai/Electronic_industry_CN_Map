# -*- coding: utf-8 -*-
"""地方志里的纪年 → 本仓库的 YYYYMMDD 写法。

CN_Electronic_Industry.xlsx 的日期一律写成八位数字,月/日不详处补 0
(`19410000` = 只知 1941 年,`19730400` = 只知 1973 年 4 月)。志书原文
的写法五花八门,这里统一折算:

    1958年3月          -> 19580300
    一九五八年三月十日   -> 19580310
    民国二十六年         -> 19370000
    1958年上半年         -> 19580000  (季度/上下半年一律退到年,原文另存)
    1958.3 / 1958-03    -> 19580300

折算不出来的返回 None —— 宁可空着,也不替史料作主。
"""

import re

CN_DIGIT = {"〇": 0, "○": 0, "零": 0, "一": 1, "壹": 1, "二": 2, "贰": 2, "两": 2,
            "三": 3, "叁": 3, "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6, "陆": 6,
            "七": 7, "柒": 7, "八": 8, "捌": 8, "九": 9, "玖": 9}

# 志书正文里可能出现的年号。只收民国 —— 清末及以前的年号超出本图范围,
# 真遇上了宁可留空待考,不做无据折算。
ERA = {"民国": 1911}


def cn_num(s):
    """把「二十六」「一九五八」「十二」这类中文数字读成整数,读不出返回 None。"""
    s = str(s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    # 逐字式:一九五八 —— 全是个位数字,按位拼
    if all(c in CN_DIGIT for c in s):
        if len(s) == 1:
            return CN_DIGIT[s]
        return int("".join(str(CN_DIGIT[c]) for c in s))
    # 计数式:十、十二、二十六、三十
    if "十" in s:
        a, _, b = s.partition("十")
        tens = CN_DIGIT.get(a, 1) if a else 1
        ones = CN_DIGIT.get(b, 0) if b else 0
        if (a and a not in CN_DIGIT) or (b and b not in CN_DIGIT):
            return None
        return tens * 10 + ones
    return None


def _mk(y, m=0, d=0):
    if y is None or not (1800 <= y <= 2100):
        return None
    m = m or 0
    d = d or 0
    if not (0 <= m <= 12) or not (0 <= d <= 31):
        return None
    if d and not m:          # 有日无月是坏数据,退回到年
        d = 0
    return "%04d%02d%02d" % (y, m, d)


# 「1958年3月10日」/「一九五八年三月十日」/「民国二十六年七月」
_YMD = re.compile(
    r"(?:(民国)\s*)?"
    r"([0-9]{1,4}|[〇○零一壹二贰两三叁四肆五伍六陆七柒八捌九玖十]{1,4})\s*年"
    r"(?:\s*([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*月"
    r"(?:\s*([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*[日号])?)?"
)
# 「1958.3」「1958-03-10」「1958/3」
_DOT = re.compile(r"(1[89][0-9]{2}|20[0-9]{2})\s*[.\-/]\s*([0-9]{1,2})(?:\s*[.\-/]\s*([0-9]{1,2}))?(?![0-9])")
# 已经是八位写法
_RAW8 = re.compile(r"(?<![0-9])((?:1[89]|20)[0-9]{2})([0-1][0-9])([0-3][0-9])(?![0-9])")
# 光秃秃一个年份
_BARE = re.compile(r"(?<![0-9])(1[89][0-9]{2}|20[0-9]{2})(?![0-9])")


def parse(text):
    """从一段文字里取**第一个**日期,返回 YYYYMMDD 字符串;取不到返回 None。"""
    s = str(text or "")
    if not s:
        return None

    cands = []   # (在原文中的位置, 折算结果)

    m = _RAW8.search(s)
    if m:
        got = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if got:
            cands.append((m.start(), got))

    for m in _YMD.finditer(s):
        era, ys, ms, ds = m.groups()
        y = cn_num(ys)
        if y is None:
            continue
        if era:
            y = ERA[era] + y
        elif y < 100:                 # 「58年」这类省写,按二十世纪读
            y = 1900 + y
        got = _mk(y, cn_num(ms) if ms else 0, cn_num(ds) if ds else 0)
        if got:
            cands.append((m.start(), got))
            break

    m = _DOT.search(s)
    if m:
        got = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
        if got:
            cands.append((m.start(), got))

    m = _BARE.search(s)
    if m:
        got = _mk(int(m.group(1)))
        if got:
            cands.append((m.start(), got))

    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], -len(x[1].rstrip("0"))))
    # 同一位置上,取月日更全的那个(八位写法优先于光年份)
    at = cands[0][0]
    same = [c for c in cands if c[0] == at]
    same.sort(key=lambda c: -len(c[1].rstrip("0")))
    return same[0][1]


def year(text):
    """只要年份,取不到返回 None。"""
    got = parse(text)
    return int(got[:4]) if got else None


def fmt(ymd):
    """19580300 -> 1958.03,给人看的写法。"""
    if not ymd:
        return ""
    s = str(ymd).zfill(8)
    y, m, d = s[:4], s[4:6], s[6:8]
    if d != "00":
        return "%s.%s.%s" % (y, m, d)
    if m != "00":
        return "%s.%s" % (y, m)
    return y
