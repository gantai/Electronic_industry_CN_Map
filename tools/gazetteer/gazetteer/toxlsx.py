# -*- coding: utf-8 -*-
"""过了人眼的记录 → 追加进 CN_Electronic_Industry.xlsx。

**只追加,不改动既有行。** 动手之前先把原文件另存一份带时间戳的备份。
表头按名字认列,不按字母位置认 —— 将来在表尾添 `Name EN` / `Lat` / `Lng`
也不会串行(见 src/xlsxio.js 的读法)。
"""

import os
import re
import shutil
from datetime import datetime

SHEET_UNITS = "Fact and Comp-Shanghai"
SHEET_SEMI = "Semi-Product"
SHEET_COMP = "Comp-Product"
SHEET_NAMES = "Name-History"

STAT_LABELS = [("staff", "职工总数"), ("tech", "技术人员"), ("plant", "厂房面积"),
               ("floor", "建筑面积"), ("assets", "固定资产"), ("output", "工业总产值"),
               ("sales", "销售收入"), ("profit", "实现利润")]


def _open(path):
    import openpyxl
    return openpyxl.load_workbook(path)


def _headers(ws, rows=2):
    """{表头文字: 列号},两行表头一并收。"""
    idx = {}
    for r in range(1, rows + 1):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if v is None:
                continue
            key = str(v).strip()
            if key and key not in idx:
                idx[key] = c
    return idx


def _num(v):
    """数字照数字写,日期写成八位整数,其余照录字符串。"""
    s = str(v if v is not None else "").strip()
    if s == "":
        return None
    if re.fullmatch(r"\d{8}", s):
        return int(s)
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


ALIAS_SPLIT = re.compile(r"[、,，;；/／|]")


def _bare(v):
    """判重用的样子:去掉括号与空白。「上海无线电十九厂(上无十九)」→ 上海无线电十九厂"""
    return re.sub(r"\s+", "", re.sub(r"[（(][^）)]*[）)]", "", str(v or ""))).strip()


def _names_of(name_cell, alias_cell=""):
    """这一行占着哪些名字 —— 正名、名字里括号中的、以及「别名」列里的。"""
    out = {_bare(name_cell)} if _bare(name_cell) else set()
    for grp in re.findall(r"[（(]([^）)]*)[）)]", str(name_cell or "")):
        out |= {x.strip() for x in ALIAS_SPLIT.split(grp) if x.strip()}
    out |= {x.strip() for x in ALIAS_SPLIT.split(str(alias_cell or "")) if x.strip()}
    return out


def _existing_names(ws, first_data_row, alias_col=None):
    """表里已经占着的名字。别名也算 —— 「四机部15所」与「华北计算技术研究所」
    是一家,凭正名比对,同一家会当成两家收两次。"""
    out = set()
    for r in range(first_data_row, ws.max_row + 1):
        alias = ws.cell(row=r, column=alias_col).value if alias_col else ""
        out |= _names_of(ws.cell(row=r, column=1).value, alias)
    return out


def _existing_keys(ws, cols, h, first_data_row=2):
    """器件、整机、沿革三张表的判重钥匙 —— 原先一道也没有,跑两遍就多一份。"""
    seen = set()
    for r in range(first_data_row, ws.max_row + 1):
        key = tuple(_bare(ws.cell(row=r, column=h[c]).value) if c in h else ""
                    for c in cols)
        if any(key):
            seen.add(key)
    return seen


def _last_row(ws, col=1, start=1):
    last = start - 1
    for r in range(start, ws.max_row + 1):
        if any(ws.cell(row=r, column=c).value not in (None, "")
               for c in range(1, ws.max_column + 1)):
            last = r
    return last


def append(xlsx_path, units=(), semi=(), comp=(), names=(), backup=True,
           allow_dup=False, log=print):
    wb = _open(xlsx_path)
    report = {"backup": "", "units": 0, "semi": 0, "comp": 0, "names": 0, "skipped": []}

    if backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = "%s.backup-%s.xlsx" % (os.path.splitext(xlsx_path)[0], stamp)
        shutil.copy2(xlsx_path, bak)
        report["backup"] = bak
        log("原表已备份到 %s" % os.path.basename(bak))

    # ---- 厂所名录(两行表头,正文自第 3 行起)
    if units:
        ws = wb[SHEET_UNITS]
        h = _headers(ws, 2)
        have = _existing_names(ws, 3, alias_col=h.get("别名"))
        row = _last_row(ws, start=3) + 1
        for r in units:
            nm = str(r.get("Unit") or r.get("name") or "").strip()
            if not nm:
                continue
            mine = _names_of(nm, r.get("别名", ""))
            if not allow_dup and (mine & have):
                report["skipped"].append(
                    "%s(表内已有「%s」)" % (nm, sorted(mine & have)[0])
                    if _bare(nm) not in have else nm)
                continue
            ws.cell(row=row, column=1, value=nm)
            if str(r.get("别名") or "").strip():
                _ensure_column(ws, "别名", header_row=1)
                h = _headers(ws, 2)
            for label in ("Industry", "Product", "Start Date", "End Date", "Founder",
                          "City", "Add.", "Remark", "Source", "Name EN", "Lat", "Lng",
                          "别名"):
                if label in h and r.get(label) not in (None, ""):
                    ws.cell(row=row, column=h[label], value=_num(r[label]))
            for key, label in STAT_LABELS:
                if label in h and r.get(key) not in (None, ""):
                    ws.cell(row=row, column=h[label], value=_num(r[key]))
            have |= mine
            row += 1
            report["units"] += 1

    def _append_flat(sheet, cols, rows, tag, text_cols=(), ensure=(), dedup_on=()):
        if not rows:
            return
        ws = wb[sheet]
        for label in ensure:
            if any(r.get(label) not in (None, "") for r in rows):
                _ensure_column(ws, label)
        h = _headers(ws, 1)
        keys = set() if allow_dup else _existing_keys(ws, dedup_on, h)
        row = _last_row(ws, start=2) + 1
        for r in rows:
            k = tuple(_bare(r.get(c)) for c in dedup_on)
            if any(k) and k in keys:
                report["skipped"].append("%s:%s" % (tag, k[0]))
                continue
            if any(k):
                keys.add(k)
            wrote = False
            for label in cols:
                if label in h and r.get(label) not in (None, ""):
                    v = str(r[label]) if label in text_cols else _num(r[label])
                    ws.cell(row=row, column=h[label], value=v)
                    wrote = True
            if wrote:
                row += 1
                report[tag] += 1

    _append_flat(SHEET_SEMI, ["Product", "别名", "Research Insti", "Factory", "产量", "Time",
                             "Personnel", "Remark"],
                 semi, "semi", ensure=("产量", "别名", "Research Insti"),
                 dedup_on=("Product", "Factory", "Time"))
    # 「用户」是原表没有的一列 —— 机器交到谁手里用,记在这儿(见 src/xlsxio.js)
    _append_flat(SHEET_COMP, ["Product", "字长", "内存", "Speed（次秒）", "Research Insti",
                              "Factory", "用户", "产量", "别名", "Time", "Personnel", "Remark"], comp, "comp",
                 ensure=("用户", "产量", "别名"), dedup_on=("Product", "Time"))
    # Name-History 的 From 一列,原表存的是文本(见 src/xlsxio.js 的 exportWorkbook),照旧
    _append_flat(SHEET_NAMES, ["Unit", "Name", "From", "Name EN", "Remark", "Source"],
                 names, "names", text_cols=("From",), dedup_on=("Unit", "Name", "From"))

    try:
        wb.save(xlsx_path)
    except PermissionError:
        # 这一份是总表,不能改名另存 —— 换了名字就不是那本工作簿了
        raise SystemExit(
            "写不进 %s —— 多半正开在 Excel 里,文件被锁着。\n"
            "关掉 Excel 再跑一遍。原表还是原样,备份也还在:%s"
            % (os.path.basename(xlsx_path), report["backup"] or "(这次没备份)"))
    return report


def read_known(xlsx_path):
    """把表里已有的单位名读出来(连括号里的别名),供抽取时辨认旧识。"""
    if not os.path.exists(xlsx_path):
        return {}
    wb = _open(xlsx_path)
    ws = wb[SHEET_UNITS]
    known = {}
    for r in range(3, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if not v:
            continue
        raw = str(v).strip()
        canon = re.sub(r"[（(][^）)]*[）)]", "", raw).strip()
        m = re.search(r"[（(]([^）)]*)[）)]", raw)
        known[canon] = [raw] + ([m.group(1).strip()] if m else [])
    return known


def read_aliases(geocode_js):
    """把 src/geocode.js 的 ALIASES 读出来。

    「上无十三」「上五十三」这类简称不合单位名的体例,正则认不出来,
    只能靠这张人工对照表。它已经在仓库里,没有理由再抄一份。"""
    if not os.path.exists(geocode_js):
        return {}
    with open(geocode_js, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"export\s+const\s+ALIASES\s*=\s*\{(.*?)\n\};", src, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        mm = re.match(r'\s*"([^"]+)"\s*:\s*\[([^\]]*)\]', line)
        if mm:
            out[mm.group(1)] = re.findall(r'"([^"]+)"', mm.group(2))
    return out


def merge_known(xlsx_path, geocode_js=None):
    known = read_known(xlsx_path)
    for canon, aliases in (read_aliases(geocode_js) if geocode_js else {}).items():
        known.setdefault(canon, [])
        for a in aliases:
            if a not in known[canon]:
                known[canon].append(a)
    return known


def read_places(geocode_js):
    """src/geocode.js 的 PLACES 里已经有落点的单位名。"""
    if not os.path.exists(geocode_js):
        return set()
    with open(geocode_js, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"export\s+const\s+PLACES\s*=\s*\{(.*?)\n\};", src, re.S)
    return set(re.findall(r'^\s*"([^"]+)"\s*:', m.group(1), re.M)) if m else set()


# ============================================================
#  以下供 vault.py 用:整本读出、按行改回
#  ------------------------------------------------------------
#  append() 只管往表尾添行;库里改过的字段要写回**原来那一行**,
#  故另备一套按表头认列、按行号定位的读写。
# ============================================================

UNIT_LABELS = ["Industry", "Product", "Start Date", "End Date", "Founder", "City", "Add.",
               "Remark", "Source", "Name EN", "Lat", "Lng"]


def read_units_full(xlsx_path):
    """厂所名录整本读出,每行带着它在表里的行号,回写时据以定位。"""
    wb = _open(xlsx_path)
    ws = wb[SHEET_UNITS]
    h = _headers(ws, 2)
    out = []
    for r in range(3, ws.max_row + 1):
        raw = ws.cell(row=r, column=1).value
        if raw is None or not str(raw).strip():
            continue
        rec = {"_row": r, "raw": str(raw).strip()}
        for label in UNIT_LABELS:
            rec[label] = ws.cell(row=r, column=h[label]).value if label in h else None
        for key, label in STAT_LABELS:
            rec[key] = ws.cell(row=r, column=h[label]).value if label in h else None
        out.append(rec)
    return out


def read_flat(xlsx_path, sheet, cols):
    wb = _open(xlsx_path)
    if sheet not in wb.sheetnames:
        return []
    ws = wb[sheet]
    h = _headers(ws, 1)
    out = []
    for r in range(2, ws.max_row + 1):
        rec = {"_row": r}
        got = False
        for label in cols:
            v = ws.cell(row=r, column=h[label]).value if label in h else None
            rec[label] = v
            if v not in (None, ""):
                got = True
        if got:
            out.append(rec)
    return out


def read_name_history(xlsx_path):
    return read_flat(xlsx_path, SHEET_NAMES, ["Unit", "Name", "From", "Name EN", "Remark", "Source"])


def read_semi(xlsx_path):
    return read_flat(xlsx_path, SHEET_SEMI, ["Product", "Factory", "Time", "Personnel", "Remark"])


def read_comp(xlsx_path):
    return read_flat(xlsx_path, SHEET_COMP, ["Product", "字长", "内存", "Speed（次秒）",
                                             "Research Insti", "Factory", "Time",
                                             "Personnel", "Remark"])


def _ensure_column(ws, label, header_row=1):
    """表尾按需添一列(Name EN / Lat / Lng 原表没有,库里填了才添)。"""
    h = _headers(ws, 2)
    if label in h:
        return h[label]
    col = ws.max_column + 1
    ws.cell(row=header_row, column=col, value=label)
    return col


def update_units(xlsx_path, changes, backup=True, log=print):
    """把库里改动的字段写回原行。

    changes: [{"_row": 3, "名称": "...", "fields": {"Industry": "半导体", ...}}]
    只动列出来的格子,别的一律不碰。"""
    wb = _open(xlsx_path)
    ws = wb[SHEET_UNITS]
    bak = ""
    if backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = "%s.backup-%s.xlsx" % (os.path.splitext(xlsx_path)[0], stamp)
        shutil.copy2(xlsx_path, bak)
        log("原表已备份到 %s" % os.path.basename(bak))

    n = 0
    for ch in changes:
        row = ch["_row"]
        if "名称" in ch:
            ws.cell(row=row, column=1, value=ch["名称"])
            n += 1
        for label, val in (ch.get("fields") or {}).items():
            col = _ensure_column(ws, label)
            ws.cell(row=row, column=col, value=(None if val in ("", None) else _num(val)))
            n += 1
    wb.save(xlsx_path)
    return {"cells": n, "backup": bak}


def rewrite_name_history(xlsx_path, rows, backup=False, log=print):
    """名称沿革整表重写 —— 库里改的是「某单位的全部段落」,逐格补丁反而易错。"""
    wb = _open(xlsx_path)
    if SHEET_NAMES not in wb.sheetnames:
        ws = wb.create_sheet(SHEET_NAMES)
        ws.append(["Unit", "Name", "From", "Name EN", "Remark", "Source"])
    ws = wb[SHEET_NAMES]
    # 原表没有 Name EN 一列;库里填了英文名就把这一列添上,不能悄悄丢掉
    if any(str(r.get("Name EN") or "").strip() for r in rows):
        _ensure_column(ws, "Name EN")
    h = _headers(ws, 1)
    order = sorted(h, key=lambda k: h[k])
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    for i, r in enumerate(rows, start=2):
        for label in order:
            if label not in h:
                continue
            v = r.get(label, "")
            ws.cell(row=i, column=h[label],
                    value=(None if v in ("", None) else (str(v) if label == "From" else _num(v))))
    wb.save(xlsx_path)
    return len(rows)
