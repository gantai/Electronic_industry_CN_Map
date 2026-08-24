# -*- coding: utf-8 -*-
"""在 Obsidian 库里改地图。

`gaz notes` 写出来的笔记是**读**的:抽完看一眼,改动仍得回工作簿里做。
这一对 push / pull 把它变成**能改**的 ——

    gaz push   工作簿 → 库    全部厂所各写一则笔记,字段在 frontmatter 里
    gaz pull   库 → 工作簿    把改过的字段写回原行,写前先列清单

于是校订这件事就在库里做:一边是志书原文(`gaz md` 转出来的那份),
一边是这家厂的字段,两下对着看,改完 `gaz pull` 一推,地图就跟着变。

## 三条不肯让步的地方

**一、你写的字,push 不动。** 笔记里 `<!-- gaz:managed -->` 那一段是机器管的,
每次 push 重写;这段之外你自己写的札记、疑问、引文,一个字都不碰。

**二、改了还没推,push 不覆盖。** 每则笔记记着上次 push 时的指纹;对不上就
说明你在库里改过而没 pull,此时 push 会跳过它并出声,免得辛苦改的东西被
工作簿的旧值冲掉。

**三、推定的坐标不冒充数据。** `src/geocode.js` 里的人工近似值只在笔记里
显示作参考(`推定坐标`),**不写进** `纬度` / `经度` 两栏;你自己填的才写回
工作簿的 Lat / Lng 列。原表里的值优先级本就高于 geocode.js(见 src/xlsxio.js),
所以填了就作数 —— 也正因如此,推定值决不能不声不响地混进去。
"""

import hashlib
import os
import re
from collections import OrderedDict
from datetime import datetime

from . import cndate, toxlsx

MANAGED_START = "<!-- gaz:managed:start 以下由 gaz push 重写,勿手改;要改请改上面的 frontmatter -->"
MANAGED_END = "<!-- gaz:managed:end 以下随你写,gaz push 不动 -->"

# frontmatter 的键 ←→ 工作簿的列。键用中文,Dataview 里查着顺手。
FIELDS = [
    ("行业", "Industry"),
    ("产品", "Product"),
    ("始建", "Start Date"),
    ("终止", "End Date"),
    ("沿革", "Founder"),
    ("城市", "City"),
    ("地址", "Add."),
    ("职工总数", "职工总数"), ("技术人员", "技术人员"),
    ("厂房面积", "厂房面积"), ("建筑面积", "建筑面积"),
    ("固定资产", "固定资产"), ("工业总产值", "工业总产值"),
    ("销售收入", "销售收入"), ("实现利润", "实现利润"),
    ("备注", "Remark"),
    ("出处", "Source"),
    ("英文名", "Name EN"),
    ("纬度", "Lat"), ("经度", "Lng"),
]
STAT_KEYS = {label: key for key, label in toxlsx.STAT_LABELS}   # 职工总数 -> staff
DATE_FIELDS = {"始建", "终止"}
NUM_FIELDS = {"职工总数", "技术人员", "厂房面积", "建筑面积", "固定资产",
              "工业总产值", "销售收入", "实现利润", "纬度", "经度"}
# 同步的字段之外,笔记里还有几样只供参考,不回写
INFO_FIELDS = ["key", "推定坐标", "坐标依据", "同步时间", "synced"]

BAD_FN = re.compile(r'[\\/:*?"<>|#\^\[\]]')


def safe(name):
    return BAD_FN.sub("_", str(name)).strip() or "无名"


# ---------------------------------------------------------------- frontmatter

def split_note(text):
    """→ (frontmatter 原文, 正文)。没有 frontmatter 就前者为空。"""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end < 0:
        return "", text
    fm = text[3:end].strip("\n")
    rest = text[end + 4:]
    return fm, rest.lstrip("\n")


def parse_fm(fm_text):
    """够用就好的 YAML:一行一个 `键: 值`,值是标量。列表只认 tags。"""
    out = OrderedDict()
    for line in (fm_text or "").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if not k:
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


def dump_fm(d):
    lines = []
    for k, v in d.items():
        s = "" if v is None else str(v)
        if s.startswith("[") and s.endswith("]"):
            lines.append("%s: %s" % (k, s))
            continue
        if s == "" or re.search(r'[:#\[\]{},&*?|>%@`"\']|^\s|\s$', s):
            s = '"%s"' % s.replace('"', "'")
        lines.append("%s: %s" % (k, s))
    return "---\n" + "\n".join(lines) + "\n---\n"


def split_managed(body):
    """→ (managed 段, 你自己写的那段)。"""
    i = body.find(MANAGED_START)
    if i < 0:
        return "", body
    j = body.find(MANAGED_END, i)
    if j < 0:
        return body[i + len(MANAGED_START):], ""
    return body[i + len(MANAGED_START):j], body[j + len(MANAGED_END):]


def fingerprint(fm, managed):
    """只按「会回写的字段 + managed 段」算指纹 —— 你写的札记改了不算数。"""
    parts = ["名称=" + str(fm.get("名称", ""))]
    for key, _col in FIELDS:
        parts.append("%s=%s" % (key, str(fm.get(key, "")).strip()))
    parts.append(re.sub(r"\s+", " ", managed).strip())
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- 值的折算

def norm_value(key, raw):
    """库里写的值 → 工作簿里该有的样子。日期宽进(1966.6 / 1966年6月都认)。"""
    s = "" if raw is None else str(raw).strip()
    if s == "":
        return ""
    if key in DATE_FIELDS:
        got = cndate.parse(s)
        return got if got else s          # 折算不出来就照录,pull 时会报出来
    if key in NUM_FIELDS:
        t = s.replace(",", "")
        try:
            f = float(t)
            return int(f) if f == int(f) and key not in ("纬度", "经度") else f
        except ValueError:
            return s
    return s


def cell_text(v):
    """工作簿里的值 → 笔记里的写法。"""
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def same(a, b):
    """比对时忽略 1218 与 1218.0 一类的差别。"""
    sa, sb = cell_text(a), cell_text(b)
    if sa == sb:
        return True
    try:
        return abs(float(sa) - float(sb)) < 1e-9
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- 写笔记

def _nh_table(segs):
    head = ["| 名称 | 启用 | 英文名 | 备注 | 出处 |", "| --- | --- | --- | --- | --- |"]
    if not segs:
        return head + ["|  |  |  |  |  |"]
    rows = []
    for s in segs:
        rows.append("| %s | %s | %s | %s | %s |" % (
            cell_text(s.get("Name")), cell_text(s.get("From")), cell_text(s.get("Name EN")),
            cell_text(s.get("Remark")).replace("|", "／"),
            cell_text(s.get("Source")).replace("|", "／")))
    return head + rows


NH_HEADING = "## 名称沿革"


def parse_nh_table(managed):
    """把「名称沿革」那一节里的表读回来。

    **只读这一节。** managed 段里还有只读的产品表,列数相仿;
    若不认标题一律扫过去,DJS-130 小型计算机就会摇身变作一段厂名
    ——「16」当年份、「400K-500K」当英文名,一路写进 Name-History。"""
    lines = managed.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().startswith(NH_HEADING))
    except StopIteration:
        return []
    out = []
    for line in lines[start + 1:]:
        s = line.strip()
        if s.startswith("## "):          # 下一节开始了
            break
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if cells[0] == "名称" or set("".join(cells)) <= set("- :"):
            continue                      # 表头与分隔行
        if not cells[0].strip() or not cells[1].strip():
            continue                      # 留白的空行
        out.append({"Name": cells[0], "From": cells[1], "Name EN": cells[2],
                    "Remark": cells[3], "Source": cells[4]})
    return out


def render(unit, nh, semi, comp, place, prose=""):
    raw = unit["raw"]
    name = re.sub(r"[（(][^）)]*[）)]", "", raw).strip()

    fm = OrderedDict()
    fm["key"] = raw                       # 匹配用的钥匙,别改
    fm["名称"] = raw                       # 要改名就改这一行
    fm["类型"] = "单位"
    for key, col in FIELDS:
        src = STAT_KEYS.get(col, col)     # 统计块在 read_units_full 里是英文 key
        fm[key] = cell_text(unit.get(src if src in unit else col))
    if place and place.get("lat") is not None:
        fm["推定坐标"] = "%.4f, %.4f" % (place["lat"], place["lng"])
        fm["坐标依据"] = "geocode.js %s（人工近似,未回写)" % (place.get("precision") or "")
    fm["tags"] = "[电子工业, 地图]"

    managed = ["", "## 名称沿革", "",
               "> 一行一段名字,`启用` 是这个名字开始用的日期(19660300 = 1966 年 3 月)。",
               "> 改这张表,`gaz pull` 会照改 Name-History 工作表。", ""]
    managed += _nh_table(nh)
    managed += ["", "> 只登记改过名的单位;没改过名的,这张表空着即可。", ""]

    if semi or comp:
        managed += ["## 产品记录", "",
                    "> **这一段是只读的。** 器件与整机的记录一行可能牵着两三家单位,",
                    "> 从各家的笔记里往回并容易打架,所以仍在工作簿里改。", ""]
        if semi:
            managed += ["**器件**", "", "| 产品 | 时间 | 人员 | 备注 |", "| --- | --- | --- | --- |"]
            managed += ["| %s | %s | %s | %s |" % (
                cell_text(s.get("Product")), cndate.fmt(cell_text(s.get("Time"))),
                cell_text(s.get("Personnel")), cell_text(s.get("Remark")).replace("|", "／"))
                for s in semi]
            managed += [""]
        if comp:
            managed += ["**整机**", "",
                        "| 产品 | 字长 | 内存 | 速度(次/秒) | 时间 | 人员 |",
                        "| --- | --- | --- | --- | --- | --- |"]
            managed += ["| %s | %s | %s | %s | %s | %s |" % (
                cell_text(c.get("Product")), cell_text(c.get("字长")), cell_text(c.get("内存")),
                cell_text(c.get("Speed（次秒）")), cndate.fmt(cell_text(c.get("Time"))),
                cell_text(c.get("Personnel"))) for c in comp]
            managed += [""]

    managed_text = "\n".join(managed)
    fm["同步时间"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    fm["synced"] = fingerprint(fm, managed_text)

    if not prose.strip():
        prose = "\n## 札记\n\n（这一段归你,`gaz push` 不动它。存疑之处、别处的旁证、" \
                "还没定夺的写法,都写在这儿。）\n"

    return (dump_fm(fm) + "\n# " + name + "\n"
            + MANAGED_START + managed_text + MANAGED_END + "\n" + prose)


# ---------------------------------------------------------------- push

def push(xlsx_path, vault_dir, geocode_js=None, force=False, log=print):
    units = toxlsx.read_units_full(xlsx_path)
    nh_all = toxlsx.read_name_history(xlsx_path)
    semi_all = toxlsx.read_semi(xlsx_path)
    comp_all = toxlsx.read_comp(xlsx_path)
    places = _read_places_full(geocode_js) if geocode_js else {}
    known = toxlsx.merge_known(xlsx_path, geocode_js) if geocode_js else {}

    os.makedirs(vault_dir, exist_ok=True)
    wrote = kept = 0
    skipped = []
    for u in units:
        raw = u["raw"]
        name = re.sub(r"[（(][^）)]*[）)]", "", raw).strip()
        path = os.path.join(vault_dir, safe(name) + ".md")

        prose = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = f.read()
            fm_old_text, body_old = split_note(old)
            fm_old = parse_fm(fm_old_text)
            managed_old, prose = split_managed(body_old)
            if fm_old.get("synced") and not force:
                if fingerprint(fm_old, managed_old) != fm_old["synced"]:
                    skipped.append(name)
                    kept += 1
                    continue

        aliases = set([raw, name] + list(known.get(name, [])))
        nh = [r for r in nh_all if _match(r.get("Unit"), aliases)]
        nh.sort(key=lambda r: str(r.get("From") or ""))
        semi = [r for r in semi_all if _match(r.get("Factory"), aliases)]
        comp = [r for r in comp_all
                if _match(r.get("Factory"), aliases) or _match(r.get("Research Insti"), aliases)]

        with open(path, "w", encoding="utf-8") as f:
            f.write(render(u, nh, semi, comp, places.get(name), prose))
        wrote += 1

    _write_index(units, vault_dir)
    log("写出 %d 则笔记 → %s" % (wrote, vault_dir))
    if skipped:
        log("跳过 %d 则:库里改过、还没 pull 回去 —— %s" % (len(skipped), "、".join(skipped[:8])))
        log("     先跑 `gaz pull` 把改动收回工作簿;确要拿工作簿的值盖掉,加 --force。")
    return {"wrote": wrote, "skipped": skipped, "kept": kept}


def _match(cell, aliases):
    s = str(cell or "")
    return any(a and a in s for a in aliases)


def _read_places_full(geocode_js):
    """geocode.js 的 PLACES,连坐标一并读出(只作参考,不回写)。"""
    if not geocode_js or not os.path.exists(geocode_js):
        return {}
    with open(geocode_js, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"export\s+const\s+PLACES\s*=\s*\{(.*?)\n\};", src, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        mm = re.match(r'\s*"([^"]+)"\s*:\s*\{(.*)\}', line)
        if not mm:
            continue
        body = mm.group(2)
        lat = re.search(r"lat:\s*([-\d.]+)", body)
        lng = re.search(r"lng:\s*([-\d.]+)", body)
        prec = re.search(r'precision:\s*"([^"]*)"', body)
        out[mm.group(1)] = {
            "lat": float(lat.group(1)) if lat else None,
            "lng": float(lng.group(1)) if lng else None,
            "precision": prec.group(1) if prec else "",
        }
    return out


def _write_index(units, vault_dir):
    by = {}
    for u in units:
        by.setdefault(u.get("Industry") or "未分类", []).append(u)
    out = ["---", "title: 中国电子工业历史地图 · 厂所索引", "类型: 索引",
           "tags: [电子工业, 索引]", "---", "",
           "# 厂所索引", "",
           "共 %d 家。改哪一家就点进哪一则,改完 `gaz pull` 推回工作簿。" % len(units), ""]
    for ind in sorted(by, key=lambda k: -len(by[k])):
        out += ["## %s（%d）" % (ind, len(by[ind])), "",
                "| 单位 | 始建 | 终止 | 地址 |", "| --- | --- | --- | --- |"]
        for u in sorted(by[ind], key=lambda x: str(x.get("Start Date") or "9")):
            nm = re.sub(r"[（(][^）)]*[）)]", "", u["raw"]).strip()
            out.append("| [[%s]] | %s | %s | %s |" % (
                safe(nm), cndate.fmt(cell_text(u.get("Start Date"))),
                cndate.fmt(cell_text(u.get("End Date"))), cell_text(u.get("Add.")) or "—"))
        out.append("")
    with open(os.path.join(vault_dir, "_厂所索引.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))


# ---------------------------------------------------------------- pull

def collect(xlsx_path, vault_dir):
    """把库里与工作簿不一样的地方找出来,不动任何文件。"""
    units = {u["raw"]: u for u in toxlsx.read_units_full(xlsx_path)}
    nh_all = toxlsx.read_name_history(xlsx_path)
    changes, nh_new, problems, unknown = [], None, [], []
    nh_touched, seen, troubled = {}, [], set()

    for fn in sorted(os.listdir(vault_dir)):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        with open(os.path.join(vault_dir, fn), encoding="utf-8") as f:
            text = f.read()
        fm_text, body = split_note(text)
        fm = parse_fm(fm_text)
        key = fm.get("key")
        if not key:
            continue
        if key not in units:
            unknown.append((fn, key))
            continue
        u = units[key]
        managed, _prose = split_managed(body)
        seen.append(os.path.join(vault_dir, fn))

        fields, shown = {}, []
        newname = fm.get("名称", "").strip()
        if newname and newname != key:
            shown.append(("名称", key, newname))
        for fkey, col in FIELDS:
            src = STAT_KEYS.get(col, col)
            cur = u.get(src if src in u else col)
            want = norm_value(fkey, fm.get(fkey, ""))
            if fkey in DATE_FIELDS and want and not re.fullmatch(r"\d{8}", str(want)):
                problems.append("%s:%s 的日期「%s」折算不出来,这一格没动" % (fn, fkey, fm.get(fkey)))
                troubled.add(os.path.join(vault_dir, fn))
                continue
            if not same(cur, want):
                fields[col] = want
                shown.append((fkey, cell_text(cur), cell_text(want)))
        if fields or (newname and newname != key):
            ch = {"_row": u["_row"], "fields": fields, "file": fn, "shown": shown}
            if newname and newname != key:
                ch["名称"] = newname
            changes.append(ch)

        segs = parse_nh_table(managed)
        unit_label = newname or key
        nh_touched[key] = [dict(s, Unit=unit_label) for s in segs
                           if s.get("Name") and s.get("From")]

    # 名称沿革:库里登记过的单位以库为准,没登记的照旧
    if nh_touched:
        keep = [r for r in nh_all
                if not any(_match(r.get("Unit"), {k, re.sub(r"[（(][^）)]*[）)]", "", k).strip()})
                           for k in nh_touched)]
        rebuilt = list(keep)
        for k in nh_touched:
            for s in nh_touched[k]:
                s = dict(s)
                got = cndate.parse(s.get("From"))
                if got:
                    s["From"] = got
                rebuilt.append(s)
        rebuilt.sort(key=lambda r: (str(r.get("Unit") or ""), str(r.get("From") or "")))
        if _nh_differs(nh_all, rebuilt):
            nh_new = rebuilt
    return {"changes": changes, "name_history": nh_new, "problems": problems,
            "unknown": unknown, "seen": seen, "troubled": troubled}


def restamp(paths, log=print):
    """pull 之后给笔记重新盖戳。

    戳记("synced")记的是「上一次与工作簿对齐时,这则笔记长什么样」。pull 把
    库里的改动收进工作簿之后,两边就对齐了 —— 戳记若不跟着更新,下一次 push
    会把这些刚刚收进去的笔记当成「改过还没 pull」,平白跳过。"""
    n = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        fm_text, body = split_note(text)
        fm = parse_fm(fm_text)
        if not fm.get("synced"):
            continue
        managed, _ = split_managed(body)
        fresh = fingerprint(fm, managed)
        if fresh == fm["synced"]:
            continue
        fm["synced"] = fresh
        fm["同步时间"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(path, "w", encoding="utf-8") as f:
            f.write(dump_fm(fm) + "\n" + body.lstrip("\n"))
        n += 1
    return n


def _nh_differs(old, new):
    def norm(rows):
        return sorted(tuple(cell_text(r.get(c)) for c in
                            ("Unit", "Name", "From", "Name EN", "Remark", "Source"))
                      for r in rows)
    return norm(old) != norm(new)


def pull(xlsx_path, vault_dir, dry_run=False, log=print):
    got = collect(xlsx_path, vault_dir)
    changes, nh_new = got["changes"], got["name_history"]

    for msg in got["problems"]:
        log("  ! " + msg)
    for fn, key in got["unknown"]:
        log("  ? %s 的 key「%s」在名录里找不到 —— 新单位请走 gaz xlsx,不走 pull" % (fn, key))

    if not changes and not nh_new:
        log("库与工作簿一致,没有要改的。")
        return {"units": 0, "cells": 0, "name_history": 0}

    for ch in changes:
        log("  %s" % ch["file"])
        for fkey, old, new in ch["shown"]:
            log("     %s: %s → %s" % (fkey, old or "（空）", new or "（空）"))
    if nh_new:
        log("  名称沿革表将重写为 %d 行" % len(nh_new))

    if dry_run:
        log("(--dry-run,未落笔)")
        return {"units": len(changes), "cells": 0, "name_history": len(nh_new or [])}

    rep = toxlsx.update_units(xlsx_path, changes, log=log)
    n_nh = toxlsx.rewrite_name_history(xlsx_path, nh_new) if nh_new else 0
    stamped = restamp([p for p in got["seen"] if p not in got["troubled"]])
    if stamped:
        log("%d 则笔记重新盖戳(下次 push 不会再当它们是未推的改动)" % stamped)
    log("已写回 %s:%d 家单位、%d 格%s"
        % (os.path.basename(xlsx_path), len(changes), rep["cells"],
           ("、名称沿革 %d 行" % n_nh) if n_nh else ""))
    return {"units": len(changes), "cells": rep["cells"], "name_history": n_nh}
