#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整条流水线的回归测试:纪年折算 → Markdown → 抽取 → 回写 xlsx。

不依赖 pytest,直接跑:

    python3 tools/gazetteer/tests/test_pipeline.py

样张见 fixture/README.md,盯的是几处最容易张冠李戴的地方。
"""

import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

from gazetteer import (bookmd, cndate, extract as EX, notes,  # noqa: E402
                       toxlsx, tsvio, vault)

FAILED = []


def check(cond, what):
    print(("  ✓ " if cond else "  ✗ ") + what)
    if not cond:
        FAILED.append(what)


def eq(got, want, what):
    check(got == want, "%s(得 %r)" % (what, got) if got != want else what)


# ---------------------------------------------------------------- 纪年

def test_dates():
    print("纪年折算")
    eq(cndate.parse("1958年3月"), "19580300", "1958年3月")
    eq(cndate.parse("一九五八年三月十日"), "19580310", "一九五八年三月十日")
    eq(cndate.parse("民国二十六年"), "19370000", "民国二十六年")
    eq(cndate.parse("1958年上半年"), "19580000", "季度写法退到年")
    eq(cndate.parse("19660601"), "19660601", "已是八位写法")
    eq(cndate.parse("没有日期"), None, "没有日期就留空")
    eq(cndate.fmt("19730400"), "1973.04", "给人看的写法")


# ---------------------------------------------------------------- 认名字

def test_names():
    print("单位名")
    eq(EX.unit_names("该机与上海无线电十三厂协作生产。"), ["上海无线电十三厂"], "连接词后头的名字")
    eq(EX.unit_names("由上海红星电讯厂和上海新华电器厂合并组建。"),
       ["上海红星电讯厂", "上海新华电器厂"], "并列的两家")
    eq(EX.unit_names("上海和平电器厂由某某厂改组。"), ["上海和平电器厂"], "名字里带「和」不被截断")
    eq(EX.unit_names("1966年3月改名为上海无线电十九厂。"), ["上海无线电十九厂"], "剥掉年月与动词")
    eq(EX.unit_names("厂房面积15600平方米。"), [], "厂房不是厂")
    eq(EX.unit_names("该所所长由王某担任,全所职工486人。"), [], "所长不是所")
    # 以下都是拿《北京工业志·电子志》第三章跑出来的漏子
    eq(EX.unit_names("交由国营738厂试制。"), ["国营738厂"], "厂名里的数字不是断点")
    eq(EX.unit_names("四机部15所为空军125工程研制108甲。"), ["四机部15所"],
       "「四机部」是部委正名,不是「四个机部」")
    eq(EX.unit_names("生产厂家有北京计算机外部设备三厂。"), ["北京计算机外部设备三厂"],
       "「设备」的「设」不是断点,「厂家」也不算收尾")
    eq(EX.unit_names("北京北优计算机系统有限公司承接。"), ["北京北优计算机系统有限公司"],
       "「系统」的「系」不是断点")
    eq(EX.unit_names("华北计算技术研究所和哈尔滨军事工程学院联合研制。"),
       ["华北计算技术研究所", "哈尔滨军事工程学院"], "「和」连着的两家不并成一家")
    eq(EX.find_district(["厂址杨浦区平凉路1690号。"]), "杨浦", "区名不带前一个字")
    eq(EX.find_address(["上海元件十四厂,厂址在闸北区中华新路688号。"])[0], "中华新路688号",
       "地址照原表体例,不带区名")


# ---------------------------------------------------------------- 整条流水线

def test_pipeline():
    print("转换稿")
    # 扫描件 → Markdown 归 zhiconv 管(见 Historian_Archive_Management)。
    # 这里定死一份它那种成色的稿子,验的是抽取,不是转换。
    md, _enc = bookmd.read_text(os.path.join(HERE, "fixture", "上海电子仪表工业志.md"))
    check("<!-- p.101 -->" in md and "<!-- p.247 -->" in md, "页码锚点在")
    check("### 第一章 半导体器件" in md, "标题层级在")
    check("1958年6月建立。1966年3月" in md, "正文没有断行")

    print("抽取")
    known = toxlsx.merge_known(os.path.join(REPO, "CN_Electronic_Industry.xlsx"),
                               os.path.join(REPO, "src", "geocode.js"))
    res = EX.extract(md, book="上海电子仪表工业志", known=known)
    by = {r["Unit"]: r for r in res["units"]}

    check("上海无线电十九厂" in by and "上海元件十四厂" in by and "上海计算机研究所" in by,
          "三家专条单位都抽到了")
    u = by["上海无线电十九厂"]
    eq(u["Start Date"], "19580600", "十九厂始建年")
    eq(u["End Date"], "", "十九厂没有终止年(撤销的是元件十四厂)")
    check("并入" not in u["Founder"], "他家并入本厂的话没混进 Founder")
    eq(u["Add."], "平凉路1690号", "十九厂门牌")
    eq(u["staff"], 1218.0, "职工总数")
    eq(u["profit"], 432.8, "实现利润")
    eq(u["Industry"], "半导体", "行业")
    check(u["Source"].endswith("p.101"), "出处回注到页")

    v = by["上海元件十四厂"]
    eq(v["End Date"], "19851200", "元件十四厂终止年")
    check("并入上海无线电十九厂" in v["Remark"], "终局归并记进备注")
    check("并入" not in v["Founder"], "终局归并不进 Founder")
    check(v["Founder"].startswith("上海红星电讯厂和上海新华电器厂合并"), "合并来历")

    w = by["上海计算机研究所"]
    eq(w["Start Date"], "19610500", "计算所始建年")
    check("19650000改名上海市计算技术研究所" in w["Founder"], "中文数字纪年的改名")
    eq(w["district"], "徐汇", "区名")

    print("名称沿革")
    segs = [r for r in res["names"] if r["Unit"] == "上海计算机研究所"]
    eq(len(segs), 3, "计算所三段名称")
    check(all(r["Source"].startswith("上海电子仪表工业志") for r in segs),
          "沿革出处是志书页码,不是「据 Founder 列推定」")

    print("产品记录")
    semi = {(r["Product"], r["Factory"]): r for r in res["semi"]}
    check(("锗合金晶体管", "上海无线电十九厂") in semi, "器件挂到本厂")
    eq(semi[("锗合金晶体管", "上海无线电十九厂")]["Time"], "19590000", "器件投产年")
    eq(semi[("锗合金晶体管", "上海无线电十九厂")]["Personnel"], "周德昌", "人名不带职称")
    check(not any(r["Factory"] == "上海无线电十九厂" and r["Product"] == "可控硅整流器"
                  for r in res["semi"]), "别家的产品没串门")

    comp = {r["Product"]: r for r in res["comp"]}
    eq(comp["TQ-16型晶体管计算机"]["字长"], "48", "字长")
    eq(comp["TQ-16型晶体管计算机"]["Speed（次秒）"], "110000", "每秒11万次 → 110000")
    eq(comp["TQ-16型晶体管计算机"]["Personnel"], "虞浦帆、何育辽", "两位主持人")
    eq(comp["TQ-16型晶体管计算机"]["Factory"], "上海无线电十三厂", "协作厂")
    eq(comp["DJS-130型小型计算机"]["Factory"], "", "协作只算前一台机器")

    print("回写工作簿")
    tmp = tempfile.mkdtemp(prefix="gaz-test-")
    try:
        target = os.path.join(tmp, "wb.xlsx")
        shutil.copy2(os.path.join(REPO, "CN_Electronic_Industry.xlsx"), target)
        import openpyxl
        before = openpyxl.load_workbook(target)["Fact and Comp-Shanghai"].max_row
        picked = [dict(r, keep="y") for r in res["units"] if r["role"] == "专条"]
        rep = toxlsx.append(target, units=picked, semi=res["semi"], comp=res["comp"],
                            names=res["names"], backup=False, log=lambda *a: None)
        eq(rep["units"], 3, "追加 3 家单位")
        wb = openpyxl.load_workbook(target)
        ws = wb["Fact and Comp-Shanghai"]
        eq(ws.max_row, before + 3, "名录表多了 3 行")
        row = [c for c in next(ws.iter_rows(min_row=before + 1, max_row=before + 1,
                                            values_only=True))]
        eq(row[0], "上海无线电十九厂", "A 列是单位名")
        eq(row[3], 19580600, "始建日期写成八位整数")
        eq(row[8], 1218, "统计块落在职工总数那一格")
        nh = wb["Name-History"]
        last = [c for c in next(nh.iter_rows(min_row=nh.max_row, max_row=nh.max_row,
                                             values_only=True))]
        check(isinstance(last[2], str), "Name-History 的 From 照原表存成文本")

        print("Obsidian 笔记")
        vault = os.path.join(tmp, "vault")
        notes.write_vault(picked, vault, book="上海电子仪表工业志", book_note="上海电子仪表工业志",
                          log=lambda *a: None)
        with open(os.path.join(vault, "上海元件十四厂.md"), encoding="utf-8") as f:
            note = f.read()
        check("[[上海无线电十九厂]]" in note, "沿革里的单位连成 wikilink")
        check("始建: 1970.04" in note, "frontmatter 带始建年")
        check("原文佐证" in note, "原文照录")

        print("TSV 闸门")
        tsv = os.path.join(tmp, "u.tsv")
        tsvio.write(tsv, [dict(keep="?", Unit="甲"), dict(keep="y", Unit="乙")],
                    ["keep", "Unit"])
        eq([r["Unit"] for r in tsvio.kept(tsvio.read(tsv))], ["乙"], "只有 keep=y 的行放行")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)



def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def test_vault():
    """库 ←→ 工作簿的来回:改在 Obsidian 里,推回工作簿,再推回来不打架。"""
    print("库与工作簿的来回")
    import openpyxl
    tmp = tempfile.mkdtemp(prefix="gaz-vault-")
    try:
        xlsx = os.path.join(tmp, "wb.xlsx")
        shutil.copy2(os.path.join(REPO, "CN_Electronic_Industry.xlsx"), xlsx)
        geo = os.path.join(REPO, "src", "geocode.js")
        vdir = os.path.join(tmp, "vault")
        quiet = lambda *a: None

        rep = vault.push(xlsx, vdir, geocode_js=geo, log=quiet)
        eq(rep["wrote"], 29, "29 家各写一则")
        check(os.path.exists(os.path.join(vdir, "_厂所索引.md")), "索引也写了")

        note = os.path.join(vdir, "上海微波设备研究所.md")
        fm = vault.parse_fm(vault.split_note(_read(note))[0])
        eq(fm["key"], "上海微波设备研究所", "key 是匹配用的钥匙")
        eq(fm["行业"], "研究所", "字段照工作簿")
        check(fm.get("推定坐标", "").startswith("31.27"), "geocode.js 的推定坐标只作参考")
        eq(fm["纬度"], "", "推定坐标不冒充数据,纬度仍空着")

        nh_before = len(toxlsx.read_name_history(xlsx))
        got = vault.collect(xlsx, vdir)
        eq(len(got["changes"]), 0, "刚推出来,没有该改的")
        eq(got["name_history"], None, "名称沿革也没动")

        # 产品表混进名称沿革 —— 曾经真出过这个岔子
        big = os.path.join(vdir, "上海电子计算机厂.md")
        managed, _ = vault.split_managed(vault.split_note(_read(big))[1])
        check("整机" in managed, "整机表在 managed 段里")
        segs = vault.parse_nh_table(managed)
        check(all("计算机" not in s["Name"] for s in segs),
              "只读的产品表没被当成名称沿革(DJS-130 不是厂名)")

        # 改三样:普通字段、宽写的日期、自填坐标;再改一行沿革的出处
        s0 = _read(note)
        s0 = s0.replace('城市: ""', "城市: Shanghai")
        s0 = s0.replace("始建: 19501100", "始建: 1950年11月")
        s0 = s0.replace('纬度: ""', "纬度: 31.2701").replace('经度: ""', "经度: 121.3481")
        s0 = s0.replace("| 上海仪表铜厂 | 19610000 |  |  | 据 Founder 列推定,待核 |",
                        "| 上海仪表铜厂 | 19610000 | Copper Works | 1961年改称 | 仪表工业志 p.412 |")
        s0 = s0.replace("（这一段归你", "我的札记在此。（这一段归你")
        _write(note, s0)

        got = vault.collect(xlsx, vdir)
        eq(len(got["changes"]), 1, "认出一则改动")
        keys = {k for k, _o, _n in got["changes"][0]["shown"]}
        eq(keys, {"城市", "纬度", "经度"}, "只认出真改过的三样")
        check(got["name_history"] is not None, "沿革表也改了")

        rep = vault.pull(xlsx, vdir, log=quiet)
        eq(rep["units"], 1, "写回一家")
        eq(len(toxlsx.read_name_history(xlsx)), nh_before, "沿革行数不该无故增减")

        wb = openpyxl.load_workbook(xlsx)
        heads = [c.value for c in wb["Fact and Comp-Shanghai"][1]]
        check("Lat" in heads and "Lng" in heads, "Lat / Lng 两列按需添上")
        nh = [r for r in toxlsx.read_name_history(xlsx)
              if r["Unit"] == "上海微波设备研究所" and r["Name"] == "上海仪表铜厂"]
        eq(len(nh), 1, "改过的那一段还在")
        eq(nh[0]["Source"], "仪表工业志 p.412", "核实过的出处写回去了")
        eq(nh[0]["Name EN"], "Copper Works", "英文名不会因原表没这一列就丢掉")

        wb2 = openpyxl.load_workbook(xlsx)["Fact and Comp-Shanghai"]
        h = {c.value: i + 1 for i, c in enumerate(wb2[1]) if c.value}
        vals = [wb2.cell(row=r, column=h["Lat"]).value for r in range(3, wb2.max_row + 1)
                if wb2.cell(row=r, column=1).value == "上海元件五厂"]
        eq(vals, [None], "别家的推定坐标没被顺手写进表里")

        # pull 之后重新盖戳:再 push 不该把它当成未推的改动
        rep = vault.push(xlsx, vdir, geocode_js=geo, log=quiet)
        eq(rep["skipped"], [], "刚 pull 过,不该跳过")
        check("我的札记在此。" in _read(note), "自己写的札记,push 不动它")
        fm = vault.parse_fm(vault.split_note(_read(note))[0])
        eq(fm["城市"], "Shanghai", "改动已在工作簿里,推回来还是它")

        # 真有未推的改动时,push 要拦住
        other = os.path.join(vdir, "上海元件五厂.md")
        _write(other, _read(other).replace("行业: 半导体", "行业: 电子计算机"))
        rep = vault.push(xlsx, vdir, geocode_js=geo, log=quiet)
        eq(rep["skipped"], ["上海元件五厂"], "未推的改动,push 拦住不盖")
        check("行业: 电子计算机" in _read(other), "拦住之后,库里的改动还在")
        rep = vault.push(xlsx, vdir, geocode_js=geo, force=True, log=quiet)
        eq(rep["skipped"], [], "--force 才照盖")
        check("行业: 半导体" in _read(other), "--force 之后以工作簿为准")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_book():
    """现成的转换稿:换个编码、换座城、没有页码锚点,照样走得通。"""
    print("现成的转换稿")
    import openpyxl
    src = os.path.join(HERE, "fixture", "北京转换稿-gb18030.md")

    text, enc = bookmd.read_text(src)
    eq(enc, "gb18030", "认出 GB18030,不是硬按 UTF-8 读")
    check("北京电子管厂" in text, "汉字没读成乱码")

    wrapped, share = bookmd.hard_wrapped(text)
    check(wrapped and share > 0.3, "认出照原书行宽硬断的稿子")
    check("北京市半导体\n器件研究所" in text, "厂名确实被断成了两截")
    flowed = bookmd.reflow_soft(text)
    check("北京市半导体器件研究所" in flowed, "接回段落之后厂名完整")
    got = EX.unit_names("北京市半导体\n器件研究所")
    check("北京市半导体器件研究所" not in got, "不接回就认不出整个厂名(所以才要接)")
    check(all("\n" not in n for n in got), "厂名里决不夹换行")

    picks = bookmd.detect_page_marks(flowed)
    eq(picks[0]["name"], "第N页", "认出「第N页」这种写法")
    check(picks[0]["ok"], "页码递增,像页码")
    normed, how, n = bookmd.normalize_page_marks(flowed)
    eq(how, "第N页", "采用它")
    eq(n, 3, "三处")
    check("<!-- p.55 -->" in normed and "<!-- p.57 -->" in normed, "归一成本工具的写法")

    # 脚注号不是页码 —— 这是「递增」这条判据要挡住的
    foot = "\n".join(["正文一。", "[1]", "正文二。", "[2]", "正文三。", "[1]",
                      "正文四。", "[3]", "正文五。", "[1]", "正文六。"])
    cands = [c for c in bookmd.detect_page_marks(foot) if c["ok"]]
    eq(cands, [], "[1][2][1] 这类脚注号没被当成页码")

    known = toxlsx.merge_known(os.path.join(REPO, "CN_Electronic_Industry.xlsx"),
                               os.path.join(REPO, "src", "geocode.js"))
    res = EX.extract(normed, book="北京工业志·电子志", known=known, city="Beijing")
    by = {r["Unit"]: r for r in res["units"]}
    eq(sorted(by), sorted(["北京电子管厂", "北京半导体器件二厂", "北京市半导体器件研究所"]),
       "三家专条单位")
    eq(by["北京电子管厂"]["City"], "Beijing", "City 列跟着 --city 走")
    eq(by["北京电子管厂"]["Add."], "酒仙桥路2号", "门牌")
    eq(by["北京电子管厂"]["staff"], 10286.0, "职工总数")
    eq(by["北京电子管厂"]["Source"], "北京工业志·电子志·p.55", "出处回注到页")
    eq(by["北京市半导体器件研究所"]["district"], "西城", "北京的区名也认得")
    # 动词照原文录:「划出组建」是分立,写成「合并」就成了另一回事
    check("划出组建" in by["北京半导体器件二厂"]["Founder"], "沿革里的动词照原文,不改字")

    # 没有页码时,出处退到篇章节
    nopage = re.sub(r"<!-- p\.\d+ -->", "", normed)
    res2 = EX.extract(nopage, book="北京工业志·电子志", known=known, city="Beijing")
    src2 = {r["Unit"]: r["Source"] for r in res2["units"]}
    check(src2["北京电子管厂"].startswith("北京工业志·电子志·"), "退到篇章节仍带书名")
    check("p.0" not in "".join(src2.values()), "决不写出 p.0 这种假页码")

    tmp = tempfile.mkdtemp(prefix="gaz-book-")
    try:
        out = os.path.join(tmp, "北京.xlsx")
        bookmd.write_xlsx(out, res, city="Beijing", book="北京工业志·电子志",
                          log=lambda *a: None)
        wb = openpyxl.load_workbook(out)
        eq(wb.sheetnames, ["Fact and Comp-Beijing", "Semi-Product", "Comp-Product",
                           "Name-History", "待核"], "五张表")
        ws = wb["Fact and Comp-Beijing"]
        eq([c.value for c in ws[1]][:8],
           [None, "Industry", "Product", "Start Date", "End Date", "Founder", "City", "Add."],
           "第一行表头与原表一致(A1 照原表留空)")
        eq(ws.cell(row=2, column=9).value, "职工总数", "第二行是统计块的表头")
        eq(ws.cell(row=3, column=4).value, 19561000, "日期写成八位整数")
        rv = wb["待核"]
        eq(rv.cell(row=1, column=11).value, "据以立论的原文", "待核表最后一列是原文")
        check(rv.max_row == len(res["units"]) + 1, "待核表一家一行")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flat_heads():
    """别处转来的稿子:篇章节全压成 `##`,而且一个页码都没有。

    《北京工业志·电子志》2001 第三章就是这样。层级若只数井号,「第三章」
    「第一节」会被「一、」顶掉,而这书没有页码,出处全靠这条路径 —— 只剩
    「一、电子管计算机」等于没说,哪一章的一、都长这样。"""
    print("压平的标题 / 没有页码的书")
    text, enc = bookmd.read_text(os.path.join(HERE, "fixture", "北京-压平标题.md"))

    check(not bookmd.detect_page_marks(text),
          "认不出页码(这书本来就没有),不硬凑")

    blocks = EX.read_blocks(text)
    deep = [b for b in blocks if "晶体管" in "·".join(b["heads"])]
    check(bool(deep), "找得到「二、晶体管计算机」底下的正文")
    eq(deep[0]["heads"],
       ["第三章 电子计算机", "第一节 数字计算机", "二、晶体管计算机"],
       "三级标题同为 `##`,仍按字面认出章 → 节 → 一、")

    first = [b for b in blocks if "地区" in b["text"]][0]
    eq(first["heads"], ["第三章 电子计算机"], "概述段只归到章,不蹭下面的节")

    src_ = EX.make_source("北京工业志·电子志", None, "·".join(deep[0]["heads"]))
    for want in ("第三章", "第一节", "二、"):
        check(want in src_, "没页码时出处带上「%s」这一级" % want)

    res = EX.extract(text, book="北京工业志·电子志", city="Beijing", min_mentions=1)
    names = {r["Unit"] for r in res["units"]}
    check("北京计算机一厂" in names, "「北京计算 机一厂」中间的空格已去掉,厂名认全")
    check("机一厂" not in names, "没有截出「机一厂」这种鬼名字")
    check("国营738厂" in names, "「交由国营738厂试制」认得出国营738厂")


def main():
    for fn in (test_dates, test_names, test_pipeline, test_vault,
               test_book, test_flat_heads):
        fn()
    print()
    if FAILED:
        print("%d 项没通过:" % len(FAILED))
        for f in FAILED:
            print("   -", f)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
