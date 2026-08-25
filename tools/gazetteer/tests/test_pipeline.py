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
    # 志书讲协作、讲配套,动词花样比改名多得多。下面这些是《北京工业志·
    # 电子志》第三章跑出来的原样脏名字,111 家里有二十几家是这么来的
    eq(EX.unit_names("1972年，中国科学院自动化研究所与该厂协作研制。"),
       ["中国科学院自动化研究所"], "「自」不再把「自动化」腰斩")
    eq(EX.unit_names("样机交由中国科学院的508所试验。"), ["508所"],
       "「的」是断点,「508所」是名字")
    eq(EX.unit_names("中国科学院半导体研究所研制成功3AG管。"), ["中国科学院半导体研究所"],
       "「科学院」不是「学院」,别从长名里截出个「中国科学院」")
    eq(EX.unit_names("1990年完成了新疆水泥厂的过程控制改造。"), ["新疆水泥厂"], "剥掉「完成了」")
    eq(EX.unit_names("1988年通过对DEC公司微机的仿制。"), ["DEC公司"], "「通过对」两层都剥掉")
    # 承接的那一头是拿机器去用的人家 —— 正是要留的,不是要丢的
    eq(EX.unit_names("该所承接了市旅游汽车公司的调度系统。"), ["市旅游汽车公司"],
       "「承接了」后头切开,用户单位留下来")
    eq(EX.unit_names("四机部6所承接了大庆石油化工总厂的过程控制系统。"),
       ["四机部6所", "大庆石油化工总厂"], "研制方与用户两家都认出来")
    eq(EX.clean_unit_name("北京华海新技术开发公司"), "北京华海新技术开发公司",
       "「开发」不当动词切 —— 它在这儿是名号的一截")
    eq(EX.unit_names("该校电子厂生产微机。"), [], "「该校电子厂」截出来的「校电子厂」不算名字")
    eq(EX.clean_unit_name("第一个通过机电部4所"), "机电部4所", "「通过」后头切开,所名留下")
    eq(EX.clean_unit_name("第一机床厂"), "第一机床厂", "真的「第一…厂」照留")
    eq(EX.unit_names("首钢电子公司（当时名为自动化研究所）开发建成。"),
       ["首钢电子公司", "自动化研究所"], "「自」当连接词剥得,「自动化」剥不得")
    eq(EX.clean_unit_name("6所华胜计算机公司"), "华胜计算机公司", "「6所」是定语,不是名号")
    eq(EX.clean_unit_name("508所"), "508所", "可「508所」本身就是名号,剥不得")
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
        # 核的是名字,名字与据以判断的原文都摆在最左边
        eq(rv.cell(row=1, column=2).value, "单位", "待核表第二列就是单位名")
        eq(rv.cell(row=1, column=3).value, "别名", "别名紧挨着正名 —— 核的是名字")
        eq(rv.cell(row=1, column=6).value, "据以立论的原文", "原文也在近处,不用横拉")
        check(rv.max_row == len(res["units"]) + 1, "待核表一家一行")

        # 核过再读回来:「取否」写 y 的才算数,名字改成一样的并作一行
        rv.cell(row=2, column=1).value = "y"
        rv.cell(row=3, column=1).value = "y"
        rv.cell(row=2, column=2).value = "上海无线电十九厂"
        rv.cell(row=3, column=2).value = "上海无线电十九厂"
        rv.cell(row=4, column=1).value = ""
        wb.save(out)
        bundle, city2, seen = bookmd.read_review(out)
        eq(city2, "Beijing", "城市从「Fact and Comp-北京」这类表名上认")
        eq(len(bundle["units"]), 1, "两行改成同一个名字,并作一家")
        eq(seen["merged"], 1, "并了几行要报出来")
        eq(bundle["units"][0]["Unit"], "上海无线电十九厂", "并成的那一家用核过的名字")
        check("；" in bundle["units"][0]["Source"], "两处出处都留着")
        check(all(not r.get("evidence") for r in bundle["units"]), "原文只是核对用的,不进表")
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


def test_fixes():
    """字形订正表:转换稿认错的字,一本书一张表。"""
    print("字形订正")
    tmp = tempfile.mkdtemp(prefix="gaz-fix-")
    try:
        tsv = os.path.join(tmp, "fixes.tsv")
        _write(tsv, "# 《北京工业志·电子志》2001\n"
                    "安做无线电厂\t安徽无线电厂\n"
                    "莫须有厂\t查无此厂\n")
        fixes = bookmd.load_fixes(tsv)
        eq(len(fixes), 2, "注解行不算一条")
        # 汉字之间的制表符是分栏用的,不能跟空格一起吃掉,不然两列并成一列
        eq(fixes[0], ("安做无线电厂", "安徽无线电厂"), "两列各归各的")
        text, ledger = bookmd.apply_fixes("由四机部6所、安做无线电厂联合研制。", fixes)
        check("安徽无线电厂" in text, "认错的字改了回来")
        eq([n for _a, _b, n in ledger], [1, 0], "每条改了几处都记着")
        check(bookmd.load_fixes(None) == [], "没给表就是没有,不报错")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_users():
    """用机的人家:记在整机的「用户」一列,不混进研制单位。

    先前一律记进 Factory,站点便据以推定「协作」—— 水泥厂成了计算机的共同
    研制单位。用户要留(机器去了哪儿,正是计算机怎么用开的),但不能算研制方。"""
    print("用户单位")
    md = ("## 一、控制机\n\n"
          "1988年，四机部6所承接了大庆石油化工总厂的过程控制系统，研制成功DJS-186小型计算机。\n"
          "1979年，北京控制机厂与北京市计算机技术研究所联合研制成功DJS-130小型计算机。\n")
    res = EX.extract(md, book="北京工业志·电子志", city="Beijing", min_mentions=1)
    by = {c["Product"]: c for c in res["comp"]}
    check("DJS-186小型计算机" in by, "承接工程那一台也记下来了")
    u = by["DJS-186小型计算机"]
    eq(u.get("用户"), "大庆石油化工总厂", "承接的那一头记进「用户」")
    check("大庆" not in u.get("Factory", ""), "决不混进研制单位 —— 否则要画成协作")
    check("四机部6所" in u.get("Factory", ""), "研制方还在原处")
    v = by["DJS-130小型计算机"]
    eq(v.get("用户", ""), "", "真的协作研制,没有用户")
    check("北京市计算机技术研究所" in (v.get("Research Insti", "") + v.get("Factory", "")),
          "真的协作单位照旧记下,协作连线不受影响")


def test_rename_subject():
    """一句话点到好几家时,「改名为」说的是主语那一家。"""
    print("改的是谁的名")
    md = ("## 一、控制机\n\n"
          "1979年，北京控制机厂为兰州炼油厂研制成功过程控制系统，同年改名为北京自动化设备厂。\n"
          "1980年，北京电器科学研究院参加该项目的设计。\n")
    res = EX.extract(md, book="试", city="Beijing", min_mentions=1)
    got = [(n["Unit"], n["Name"]) for n in res["names"]]
    eq(got, [("北京控制机厂", "北京自动化设备厂")], "只有主语那一家改了名")
    # 志书行文主语在前,「为兰州炼油厂」夹在主语与动词之间 —— 认第一家,不认最后一家
    check(EX.renames_this("北京控制机厂为兰州炼油厂研制系统，同年改名为甲厂。", 22, "北京控制机厂"),
          "主语那一家认得出")
    check(not EX.renames_this("北京控制机厂为兰州炼油厂研制系统，同年改名为甲厂。", 22, "兰州炼油厂"),
          "顺带提到的用户不算")
    check(EX.renames_this("该厂1966年改名为上海无线电十九厂。", 8, "上海元件十四厂"),
          "前头一家也没点到,那就是它")


def test_models():
    """型号常是句子的主语,从动词后头取不着。

    「104机的仿制与103机同时进行」—— find_products 一律从「试制/研制」之后取,
    这一句一台也取不着。按型号的样子再扫一遍,宁滥勿缺:漏掉一台就永远没有了,
    多认一个错的,核对时一眼划掉。"""
    print("型号")
    eq(EX.find_models("104机的仿制与103机同时进行。"), ["104机", "103机"], "主语位置上的型号")
    eq(EX.find_models("该机共有机柜32个，字长39位，内存4K，共生产38台。"), [],
       "「32个」「39位」「38台」都不是型号")
    eq(EX.find_models("其性能指标超过GB1962-82《声频功率放大器》的要求。"), [],
       "GB 开头是国标号,从来不是产品")
    eq(EX.model_key("103型通用数字计算机"), EX.model_key("103机"), "同一台机器,钥匙相同")
    check(EX.model_key("DJS-130小型计算机") != EX.model_key("DJS2"), "不同型号,钥匙不同")

    md = ("## 第三章 电子计算机\n\n## 一、电子管计算机\n\n"
          "1958年，中国科学院计算技术研究所仿M-3试制103型通用数字计算机。\n"
          "104机的仿制与103机同时进行。104机比103机大得多，共有机柜32个。\n")
    res = EX.extract(md, book="北京工业志·电子志", city="Beijing", min_mentions=1)
    prod = {c["Product"] for c in res["comp"]}
    check("104机" in prod, "没人说谁造的,也照样进产品名录")
    check(not any(EX.model_key(p) == "103" and p != "103型通用数字计算机" for p in prod),
          "「103机」与「103型通用数字计算机」是一台,不重复登记")
    orphan = [c for c in res["comp"] if c["Product"] == "104机"][0]
    eq(orphan.get("Factory", ""), "", "研制单位空着就是空着,不硬派给谁")
    check("未详" in orphan["Remark"], "备注里写明研制单位未详")
    check(orphan["Remark"].endswith("一、电子管计算机"), "出处照旧回注到篇章节")


def test_output():
    """产量:「至1960年,共生产38台」。动词得在数字前头,不然满篇都是产量。"""
    print("产量")
    eq(EX.find_output("至1960年，共生产38台。")[0], 38, "共生产38台")
    eq(EX.find_output("1988年，年产微机1.2万台。")[0], 12000, "「1.2万台」折成个位")
    eq(EX.find_output("全机共用800多只电子管。")[0], 0, "电子管的只数不是产量")
    eq(EX.find_output("配套外部设备有磁鼓4台；磁带机5台。")[0], 0, "配套设备的台数不是产量")
    eq(EX.find_output("机房占地面积约40平方米。")[0], 0, "平方米不是产量")
    eq(EX.find_output("共生产12万只。")[0], 120000, "器件论只,整机论台,都要认")
    eq(EX.find_output("共生产集成电路120万块。")[0], 1200000, "集成电路论块")

    # 器件也分研制与生产:半导体所研制、元件厂投产。原表只有一列 Factory,
    # 研究所便也写作了厂
    md4 = ("## 第二章 半导体器件\n\n## 一、晶体管\n\n"
           "1965年，中国科学院半导体研究所研制成功3AG型锗晶体管。\n"
           "1968年，上海元件五厂投产3DG型硅晶体管，共生产12万只。\n")
    r4 = EX.extract(md4, book="试", city="Shanghai", min_mentions=1)
    by4 = {c["Product"]: c for c in r4["semi"]}
    eq(by4["3AG型锗晶体管"].get("Research Insti"), "中国科学院半导体研究所", "研究所记进研制单位")
    eq(by4["3AG型锗晶体管"].get("Factory", ""), "", "研究所不写作厂")
    eq(by4["3DG型硅晶体管"].get("Factory"), "上海元件五厂", "厂还是记进生产单位")
    eq(by4["3DG型硅晶体管"].get("产量"), "120000", "12万只")
    check(all(c["Product"] not in ("3AG型锗晶体管", "3DG型硅晶体管") for c in r4["comp"]),
          "半导体器件不该混进整机表 —— 哪怕这一章标题里带「电子」")

    # 产量常与型号隔着一两句,主语是「该机」或干脆省略
    md = ("## 第三章 电子计算机\n\n## 一、电子管计算机\n\n"
          "1958年，中国科学院计算技术研究所仿M-3试制103型通用数字计算机。"
          "该机共有三大机柜。至1960年，共生产38台。\n")
    res = EX.extract(md, book="北京工业志·电子志", city="Beijing", min_mentions=1)
    by = {c["Product"]: c for c in res["comp"]}
    eq(by["103型通用数字计算机"]["产量"], "38", "隔了两句也认得回来")
    check("共生产38台" in by["103型通用数字计算机"]["Remark"], "备注里留着原话,好核对")
    # 同一段里有两台机器,产量归产量前头最后点到的那一台 —— M-3 是仿的对象,不是它
    eq(by.get("M-3", {}).get("产量", ""), "", "一段两台机器,产量不派给另一台")


def test_edit_in_place():
    """核对是改字,不只是打勾:改过的字要照改过的样子读回来。"""
    print("直接改字")
    import datetime
    eq(bookmd.date_cell("1958"), "19580000", "只写年份,补成八位")
    eq(bookmd.date_cell("195803"), "19580300", "写到月,补成八位")
    eq(bookmd.date_cell("1958年3月"), "19580300", "中文写法照样认")
    eq(bookmd.date_cell(datetime.datetime(1958, 3, 1)), "19580301", "Excel 存成日期格也认")
    eq(bookmd.date_cell("待查"), "待查", "认不出就原样留着,不猜")

    tmp = tempfile.mkdtemp(prefix="gaz-edit-")
    try:
        import openpyxl
        md, _enc = bookmd.read_text(os.path.join(HERE, "fixture", "北京-压平标题.md"))
        res = EX.extract(md, book="试", city="Beijing", min_mentions=1)
        x = os.path.join(tmp, "核.xlsx")
        bookmd.write_xlsx(x, res, city="Beijing", log=lambda *a: None)

        wb = openpyxl.load_workbook(x)
        rv = wb["待核"]
        head = [c.value for c in rv[1]]
        rv.cell(row=2, column=1).value = "y"
        rv.cell(row=2, column=head.index("单位") + 1).value = "安徽无线电厂"
        rv.cell(row=2, column=head.index("行业") + 1).value = "半导体"
        rv.cell(row=2, column=head.index("始建") + 1).value = 1958
        wb.save(x)

        bundle, city, seen = bookmd.read_review(x)
        eq(len(bundle["units"]), 1, "只取点了头的那一行")
        u = bundle["units"][0]
        eq(u["Unit"], "安徽无线电厂", "改过的厂名照改过的读回来")
        eq(u["Industry"], "半导体", "改过的行业照改过的读回来")
        eq(u["Start Date"], "19580000", "手填的年份补成八位,不会写成 1958")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_aliases():
    """一家单位、一台机器同时有好几个名号,不必挑一个 —— 全留着,全显示。"""
    print("别名")
    A = EX.find_aliases
    eq(A("中国科学院计算技术研究所（简称中科院计算所）成立。", "中国科学院计算技术研究所"),
       ["中科院计算所"], "「简称」后头那个")
    eq(A("仿M-3试制103型通用数字计算机（亦称DJS-1）。", "103型通用数字计算机"),
       ["DJS-1"], "「亦称」后头那个")
    eq(A("华北计算技术研究所（四机部15所）和哈军工联合研制。", "华北计算技术研究所"),
       ["四机部15所"], "没有「简称」二字,紧跟着的括号里也认")
    eq(A("北京崇文电子仪器厂（北京计算机五厂前身）。", "北京崇文电子仪器厂"),
       [], "「…前身」是注解,不是别名")
    eq(A("甲厂与乙厂协作，乙厂简称乙。", "甲厂"), [], "别名只跟紧挨着的正名走")

    # 别名与沿革是两回事:「四机部15所」是同时并行的另一个名号,「后改名为…」
    # 说的是后来改叫什么 —— 那有年份可系,归名称沿革表,不该混进别名
    who = "北京崇文电子仪器厂"
    for paren in ("后改名为北京计算机五厂", "改名为北京计算机五厂",
                  "1985年改名为北京计算机五厂", "后称北京计算机五厂",
                  "今北京计算机五厂", "原北京无线电三厂", "北京计算机五厂前身", "兼营"):
        eq(A("%s（%s）研制。" % (who, paren), who), [],
           "「%s」是沿革或注解,不是别名" % paren)

    # 改名那一年,取紧挨着动词的那个 —— 不是整句的年份
    md3 = ("## 一、控制机\n\n"
           "1965年，北京崇文电子仪器厂（1985年改名为北京计算机五厂）研制成功107机。\n")
    r3 = EX.extract(md3, book="试", city="Beijing", min_mentions=1)
    eq([(n["Unit"], n["Name"], n["From"]) for n in r3["names"]],
       [("北京崇文电子仪器厂", "北京计算机五厂", "19850000")],
       "改名记在1985年,不是造机器的1965年")
    check(not any(u.get("别名") for u in r3["units"]), "这一条不进别名列")

    md = ("## 一、电子管计算机\n\n"
          "1956年，中国科学院计算技术研究所（简称中科院计算所）仿M-3试制"
          "103型通用数字计算机（亦称DJS-1）。\n")
    res = EX.extract(md, book="试", city="Beijing", min_mentions=1)
    by = {u["Unit"]: u for u in res["units"]}
    eq(by["中国科学院计算技术研究所"]["别名"], "中科院计算所", "单位的别名记在自己名下")
    eq({c["Product"]: c["别名"] for c in res["comp"]}.get("103型通用数字计算机"),
       "DJS-1", "机器的别名记在机器名下")

    # 并作一行时,被并掉的名字不能就这么没了
    rows = [{"Unit": "华北计算技术研究所", "别名": "四机部15所", "Source": "甲"},
            {"Unit": "华北计算技术研究所", "别名": "电子部15所、电子部第15所", "Source": "乙"}]
    got, n = bookmd.merge_by_name(rows)
    eq(n, 1, "两行并作一行")
    eq(set(got[0]["别名"].split("、")), {"四机部15所", "电子部15所", "电子部第15所"},
       "两边的别名都留着,一边有两个也不丢")

    # 三个别名一路走到工作簿:待核 → read_review → toxlsx → 名录表
    tmp = tempfile.mkdtemp(prefix="gaz-alias-")
    try:
        import openpyxl
        many = "四机部15所、电子部15所、电子部第15所"
        md2 = "## 一、机\n\n1959年，华北计算技术研究所研制成功机器23计算机。\n"
        r2 = EX.extract(md2, book="试", city="Beijing", min_mentions=1)
        bk = os.path.join(tmp, "待核.xlsx")
        bookmd.write_xlsx(bk, r2, city="Beijing", log=lambda *a: None)
        wb = openpyxl.load_workbook(bk)
        rv = wb["待核"]
        hd = [c.value for c in rv[1]]
        for i in range(2, rv.max_row + 1):
            if rv.cell(row=i, column=2).value == "华北计算技术研究所":
                rv.cell(row=i, column=1).value = "y"
                rv.cell(row=i, column=hd.index("别名") + 1).value = many
        wb.save(bk)

        bundle, _city, _seen = bookmd.read_review(bk)
        eq(bundle["units"][0]["别名"], many, "三个别名原样读回来")

        master = os.path.join(tmp, "总表.xlsx")
        shutil.copy(os.path.join(REPO, "CN_Electronic_Industry.xlsx"), master)
        toxlsx.append(master, backup=False, **bundle)
        ws = openpyxl.load_workbook(master)[toxlsx.SHEET_UNITS]
        hh = {c.value: c.column for c in ws[1] if c.value}
        check("别名" in hh, "原表没有「别名」列,按需在表尾添上")
        hit = [ws.cell(row=i, column=hh["别名"]).value
               for i in range(3, ws.max_row + 1)
               if ws.cell(row=i, column=1).value == "华北计算技术研究所"]
        eq(hit, [many], "三个别名一并写进名录表(站点按顿号拆开,逐个都能认)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for fn in (test_dates, test_names, test_pipeline, test_vault,
               test_book, test_flat_heads, test_fixes, test_users,
               test_rename_subject, test_models, test_output,
               test_edit_in_place, test_aliases):
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
