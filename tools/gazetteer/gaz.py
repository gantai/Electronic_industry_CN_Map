#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gaz —— 把一本地方志变成这张地图上的数据。

    gaz check                     看看本机装了什么、缺什么
    gaz inspect 某某志.md          现成的转换稿:看一眼标题、页码、套语
    gaz book    某某志.md          现成的转换稿 → 待核 TSV + 一份本地 Excel
    gaz convert 上海电子工业志.pdf  扫描件 → Markdown(转换交给 zhiconv)
    gaz extract --slug ...         Markdown → 四张待核 TSV
    gaz notes  --slug ...          待核记录 → Obsidian 笔记
    gaz push   --vault ~/库/地图    工作簿 → 库,全部厂所各一则,字段在 frontmatter
    gaz pull   --vault ~/库/地图    库 → 工作簿,把你改过的字段写回原行
    gaz geocode --slug ...         新单位 → src/geocode.js 的落点条目草稿
    gaz xlsx   --slug ...          核过的行 → 追加进 CN_Electronic_Industry.xlsx
    gaz run    上海电子工业志.pdf   convert → extract → notes 一气跑完

一切成果落在 `--work`(默认 gaz-work/<slug>/)底下:

    <slug>.md    转好的 Markdown(丢进 Obsidian 库里就能读)
    review/      四张 TSV,`keep` 列改成 y 的行才准进工作簿
    vault/       每单位一则笔记 + 一则索引
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gazetteer import (bookmd as BOOK, cndate, extract as EX,  # noqa: E402
                       notes as NOTES, toxlsx, tsvio, vault as VAULT)

# 扫描件 → Markdown 不在这个仓里。同一批 PDF 另一个项目也要转,那边把转换
# 单拆成了 zhiconv 一个包,专门伺候这两处;这边再写一份只会更差。
ZHICONV_INSTALL = (
    'pip install "zhiconv @ git+https://github.com/gantai/Historian_Archive_Management"\n'
    '       再装识别引擎:pip install paddleocr "paddlex[ocr]==3.7.2"')
ZHICONV_MISSING = (
    "没装 zhiconv —— 扫描件转 Markdown 归它管:\n"
    "  " + ZHICONV_INSTALL + "\n"
    "已经转好的 .md 不必走这一步,直接 gaz book 某某志.md")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DEFAULT_XLSX = os.path.join(REPO, "CN_Electronic_Industry.xlsx")
DEFAULT_GEOCODE = os.path.join(REPO, "src", "geocode.js")

UNIT_COLS = (["keep", "confidence", "role", "page", "Unit", "Industry", "Product", "Start Date",
              "End Date", "Founder", "City", "Add."]
             + [k for k, _ in EX.STAT_PATTERNS]
             + ["Remark", "Source", "district", "known", "evidence"])
SEMI_COLS = ["keep", "confidence", "page", "Product", "Factory", "Time", "Personnel",
             "Remark", "evidence"]
COMP_COLS = ["keep", "confidence", "page", "Product", "字长", "内存", "Speed（次秒）",
             "Research Insti", "Factory", "用户", "Time", "Personnel", "Remark", "evidence"]
NAME_COLS = ["keep", "confidence", "page", "Unit", "Name", "From", "Remark", "Source", "evidence"]


def workdir(args, slug=None):
    slug = slug or args.slug
    if not slug:
        sys.exit("要给这本志起个名:--slug 上海电子工业志")
    return os.path.abspath(os.path.join(args.work, slug))


def review_dir(wd):
    return os.path.join(wd, "review")


# ---------------------------------------------------------------- 各子命令

def cmd_check(args):
    print("本机环境:\n")
    for mod, what, how in (("openpyxl", "读写 .xlsx", "pip install openpyxl"),
                           ("zhiconv", "扫描件 → Markdown", ZHICONV_INSTALL)):
        try:
            __import__(mod)
            print("  [✓] %-12s %s" % (mod, what))
        except ImportError:
            print("  [ ] %-12s %s\n       装法:%s" % (mod, what, how))
    try:
        from zhiconv import install_hints
        print("\nzhiconv 认得的转换器:\n  %s" % install_hints(".pdf"))
    except ImportError:
        pass
    print("\n已经转好的 .md 不需要 zhiconv,gaz book 直接读。")
    return 0


def cmd_convert(args):
    """扫描件 → Markdown,转换本身交给 zhiconv。"""
    try:
        from zhiconv import to_markdown
    except ImportError:
        sys.exit(ZHICONV_MISSING)
    from pathlib import Path
    slug = args.slug or os.path.splitext(os.path.basename(args.src))[0]
    args.slug = slug
    wd = workdir(args, slug)
    os.makedirs(wd, exist_ok=True)
    out = Path(args.out or os.path.join(wd, slug + ".md"))
    span = (args.first, args.last) if args.last else None
    if span:
        print("只转第 %d–%d 页" % span)
    res = to_markdown(Path(args.src), pages=span, language=args.lang,
                      force=args.force, out=out)
    for w in res.warnings:
        print("  注意:%s" % w)
    if not res.ok or not res.output:
        sys.exit("转不了:%s" % (res.reason or "zhiconv 没说原因"))
    print("%s（%s）" % (res.output, res.converter))
    print("下一步:gaz book %s —— 或 gaz extract --slug %s" % (res.output, slug))
    return 0


def cmd_extract(args):
    wd = workdir(args)
    md_path = args.md or os.path.join(wd, args.slug + ".md")
    if not os.path.exists(md_path):
        sys.exit("找不到 %s,先跑 gaz convert" % md_path)
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    known = toxlsx.merge_known(args.xlsx, DEFAULT_GEOCODE) if os.path.exists(args.xlsx) else {}
    res = EX.extract(md, book=args.book or args.slug, known=known,
                     stats_year=args.stats_year, city=args.city,
                     min_mentions=args.min_mentions, auto_keep=args.auto_keep)
    rd = review_dir(wd)
    tsvio.write(os.path.join(rd, "units.tsv"), res["units"], UNIT_COLS)
    tsvio.write(os.path.join(rd, "semi.tsv"), res["semi"], SEMI_COLS)
    tsvio.write(os.path.join(rd, "comp.tsv"), res["comp"], COMP_COLS)
    tsvio.write(os.path.join(rd, "names.tsv"), res["names"], NAME_COLS)
    fresh = sum(1 for r in res["units"] if not r.get("known"))
    print("抽出:%d 家单位(其中 %d 家尚未入表)、%d 条器件、%d 条整机、%d 段名称沿革"
          % (len(res["units"]), fresh, len(res["semi"]), len(res["comp"]), len(res["names"])))
    print("待核 TSV 在 %s" % rd)
    print("把要的行 keep 改成 y,再跑:gaz notes --slug %s / gaz xlsx --slug %s"
          % (args.slug, args.slug))
    return 0


def cmd_notes(args):
    wd = workdir(args)
    rows = tsvio.read(os.path.join(review_dir(wd), "units.tsv"))
    if not args.all:
        picked = tsvio.kept(rows)
        if not picked:
            print("units.tsv 里还没有 keep=y 的行。先核对,或加 --all 把全部候选都写成笔记。")
            return 1
        rows = picked
    NOTES.write_vault(rows, args.out or os.path.join(wd, "vault"),
                      book=args.book or args.slug,
                      book_note=args.book_note or args.slug)
    return 0


def cmd_inspect(args):
    """先看看这份转换稿长什么样 —— 抽取之前值得花十秒钟。"""
    text, enc = BOOK.read_text(args.md)
    print("编码:%s" % enc)
    BOOK.report(BOOK.inspect(text, args.md))
    return 0


def cmd_book(args):
    """现成的 .md → 待核 TSV + 一份本地 Excel。扫描件请先走 gaz convert。"""
    text, enc = BOOK.read_text(args.md)
    stem = os.path.splitext(os.path.basename(args.md))[0]
    book = args.book or stem
    slug = args.slug or stem
    print("读入 %s（%s,%d 字）" % (os.path.basename(args.md), enc, len(text)))

    fixes = BOOK.load_fixes(args.fixes)
    if fixes:
        text, ledger = BOOK.apply_fixes(text, fixes)
        hit = [(a, b, n) for a, b, n in ledger if n]
        miss = [a for a, _b, n in ledger if not n]
        print("字形订正 %d 条,改了 %d 处%s"
              % (len(fixes), sum(n for _a, _b, n in hit),
                 (":" + "、".join("%s→%s×%d" % t for t in hit)) if hit else ""))
        if miss:
            print("  没对上的 %d 条,原文里找不到:%s" % (len(miss), "、".join(miss)))

    wrapped, share = BOOK.hard_wrapped(text)
    if args.reflow == "on" or (args.reflow == "auto" and wrapped):
        text = BOOK.reflow_soft(text)
        print("%.0f%% 的行没收在句读上,已接回段落(--reflow off 可关掉)" % (share * 100))

    text, how, n = BOOK.normalize_page_marks(text, force=args.page_pattern)
    if how:
        print("页码写法「%s」%d 处,已归一成 <!-- p.N -->" % (how, n))
    else:
        print("没认出页码 —— 出处退到篇章节(如「%s·第三章」)" % book)

    wd = workdir(args, slug)
    os.makedirs(wd, exist_ok=True)
    md_path = os.path.join(wd, slug + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text)

    known = toxlsx.merge_known(args.xlsx, DEFAULT_GEOCODE) if os.path.exists(args.xlsx) else {}
    res = EX.extract(text, book=book, known=known, stats_year=args.stats_year,
                     city=args.city, min_mentions=args.min_mentions, auto_keep=args.auto_keep)

    rd = review_dir(wd)
    tsvio.write(os.path.join(rd, "units.tsv"), res["units"], UNIT_COLS)
    tsvio.write(os.path.join(rd, "semi.tsv"), res["semi"], SEMI_COLS)
    tsvio.write(os.path.join(rd, "comp.tsv"), res["comp"], COMP_COLS)
    tsvio.write(os.path.join(rd, "names.tsv"), res["names"], NAME_COLS)

    entries = sum(1 for r in res["units"] if r.get("role") == "专条")
    print("抽出:%d 家单位(%d 家有专条)、%d 条器件、%d 条整机、%d 段名称沿革"
          % (len(res["units"]), entries, len(res["semi"]), len(res["comp"]), len(res["names"])))

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.md)), stem + ".xlsx")
    BOOK.write_xlsx(out, res, city=args.city, book=book, stats_year=args.stats_year)
    print("待核 TSV 另存一份在 %s" % rd)
    print()
    print("接下来:在 Excel 的「待核」表里核名字 —— 原文就在第 5 列。")
    print("  名字认错的当场改;同一家的几个名字改成同一个,追加时会并作一行;")
    print("  要的行「取否」写 y。核完:")
    print('    gaz xlsx --from "%s"' % out)
    return 0


def _vault_dir(args):
    """--vault,或环境变量 GAZ_VAULT。库在你自己的机器上,路径只有你知道。"""
    v = getattr(args, "vault", None) or os.environ.get("GAZ_VAULT")
    if not v:
        sys.exit("要指出库在哪:--vault ~/Obsidian/电子工业/地图,或设个 GAZ_VAULT 环境变量")
    return os.path.expanduser(v)


def cmd_push(args):
    """工作簿 → 库。全部厂所各写一则笔记,字段摆在 frontmatter 里等你改。"""
    VAULT.push(args.xlsx, _vault_dir(args), geocode_js=DEFAULT_GEOCODE, force=args.force)
    print("改完哪则,`gaz pull` 推回工作簿(先 --dry-run 看清单)。")
    return 0


def cmd_pull(args):
    """库 → 工作簿。只改动过的格子,写前先列清单。"""
    rep = VAULT.pull(args.xlsx, _vault_dir(args), dry_run=args.dry_run)
    if rep["units"] and not args.dry_run:
        print("核对无误后:git add -A && git commit -m \"据库中校订更新数据\" && git push")
    return 0


def cmd_geocode(args):
    """新单位的落点条目 —— 照 src/geocode.js 的体例开好格子,坐标留白待填。

    志书只写门牌地址,经纬度得人来定。这里把地址、区名、出处都摆好,
    你查到落点填上 lat / lng,改一下 precision 即可(街段 street / 区级 district)。"""
    wd = workdir(args)
    rows = tsvio.read(os.path.join(review_dir(wd), "units.tsv"))
    rows = rows if args.all else tsvio.kept(rows)
    have = toxlsx.read_places(DEFAULT_GEOCODE)
    out, skipped = [], 0
    for r in rows:
        nm = (r.get("Unit") or "").strip()
        if not nm or nm in have:
            skipped += 1
            continue
        note = "、".join(x for x in [r.get("Add.", ""), r.get("Source", "")] if x)
        out.append('  "%s": { lat: null, lng: null, district: "%s", precision: "city"'
                   '%s },' % (nm, r.get("district", ""),
                              (', note: "%s"' % note.replace('"', "'")) if note else ""))
    if not out:
        print("没有需要新增落点的单位(%d 家已在 PLACES 里)。" % skipped)
        return 0
    path = os.path.join(review_dir(wd), "geocode-stub.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write("/* 由 tools/gazetteer 生成,粘进 src/geocode.js 的 PLACES 里,再补 lat / lng。\n"
                "   坐标未填时站点会把它落在市中心并标「坐标待定位」,不影响其余功能。*/\n")
        f.write("\n".join(out) + "\n")
    print("%d 家新单位的落点条目 → %s" % (len(out), path))
    print("填好 lat / lng 后粘进 src/geocode.js 的 PLACES,precision 改成 street 或 district。")
    return 0


def cmd_xlsx(args):
    if args.from_xlsx:
        bundle, city, seen = BOOK.read_review(args.from_xlsx)
        print("读回 %s%s" % (os.path.basename(args.from_xlsx),
                            ("(%s)" % city) if city else ""))
        if seen.get("merged"):
            print("  核过之后名字改成一样的,%d 行并作一行,出处都留着" % seen["merged"])
        where = "工作簿的「取否」列"
    else:
        rd = review_dir(workdir(args))
        bundle = {}
        for tag, fn in (("units", "units.tsv"), ("semi", "semi.tsv"),
                        ("comp", "comp.tsv"), ("names", "names.tsv")):
            p = os.path.join(rd, fn)
            bundle[tag] = tsvio.kept(tsvio.read(p)) if os.path.exists(p) else []
        where = "四张 TSV 的 keep 列"
    total = sum(len(v) for v in bundle.values())
    if not total:
        print("%s里没有一行写着 y —— 什么也没做。" % where)
        print("这是有意为之:没经你点头的记载,不进工作簿。")
        return 1
    print("将追加:%d 家单位、%d 条器件、%d 条整机、%d 段名称沿革"
          % (len(bundle["units"]), len(bundle["semi"]), len(bundle["comp"]), len(bundle["names"])))
    if args.dry_run:
        for r in bundle["units"]:
            print("   + %s %s %s" % (r.get("Unit"), r.get("Industry", ""),
                                     cndate.fmt(r.get("Start Date", ""))))
        print("(--dry-run,未落笔)")
        return 0
    rep = toxlsx.append(args.xlsx, allow_dup=args.allow_dup, **bundle)
    print("已写入 %s:单位 +%d、器件 +%d、整机 +%d、沿革 +%d"
          % (os.path.basename(args.xlsx), rep["units"], rep["semi"], rep["comp"], rep["names"]))
    if rep["skipped"]:
        print("同名已在表内、跳过 %d 家:%s" % (len(rep["skipped"]), "、".join(rep["skipped"][:8])))
        print("确要重复登记,加 --allow-dup。")
    print("核对无误后:git add -A && git commit -m \"补录 %s\" && git push" % (args.book or args.slug))
    return 0


def cmd_run(args):
    args.out = None
    cmd_convert(args)
    slug = args.slug
    args.md = None
    cmd_extract(args)
    args.all = True
    args.out = None
    cmd_notes(args)
    print("\n到此为止 —— 剩下的活儿只有人能干:")
    print("  1. 翻 %s/review/units.tsv,逐行核对 evidence 那一栏" % workdir(args, slug))
    print("  2. 要的行 keep 改成 y")
    print("  3. gaz xlsx --slug %s" % slug)
    return 0


# ---------------------------------------------------------------- 命令行

def main(argv=None):
    ap = argparse.ArgumentParser(prog="gaz", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default="gaz-work", help="工作目录(默认 gaz-work/)")
    ap.add_argument("--slug", help="这本志的代号,各步骤据以找文件")
    ap.add_argument("--xlsx", default=DEFAULT_XLSX, help="目标工作簿")

    # 这三个放在子命令前后都认。SUPPRESS 是关键:子命令没写的话不留属性,
    # 免得用一个 None 把命令前写好的值盖掉。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--work", default=argparse.SUPPRESS)
    common.add_argument("--slug", default=argparse.SUPPRESS)
    common.add_argument("--xlsx", default=argparse.SUPPRESS)

    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="看看本机装了什么", parents=[common])
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("convert", help="扫描件 → Markdown(交给 zhiconv)", parents=[common])
    p.add_argument("src", help="PDF,或别的 zhiconv 认得的文件")
    p.add_argument("--out", help="转好的 .md 写到哪儿(默认 gaz-work/<slug>/<slug>.md)")
    p.add_argument("--first", type=int, default=1, help="只转其中一段:起页")
    p.add_argument("--last", type=int, help="只转其中一段:止页 —— 一本志几百页,"
                                            "要一章就别转另外二十九章")
    p.add_argument("--lang", default="ch", help="识别语种(ch / chinese_cht)")
    p.add_argument("--force", action="store_true", help="已转过的也重转")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("extract", help="Markdown → 待核 TSV", parents=[common])
    p.add_argument("--md")
    p.add_argument("--book", help="出处里写的书名(默认用 slug)")
    p.add_argument("--city", default="Shanghai")
    p.add_argument("--stats-year", type=int, default=1990, help="统计断面年,与原表一致")
    p.add_argument("--min-mentions", type=int, default=2)
    p.add_argument("--auto-keep", type=float,
                   help="置信高于此值的行直接置 y(不填则一律待核)")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("notes", help="→ Obsidian 笔记", parents=[common])
    p.add_argument("--out")
    p.add_argument("--book")
    p.add_argument("--book-note", help="库中原书笔记的文件名,供 wikilink")
    p.add_argument("--all", action="store_true", help="不问 keep,全部写出")
    p.set_defaults(func=cmd_notes)

    p = sub.add_parser("inspect", help="看一眼现成的 .md 转换稿:标题、页码、套语", parents=[common])
    p.add_argument("md", help="已转好的 Markdown 文件")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("book", help="现成的 .md → 待核 TSV + 一份本地 Excel", parents=[common])
    p.add_argument("md", help="已转好的 Markdown 文件")
    p.add_argument("--out", help="Excel 存到哪(默认与 .md 同目录同名)")
    p.add_argument("--city", default="Shanghai", help="City 列的值,如 Beijing")
    p.add_argument("--book", help="出处里写的书名(默认取文件名)")
    p.add_argument("--stats-year", type=int, default=1990)
    p.add_argument("--min-mentions", type=int, default=2)
    p.add_argument("--auto-keep", type=float)
    p.add_argument("--fixes", help="字形订正表(TSV:错<TAB>对),转换稿认错的字在这儿改")
    p.add_argument("--page-pattern", help="指定页码写法,不用自动认")
    p.add_argument("--reflow", default="auto", choices=["auto", "on", "off"],
                   help="接回硬断的行(默认 auto:看了再定)")
    p.set_defaults(func=cmd_book)

    p = sub.add_parser("push", help="工作簿 → Obsidian 库(全部厂所各一则笔记)", parents=[common])
    p.add_argument("--vault", help="库里放笔记的目录(也可用 GAZ_VAULT 环境变量)")
    p.add_argument("--force", action="store_true", help="库里改过也照盖不误")
    p.set_defaults(func=cmd_push)

    p = sub.add_parser("pull", help="Obsidian 库 → 工作簿(把改过的字段写回)", parents=[common])
    p.add_argument("--vault", help="库里放笔记的目录(也可用 GAZ_VAULT 环境变量)")
    p.add_argument("--dry-run", action="store_true", help="只列清单,不落笔")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("geocode", help="新单位 → src/geocode.js 的落点条目草稿", parents=[common])
    p.add_argument("--all", action="store_true", help="不问 keep,全部列出")
    p.set_defaults(func=cmd_geocode)

    p = sub.add_parser("xlsx", help="取否=y 的行 → 追加进工作簿", parents=[common])
    p.add_argument("--from", dest="from_xlsx", metavar="XLSX",
                   help="读 gaz book 生成的那份工作簿(你核过的),而不是 TSV")
    p.add_argument("--allow-dup", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--book")
    p.set_defaults(func=cmd_xlsx)

    p = sub.add_parser("run", help="convert → extract → notes 一气跑完", parents=[common])
    p.add_argument("src")
    p.add_argument("--out")
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--last", type=int)
    p.add_argument("--lang", default="ch")
    p.add_argument("--force", action="store_true")
    p.add_argument("--book", help="出处里写的书名")
    p.add_argument("--book-note")
    p.add_argument("--city", default="Shanghai")
    p.add_argument("--stats-year", type=int, default=1990)
    p.add_argument("--min-mentions", type=int, default=2)
    p.add_argument("--auto-keep", type=float)
    p.set_defaults(func=cmd_run)

    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
