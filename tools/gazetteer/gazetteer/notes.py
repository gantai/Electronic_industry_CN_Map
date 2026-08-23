# -*- coding: utf-8 -*-
"""候选记录 → Obsidian 笔记(一单位一则)。

笔记里放三样东西:能进工作簿的**字段**(YAML frontmatter,Dataview 直接查)、
**原文佐证**(引用块,附页码)、以及指向沿革中提到的其他单位的 **wikilink**。
沿革谱系于是在库里自己长出来 —— 点开一家厂,前身、后身、合并对象都在眼前。

字段与 CN_Electronic_Industry.xlsx 同名同义,核对完就能原样回填。
"""

import os
import re

from . import cndate

BAD_FN = re.compile(r'[\\/:*?"<>|#\^\[\]]')


def safe(name):
    return BAD_FN.sub("_", str(name)).strip() or "无名"


def _yaml(v):
    s = str(v if v is not None else "")
    if s == "":
        return '""'
    if re.search(r'[:\-#\[\]{},&*?|>%@`"\']', s) or s.strip() != s:
        return '"%s"' % s.replace('"', "'")
    return s


def linkify(text, known_names, skip=""):
    """把文中提到的别家单位连成 wikilink,谱系于是在库里自己长出来。
    长名先连,免得「上无十四」把「上无十四厂」拆成两截。"""
    out = str(text or "")
    for other in sorted(known_names, key=len, reverse=True):
        if not other or other == skip or other not in out:
            continue
        if "[[%s]]" % other in out:
            continue
        out = out.replace(other, "[[%s]]" % other, 1)
    return out


def unit_note(row, book, book_note, known_names):
    nm = row.get("Unit") or row.get("name") or ""
    start, end = row.get("Start Date", ""), row.get("End Date", "")
    fm = [
        "---",
        "名称: %s" % _yaml(nm),
        "类型: 单位",
        "行业: %s" % _yaml(row.get("Industry", "")),
        "城市: %s" % _yaml(row.get("City", "")),
        "地址: %s" % _yaml(row.get("Add.", "")),
        "始建: %s" % _yaml(cndate.fmt(start)),
        "终止: %s" % _yaml(cndate.fmt(end)),
        "start_date: %s" % _yaml(start),
        "end_date: %s" % _yaml(end),
        "沿革: %s" % _yaml(row.get("Founder", "")),
        "产品: %s" % _yaml(row.get("Product", "")),
        "出处: %s" % _yaml(row.get("Source", "")),
        "页码: %s" % _yaml(row.get("page", "")),
        "置信: %s" % _yaml(row.get("confidence", "")),
        "校对: 未校",
        "tags: [电子工业, 待校%s]" % (", 已在表内" if row.get("known") else ""),
        "---",
        "",
        "# %s" % nm,
        "",
    ]

    body = []
    if row.get("known"):
        body += ["> [!info] 这家单位已在 `CN_Electronic_Industry.xlsx` 里,"
                 "本则是志书中的对应记载,可用来补字段、核年份。", ""]
    else:
        body += ["> [!warning] 尚未入表的新单位。核实后把 TSV 里 `keep` 改成 `y`,"
                 "再跑 `gaz xlsx` 追加。", ""]

    body += ["## 字段", ""]
    for label, key in [("行业", "Industry"), ("产品", "Product"), ("始建", "Start Date"),
                       ("终止", "End Date"), ("城市", "City"), ("地址", "Add.")]:
        v = row.get(key, "")
        if key in ("Start Date", "End Date"):
            v = "%s（%s）" % (cndate.fmt(v), v) if v else ""
        body.append("- **%s**:%s" % (label, (" " + str(v)) if v else " —"))
    body.append("")

    chain = str(row.get("Founder", "") or "")
    if chain:
        body += ["## 沿革", ""]
        for step in [s for s in re.split(r"\s*->\s*", chain) if s]:
            d = re.match(r"^(\d{4}(?:\d{4})?)", step)
            when = cndate.fmt(d.group(1).ljust(8, "0")) if d else ""
            what = step[d.end():] if d else step
            body.append("- %s%s" % (("**%s** " % when) if when else "",
                                    linkify(what, known_names, skip=nm)))
        body.append("")

    stats = [("职工总数", "staff", "人"), ("技术人员", "tech", "人"),
             ("厂房面积", "plant", "平方米"), ("建筑面积", "floor", "平方米"),
             ("固定资产", "assets", "万元"), ("工业总产值", "output", "万元"),
             ("销售收入", "sales", "万元"), ("实现利润", "profit", "万元")]
    have = [(l, row.get(k), u) for l, k, u in stats if str(row.get(k, "")).strip()]
    if have:
        body += ["## 统计", "", "| 项目 | 数值 | 量纲 |", "| --- | --- | --- |"]
        body += ["| %s | %s | %s |" % (l, v, u) for l, v, u in have]
        body += ["", "> 量纲以志书原文为准,入表前请核对是否与工作簿其余各行一致。", ""]

    if row.get("Remark"):
        # 备注里也常写着别家单位(如「1985.12 并入某厂」这类终局),一并连上
        body += ["## 备注", "", linkify(row["Remark"], known_names, skip=nm), ""]

    if row.get("evidence"):
        body += ["## 原文佐证", ""]
        for piece in str(row["evidence"]).split(" ⏐ "):
            if piece.strip():
                body.append("> %s" % piece.strip())
                body.append(">")
        body.append("")

    src = row.get("Source", "")
    body += ["## 出处", "",
             "- %s" % (("[[%s]] %s" % (book_note, src)) if book_note else src),
             "- 由 `tools/gazetteer` 自动识别、自动抽取,**未经校对**。",
             ""]
    return "\n".join(fm + body)


def index_note(rows, book, book_note):
    by_ind = {}
    for r in rows:
        by_ind.setdefault(r.get("Industry") or "未判定", []).append(r)
    out = ["---", "title: %s · 抽取索引" % book, "type: 索引",
           "tags: [电子工业, 索引]", "---", "",
           "# %s · 单位索引" % book, "",
           "共 %d 家。**均未校对**;`置信` 只是信号多寡,不是可信程度。" % len(rows), ""]
    if book_note:
        out += ["原书全文:[[%s]]" % book_note, ""]
    for ind in sorted(by_ind, key=lambda k: -len(by_ind[k])):
        out += ["## %s（%d）" % (ind, len(by_ind[ind])), "",
                "| 单位 | 始建 | 终止 | 地址 | 置信 | 已在表内 |",
                "| --- | --- | --- | --- | --- | --- |"]
        for r in sorted(by_ind[ind], key=lambda x: str(x.get("Start Date") or "9")):
            out.append("| [[%s]] | %s | %s | %s | %s | %s |" % (
                safe(r.get("Unit") or r.get("name")),
                cndate.fmt(r.get("Start Date", "")), cndate.fmt(r.get("End Date", "")),
                r.get("Add.", "") or "—", r.get("confidence", ""),
                "✓" if r.get("known") else ""))
        out.append("")
    return "\n".join(out)


def write_vault(rows, outdir, book="", book_note="", log=print):
    os.makedirs(outdir, exist_ok=True)
    known_names = {str(r.get("Unit") or r.get("name") or "") for r in rows}
    n = 0
    for r in rows:
        nm = safe(r.get("Unit") or r.get("name"))
        with open(os.path.join(outdir, nm + ".md"), "w", encoding="utf-8") as f:
            f.write(unit_note(r, book, book_note, known_names))
        n += 1
    idx = os.path.join(outdir, "_索引 %s.md" % safe(book or "志书"))
    with open(idx, "w", encoding="utf-8") as f:
        f.write(index_note(rows, book or "志书", book_note))
    log("写出 %d 则单位笔记 + 1 则索引 → %s" % (n, outdir))
    return n
