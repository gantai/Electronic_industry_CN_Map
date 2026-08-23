# -*- coding: utf-8 -*-
"""逐页文本 → 一份带页码锚点的 Markdown。

做四件事,每一件都留痕:

  **一、去书眉书脚。** 志书每页天头地脚印着书名、篇名、页码。跨页比对,凡在
  多页的同一位置反复出现的短行,判为版式而非正文,删去并记账。

  **二、并行。** OCR 按视觉行断句,一句话被拆成好几行。中文没有词间空格,
  按「上一行是否收在句读上、下一行是否另起段」把行接回段落。志书正文多以
  两个全角空格开头,这是最可靠的分段信号。

  **三、认标题。** 第 X 篇 / 章 / 节 / 目、一、、(一) 顺次折成 `#`~`#####`。

  **四、下页码锚点。** 每页正文前插一行 `<!-- p.123 -->`。预览时看不见,
  抽取时据以回注出处,Obsidian 里也搜得到 —— **每一条史料都追得回原页**。

字形订正只做全角转半角一类**不涉判断**的事;要改别的,自己写一张 fixes.tsv
(制表符分隔:错\t对),逐条都会记在 `.fixes.tsv` 里备查,绝不悄悄改字。
"""

import os
import re
from collections import Counter

CJK = r"[一-鿿]"
SENT_END = "。！？；.!?;：:」』】》\"'）)"

# 版式行:页码、书名页眉之类
_PAGENO = re.compile(r"^[\s·\-—_]*[（(]?\s*(?:[0-9]{1,4}|[〇一二三四五六七八九十百]{1,6})\s*[）)]?[\s·\-—_]*$")

# 标题:第一篇 / 第三章 / 第二节 / 第四目
_H_CHAP = re.compile(r"^\s*第\s*([0-9]{1,3}|[〇一二三四五六七八九十百]{1,4})\s*([篇卷章节目])\s*(.*)$")
# 一、二、三、
_H_ENUM = re.compile(r"^\s*([一二三四五六七八九十]{1,3})\s*[、.．]\s*(\S.*)$")
# (一) (二) （三）
_H_PAREN = re.compile(r"^\s*[（(]\s*([一二三四五六七八九十]{1,3})\s*[）)]\s*(\S.*)$")

_LEVEL = {"篇": 1, "卷": 1, "章": 2, "节": 3, "目": 4}

# 只做不涉判断的字形归一。要改别的字,请自备 fixes.tsv。
_SAFE = {}
for _a, _b in zip("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
                  "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _SAFE[_a] = _b
for _a, _b in zip("ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ", "abcdefghijklmnopqrstuvwxyz"):
    _SAFE[_a] = _b
_SAFE.update({"―": "—", "–": "—", "‐": "-", "﹣": "-", "％": "%", "～": "~"})


def load_fixes(path):
    """自备的字形订正表:每行「错<TAB>对」,# 开头是注释。"""
    table = {}
    if not path or not os.path.exists(path):
        return table
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0]:
                table[parts[0]] = parts[1]
    return table


def apply_fixes(text, table, page, ledger):
    for bad, good in table.items():
        if bad in text:
            ledger.append((page, bad, good, text.count(bad)))
            text = text.replace(bad, good)
    return text


def normalize(text, page, ledger):
    out = []
    for ch in text:
        if ch in _SAFE:
            ledger.append((page, ch, _SAFE[ch], 1))
            out.append(_SAFE[ch])
        else:
            out.append(ch)
    s = "".join(out)
    s = s.replace("　", "　")             # 全角空格保留(分段信号)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s


# ---------------------------------------------------------------- 书眉书脚

def running_lines(pages, edge=2, min_share=0.35):
    """跨页比对天头地脚,挑出反复出现的版式行。

    只看每页首尾各 `edge` 行;在 `min_share` 以上的页面出现过、且不像正文
    (短、无句读)的,判为书眉书脚。"""
    top, bot = Counter(), Counter()
    n = 0
    for _, raw in pages:
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        if not lines:
            continue
        n += 1
        for l in lines[:edge]:
            top[l] += 1
        for l in lines[-edge:]:
            bot[l] += 1
    if n < 3:
        return set()
    need = max(2, int(n * min_share))
    out = set()
    for c in (top, bot):
        for line, cnt in c.items():
            if cnt >= need and len(line) <= 30 and not any(p in line for p in "。！？"):
                out.add(line)
    return out


def strip_furniture(raw, furniture):
    """删书眉书脚,再删天头地脚的孤零页码。

    分两趟走:先把判定为版式的行整页删净(书眉未必总在第一行,OCR 会把它
    错排到第二三行),剩下的行里,头尾三行内**只有一个数字**的,是页码。
    空行照留 —— 它是分段的信号,交给 reflow 用。"""
    lines = [l for l in raw.splitlines() if l.strip() not in furniture]
    body = [i for i, l in enumerate(lines) if l.strip()]
    drop = set()
    for i in body[:3] + body[-3:]:
        if _PAGENO.match(lines[i].strip()):
            drop.add(i)
    lines = [l for i, l in enumerate(lines) if i not in drop]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


# ---------------------------------------------------------------- 认标题与并行

def heading(line):
    """返回 (层级, 标题文字);不是标题返回 None。"""
    s = line.strip().lstrip("　 ")
    if not s or len(s) > 40:
        return None
    m = _H_CHAP.match(s)
    if m:
        num, kind, rest = m.groups()
        title = ("第%s%s" % (num, kind)) + (" " + rest.strip() if rest.strip() else "")
        return _LEVEL.get(kind, 3), title
    m = _H_ENUM.match(s)
    if m and len(m.group(2)) <= 30 and m.group(2)[-1] not in "。，、":
        return 4, s
    m = _H_PAREN.match(s)
    if m and len(m.group(2)) <= 30 and m.group(2)[-1] not in "。，、":
        return 5, s
    return None


def reflow(text):
    """把 OCR 的视觉行接回段落。"""
    lines = [l.rstrip() for l in text.splitlines()]
    body = [l for l in lines if l.strip()]
    if not body:
        return []
    widths = sorted(len(l.strip()) for l in body)
    typical = widths[len(widths) // 2]          # 中位行宽 ≈ 版心一行的字数

    out, buf = [], ""

    def flush():
        nonlocal buf
        if buf.strip():
            out.append(("p", buf.strip()))
        buf = ""

    for line in lines:
        s = line.strip()
        if not s:
            flush()
            continue
        h = heading(line)
        if h:
            flush()
            out.append(("h", h))
            continue
        starts_para = line.startswith("　") or line.startswith("    ") or line.startswith("  ")
        if starts_para:
            flush()
        buf += s
        # 收在句读上、或这一行明显没写满,都算一段的末尾
        if s[-1] in SENT_END or len(s) < typical * 0.75:
            flush()
    flush()
    return out


def looks_like_table(raw):
    """数字成列、少有句读的页多半是表格 —— 标出来待人工处置,不硬认。

    志书正文里年份、产量、人数满篇皆是,单看「有没有数字」必然误判,
    所以还要看两件事:一行里的数字是否**成列**(多个数字字段并排),
    以及整页是否**几乎不用句号** —— 表格没有句子。"""
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if len(lines) < 6:
        return False

    def tabular(line):
        nums = re.findall(r"[0-9][0-9.,]*", line)
        cjk = len(re.findall(CJK, line))
        if len(nums) >= 4 and cjk <= len(line) * 0.4:
            return True
        fields = [f for f in re.split(r"\s{2,}|\t", line) if f.strip()]
        return (len(fields) >= 3
                and sum(1 for f in fields if re.fullmatch(r"[0-9.,%~\-]+", f.strip())) >= 2)

    hits = sum(1 for l in lines if tabular(l))
    stops = sum(l.count("。") for l in lines)
    return hits >= max(5, len(lines) * 0.5) and stops <= len(lines) * 0.15


# ---------------------------------------------------------------- 主流程

def build(pages, title, meta=None, fixes=None, keep_furniture=False):
    """pages 是 [(页码, 文本), ...],返回 (markdown 文本, 字形订正流水)。"""
    meta = meta or {}
    fixes = fixes or {}
    ledger = []
    furniture = set() if keep_furniture else running_lines(pages)

    how = Counter(v.get("how", "") for v in (meta.get("pages") or {}).values())
    front = [
        "---",
        "title: %s" % title,
        "type: 地方志",
        "source_file: %s" % (meta.get("source") or ""),
        "pages: %d" % len(pages),
        "page_range: %s" % ("%d-%d" % (pages[0][0], pages[-1][0]) if pages else ""),
        "ocr: %s" % (", ".join("%s×%d" % (k or "?", v) for k, v in how.most_common()) or "未记录"),
        "generated_by: tools/gazetteer",
        "tags: [地方志, 待校]",
        "---",
        "",
        "# %s" % title,
        "",
        "> 本文由扫描件自动识别转成,**未经校对**。每页正文前的 `<!-- p.NNN -->`",
        "> 是原书页码,抽取出来的每一条记录都据此回注出处。",
        "",
    ]

    body = []
    for pno, raw in pages:
        text = normalize(raw, pno, ledger)
        text = apply_fixes(text, fixes, pno, ledger)
        text = strip_furniture(text, furniture)
        body.append("<!-- p.%d -->" % pno)
        if not text.strip():
            body.append("")
            body.append("*(本页无文字)*")
            body.append("")
            continue
        if looks_like_table(text):
            body.append("")
            body.append("<!-- 疑似表格,以下照录识别原文,未作还原 -->")
            body.append("")
            body.append("```")
            body.append(text.strip())
            body.append("```")
            body.append("")
            continue
        body.append("")
        for kind, val in reflow(text):
            if kind == "h":
                lvl, title_text = val
                body.append("#" * min(lvl + 1, 6) + " " + title_text)
            else:
                body.append(val)
            body.append("")

    lines = front + body
    # 压掉连着的空行
    out = []
    for l in lines:
        if l == "" and out and out[-1] == "":
            continue
        out.append(l)
    return "\n".join(out).rstrip() + "\n", ledger


def furniture_report(pages):
    return sorted(running_lines(pages))
