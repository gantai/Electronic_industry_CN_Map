#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gaz —— 把一本地方志变成这张地图上的数据。

    gaz check                     看看本机装了什么、缺什么
    gaz ocr    上海电子工业志.pdf   扫描件 → 逐页文本(可断可续)
    gaz md     --slug 上海电子工业志 逐页文本 → 带页码锚点的 Markdown
    gaz extract --slug ...         Markdown → 四张待核 TSV
    gaz notes  --slug ...          待核记录 → Obsidian 笔记
    gaz push   --vault ~/库/地图    工作簿 → 库,全部厂所各一则,字段在 frontmatter
    gaz pull   --vault ~/库/地图    库 → 工作簿,把你改过的字段写回原行
    gaz geocode --slug ...         新单位 → src/geocode.js 的落点条目草稿
    gaz xlsx   --slug ...          核过的行 → 追加进 CN_Electronic_Industry.xlsx
    gaz run    上海电子工业志.pdf   前四步一气跑完,停在待核这一步

一切成果落在 `--work`(默认 gaz-work/<slug>/)底下:

    pages/       逐页文本,断点续跑靠它
    <slug>.md    转好的 Markdown(丢进 Obsidian 库里就能读)
    review/      四张 TSV,`keep` 列改成 y 的行才准进工作簿
    vault/       每单位一则笔记 + 一则索引
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gazetteer import (cndate, extract as EX, notes as NOTES, ocr as OCR,  # noqa: E402
                       tomd, toxlsx, tsvio, vault as VAULT)

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
             "Research Insti", "Factory", "Time", "Personnel", "Remark", "evidence"]
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
    rows, langs = OCR.check()
    print("本机环境:\n")
    for name, ok, how, why in rows:
        print("  [%s] %-30s %s" % ("✓" if ok else " ", name, why))
        if not ok:
            print("       装法:%s" % how)
    if langs:
        print("\n  tesseract 已装的中文语言包:%s" % langs)
    elif any(r[0].startswith("Tesseract") and r[1] for r in rows):
        print("\n  注意:tesseract 装了,但没找到 chi_sim / chi_tra 语言包,识别不了中文。")
    have_ocr = any(r[0] in ("PaddleOCR", "Tesseract") and r[1] for r in rows)
    print("\n结论:%s" % ("OCR 可用。" if have_ocr else
                        "还没有 OCR 引擎;若 PDF 自带文本层,`gaz ocr --engine text` 仍可直接取字。"))
    return 0


def cmd_ocr(args):
    slug = args.slug or os.path.splitext(os.path.basename(args.src))[0]
    wd = workdir(args, slug)
    os.makedirs(wd, exist_ok=True)
    OCR.run(args.src, wd, engine=args.engine, dpi=args.dpi, first=args.first,
            last=args.last, force=args.force, keep_images=args.keep_images, lang=args.lang)
    print("下一步:gaz md --slug %s" % slug)
    return 0


def cmd_md(args):
    wd = workdir(args)
    pages = OCR.load_pages(wd)
    if not pages:
        sys.exit("%s/pages/ 里没有页文本,先跑 gaz ocr" % wd)
    meta = {}
    mp = os.path.join(wd, "meta.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
    fixes = tomd.load_fixes(args.fixes)
    if args.show_furniture:
        print("判为书眉书脚、将被删去的行:")
        for l in tomd.furniture_report(pages):
            print("   ", l)
        return 0
    md, ledger = tomd.build(pages, args.title or args.slug, meta=meta, fixes=fixes,
                            keep_furniture=args.keep_furniture)
    out = args.out or os.path.join(wd, args.slug + ".md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    if ledger:
        lp = os.path.splitext(out)[0] + ".fixes.tsv"
        with open(lp, "w", encoding="utf-8") as f:
            f.write("page\t原字\t改作\t次数\n")
            for p, a, b, n in ledger:
                f.write("%s\t%s\t%s\t%s\n" % (p, a, b, n))
        print("字形订正 %d 处,逐条记在 %s" % (len(ledger), os.path.basename(lp)))
    print("%d 页 → %s（%d 字）" % (len(pages), out, len(md)))
    print("下一步:gaz extract --slug %s" % args.slug)
    return 0


def cmd_extract(args):
    wd = workdir(args)
    md_path = args.md or os.path.join(wd, args.slug + ".md")
    if not os.path.exists(md_path):
        sys.exit("找不到 %s,先跑 gaz md" % md_path)
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
    wd = workdir(args)
    rd = review_dir(wd)
    bundle = {}
    for tag, fn in (("units", "units.tsv"), ("semi", "semi.tsv"),
                    ("comp", "comp.tsv"), ("names", "names.tsv")):
        p = os.path.join(rd, fn)
        bundle[tag] = tsvio.kept(tsvio.read(p)) if os.path.exists(p) else []
    total = sum(len(v) for v in bundle.values())
    if not total:
        print("四张 TSV 里没有一行写着 keep=y —— 什么也没做。")
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
    slug = args.slug or os.path.splitext(os.path.basename(args.src))[0]
    args.slug = slug
    cmd_ocr(args)
    args.out = None
    cmd_md(args)
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

    p = sub.add_parser("ocr", help="扫描件 → 逐页文本", parents=[common])
    p.add_argument("src", help="PDF 文件,或装着页图的目录")
    p.add_argument("--engine", default="auto",
                   choices=["auto", "text", "paddle", "tesseract"],
                   help="auto=先取文本层,没有再 OCR")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--last", type=int)
    p.add_argument("--force", action="store_true", help="已识别过的页也重做")
    p.add_argument("--keep-images", action="store_true", help="留下渲染出来的页图")
    p.add_argument("--lang", default="ch", help="PaddleOCR 语种(ch/chinese_cht)")
    p.set_defaults(func=cmd_ocr)

    p = sub.add_parser("md", help="逐页文本 → Markdown", parents=[common])
    p.add_argument("--out")
    p.add_argument("--title")
    p.add_argument("--fixes", help="自备字形订正表(TSV:错<TAB>对)")
    p.add_argument("--keep-furniture", action="store_true", help="不删书眉书脚")
    p.add_argument("--show-furniture", action="store_true", help="只列出将被删的版式行")
    p.set_defaults(func=cmd_md)

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

    p = sub.add_parser("xlsx", help="keep=y 的行 → 追加进工作簿", parents=[common])
    p.add_argument("--allow-dup", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--book")
    p.set_defaults(func=cmd_xlsx)

    p = sub.add_parser("run", help="ocr → md → extract → notes 一气跑完", parents=[common])
    p.add_argument("src")
    p.add_argument("--engine", default="auto", choices=["auto", "text", "paddle", "tesseract"])
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--last", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--keep-images", action="store_true")
    p.add_argument("--lang", default="ch")
    p.add_argument("--title")
    p.add_argument("--fixes")
    p.add_argument("--keep-furniture", action="store_true")
    p.add_argument("--show-furniture", action="store_true")
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
