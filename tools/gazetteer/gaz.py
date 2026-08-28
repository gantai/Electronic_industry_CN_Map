#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gaz —— 把一本地方志变成这张地图上的数据。

    gaz guide   --vault D:\\Archive  两份《流程》:建档与核对、有厂址的章怎么落点
    gaz verify                    手改过工作簿之后验一验(只报,不动手)
    gaz dups                      工作簿里哪些行像是重复的(只报,不动手)
    gaz check                     看看本机装了什么、缺什么
    gaz inspect 某某志.md          现成的转换稿:看一眼标题、页码、套语
    gaz volume  第三章             按名字找稿子跑一本(转换稿目录设 GAZ_DRAFTS)
    gaz book    某某志.md          指名道姓地跑一份
    gaz convert 上海电子工业志.pdf  扫描件 → Markdown(转换交给 zhiconv)
    gaz extract --slug ...         Markdown → 四张待核 TSV
    gaz notes  --slug ...          待核记录 → Obsidian 笔记
    gaz push   --vault <库>/厂所    工作簿 → 库,全部厂所各一则,字段在 frontmatter
    gaz pull   --vault <库>/厂所    库 → 工作簿,把你改过的字段写回原行
    gaz geocode --slug ...         新单位 → src/geocode.js 的落点条目草稿
    gaz xlsx   --slug ...          核过的行 → 追加进 CN_Electronic_Industry.xlsx
    gaz run    上海电子工业志.pdf   convert → extract → notes 一气跑完

没把 gaz 装成命令的话,上面每一行的 `gaz` 都写成 `python tools/gazetteer/gaz.py`
—— 工具打印下一步时会照你实际的敲法写,照抄即可。

一切成果落在 `--work`(默认 gaz-work/<slug>/)底下:

    <slug>.md    转好的 Markdown(丢进 Obsidian 库里就能读)
    review/      四张 TSV,`keep` 列改成 y 的行才准进工作簿
    vault/       每单位一则笔记 + 一则索引
"""

import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gazetteer import (bookmd as BOOK, cndate, extract as EX,  # noqa: E402
                       notes as NOTES, toxlsx, tsvio, vault as VAULT)

def _self():
    """这个脚本在你机器上该怎么敲。

    装成命令了就是 `gaz`,没装就得写全 `python tools/gazetteer/gaz.py` ——
    打印下一步时按实际情况写,免得照抄下来敲不动。"""
    if os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] == "gaz" \
            and not sys.argv[0].endswith(".py"):
        return "gaz"
    try:
        path = os.path.relpath(os.path.abspath(__file__))
    except ValueError:            # Windows 上跨盘符,relpath 会翻脸
        path = os.path.abspath(__file__)
    if path.startswith(".."):
        path = os.path.abspath(__file__)
    return "python %s" % (('"%s"' % path) if " " in path else path)


SELF = _self()

# 扫描件 → Markdown 不在这个仓里。同一批 PDF 另一个项目也要转,那边把转换
# 单拆成了 zhiconv 一个包,专门伺候这两处;这边再写一份只会更差。
ZHICONV_INSTALL = (
    'pip install "zhiconv @ git+https://github.com/gantai/Historian_Archive_Management"\n'
    '       再装识别引擎:pip install paddleocr "paddlex[ocr]==3.7.2"')
ZHICONV_MISSING = (
    "没装 zhiconv —— 扫描件转 Markdown 归它管:\n"
    "  " + ZHICONV_INSTALL + "\n"
    "已经转好的 .md 不必走这一步,直接 " + SELF + " book 某某志.md")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DEFAULT_XLSX = os.path.join(REPO, "CN_Electronic_Industry.xlsx")
DEFAULT_GEOCODE = os.path.join(REPO, "src", "geocode.js")

UNIT_COLS = (["keep", "confidence", "role", "page", "Unit", "别名", "Industry", "Product",
              "Start Date",
              "End Date", "Founder", "City", "Add."]
             + [k for k, _ in EX.STAT_PATTERNS]
             + ["Remark", "Source", "district", "known", "evidence"])
SEMI_COLS = ["keep", "confidence", "page", "Product", "别名", "Research Insti", "Factory",
             "产量", "Time", "Personnel", "Remark", "evidence"]
COMP_COLS = ["keep", "confidence", "page", "Product", "字长", "内存", "Speed（次秒）",
             "Research Insti", "Factory", "用户", "产量", "别名", "Time", "Personnel", "Remark",
             "evidence"]
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
    print("\n已经转好的 .md 不需要 zhiconv,%s book 直接读。" % SELF)
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
    print("下一步:%s book %s —— 或 %s extract --slug %s"
          % (SELF, res.output, SELF, slug))
    return 0


def cmd_extract(args):
    wd = workdir(args)
    md_path = args.md or os.path.join(wd, args.slug + ".md")
    if not os.path.exists(md_path):
        sys.exit("找不到 %s,先跑 %s convert" % (md_path, SELF))
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
    print("把要的行 keep 改成 y,再跑:%s notes --slug %s / %s xlsx --slug %s"
          % (SELF, args.slug, SELF, args.slug))
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


def cmd_dups(args):
    """把工作簿里疑似重复的地方找出来 —— 只报,一个格子也不动。"""
    rep = toxlsx.report_dups(args.xlsx)
    if rep["exact"]:
        print("一模一样的 %d 处 —— 多半是追加了两遍,可以删:" % len(rep["exact"]))
        for sheet, key, rows, who in rep["exact"]:
            print("   %-22s %-26s 行 %s" % (sheet, key[:24], rows))
    if rep["similar"]:
        print("\n像是一回事的 %d 处 —— 得你自己看:" % len(rep["similar"]))
        for sheet, key, rows, who in rep["similar"]:
            print("   %-22s %-10s 行 %-14s %s" % (sheet, key[:10], str(rows), who[:44]))
        print("\n   (「DJS-130」与「DJS-130B」型号内核一样,却是两台机器 —— 别一律并掉)")
    if not rep["exact"] and not rep["similar"]:
        print("没找到重复。")
    return 0


def _w(text):
    """中文字在终端里占两格 —— 拿它对齐,列才不会歪。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


VERIFY_NOTE = {
    "日期": "只知道年份就写 19580000,月日拿零补足",
    "坐标": "Lat/Lng 两个一起填,填了就以你填的为准",
    "出处": "哪一本、哪一页 —— 空着的将来没法回查",
    "名录": "这些名字在厂所表里查无此人。打错字、把动词粘进了名字、"
            "或者这一家本来就没登记 —— 连不上的那条线,地图上什么也看不出来",
}


def cmd_verify(args):
    """手改过工作簿之后验一验 —— 只报,一个格子也不动。"""
    bad = toxlsx.verify(args.xlsx)
    if not bad:
        print("没看出问题。")
        return 0
    by = {}
    for kind, where, why in bad:
        by.setdefault(kind, []).append((where, why))
    print("%d 处可疑:" % len(bad))
    for kind in ("名录", "日期", "坐标", "出处"):
        rows = by.pop(kind, [])
        if not rows:
            continue
        print("\n【%s】%d 处 —— %s" % (kind, len(rows), VERIFY_NOTE.get(kind, "")))
        for where, why in rows[:30]:
            print("   %s%s%s" % (where, " " * max(1, 30 - _w(where)), why))
        if len(rows) > 30:
            print("   …… 还有 %d 处" % (len(rows) - 30))
    return 0


def cmd_guide(args):
    """把两份《流程》写进库里 —— 照着办的那几份,该跟笔记摆在一处。"""
    docs = [("流程.md", "地方志建档流程.md"),
            ("有厂址的章.md", "地方志建档-有厂址的章.md")]
    vault = args.vault or os.environ.get("GAZ_VAULT")
    if not vault:
        for src, _name in docs:
            with open(os.path.join(HERE, src), encoding="utf-8") as f:
                sys.stdout.write(f.read())
            sys.stdout.write("\n\n")
        return 0
    os.makedirs(vault, exist_ok=True)
    for src, name in docs:
        path = os.path.join(HERE, src)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        out = os.path.join(vault, name)
        if os.path.exists(out):
            with open(out, encoding="utf-8") as f:
                old_text = f.read()
            if old_text == text:
                print("已是最新:%s" % name)
                continue
            if not args.force:
                print("！%s 已存在,且与本版不同 —— 你可能在上头写过批注,没动它。"
                      % name)
                print("   确要覆盖:加 --force(先自己留个副本)")
                continue
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("写到 %s" % out)
    return 0


def cmd_inspect(args):
    """先看看这份转换稿长什么样 —— 抽取之前值得花十秒钟。"""
    text, enc = BOOK.read_text(args.md)
    print("编码:%s" % enc)
    BOOK.report(BOOK.inspect(text, args.md))
    return 0


def cmd_volume(args):
    """按关键词找稿子,连订正表一并配好,跑 book —— 每本志一条命令。

    路径、订正表、城市,每回都要重打一遍,打错一处就白跑。这里只记一个
    「转换稿放在哪」(GAZ_DRAFTS),往下按名字找。"""
    root = args.dir or os.environ.get("GAZ_DRAFTS")
    if not root:
        sys.exit("要指出转换稿放在哪:--dir …,或设个环境变量,以后就不必写了:\n"
                 "  Windows  [Environment]::SetEnvironmentVariable("
                 "\"GAZ_DRAFTS\", \"D:\\Coding\\CN_Map\\转换稿\", \"User\")\n"
                 "  其他     export GAZ_DRAFTS=~/转换稿")
    if not os.path.isdir(root):
        sys.exit("找不到目录:%s" % root)
    # 关键词可以写好几截,不必加引号 —— 志书的文件名带空格、带《》,
    # PowerShell 会把它拆成好几个词送进来。几截都在名字里,才算这一份。
    terms = [t for t in args.key if t.strip()]
    shown = " ".join(terms)
    mds = []
    for dirpath, _d, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".md"):
                mds.append(os.path.join(dirpath, fn))
    hits = sorted(p for p in mds if all(t in os.path.basename(p) for t in terms))
    if not hits:
        miss = [t for t in terms
                if not any(t in os.path.basename(p) for p in mds)]
        why = ""
        if miss:
            why = "\n没有一份稿子的名字里带「%s」。" % "」「".join(miss)
            stray = [t for t in miss if re.fullmatch(r"[A-Za-z]+", t)]
            if stray:
                why += ("\n「%s」看着像城市 —— 城市要写成 --city %s,"
                        "不是当关键词写。" % (stray[0], stray[0]))
        elif len(terms) > 1:
            why = "\n这几截分开都有,凑在一起没有 —— 是不是记串了两份稿子?"
        sys.exit("在 %s 底下,%d 份 .md 里没有对上「%s」的。%s"
                 % (root, len(mds), shown, why))
    if len(hits) > 1:
        print("名字里带「%s」的稿子有 %d 份:" % (shown, len(hits)))
        for h in hits:
            print("   " + h)
        sys.exit("关键词说得再准一点。")
    args.md = hits[0]
    print("稿子:%s" % args.md)

    if not args.fixes:
        here = os.path.dirname(args.md)
        stem = os.path.splitext(os.path.basename(args.md))[0]
        cand = sorted(f for f in os.listdir(here) if f.endswith(".fixes.tsv"))
        # 同名的优先,没有就用这一目录里唯一的一份
        same = [f for f in cand if stem.startswith(os.path.splitext(f)[0][:8])
                or os.path.splitext(f)[0][:8] in stem]
        pick = (same or (cand if len(cand) == 1 else []))
        if pick:
            args.fixes = os.path.join(here, pick[0])
    return cmd_book(args)


def cmd_book(args):
    """现成的 .md → 待核 TSV + 一份本地 Excel。扫描件请先走 gaz convert。"""
    text, enc = BOOK.read_text(args.md)
    stem = os.path.splitext(os.path.basename(args.md))[0]
    # 书名默认取《》里那一截:「《北京工业志·电子志》2001 第三章」→「北京工业志·电子志」。
    # 拿整个文件名当书名,出处会写成「…2001 第三章·第三章 电子计算机」,第三章说两遍。
    book = args.book or re.sub(r"^《|》.*$", "", stem) or stem
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
    guess = sum(1 for r in res["comp"] + res["semi"] if "未详" in str(r.get("Remark", "")))
    if guess:
        print("  其中 %d 条没写明研制/生产单位 —— 多半是按型号的样子认出来的,"
              "宁滥勿缺,核对时留意" % guess)

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.md)), stem + ".xlsx")
    BOOK.write_xlsx(out, res, city=args.city, book=book, stats_year=args.stats_year)
    print("待核 TSV 另存一份在 %s" % rd)
    print()
    # 别写第几列 —— 加一列就说错一次。列名不会变
    print("接下来:在 Excel 的「待核」表里核名字,判断的凭据是「据以立论的原文」那一列。")
    print("  名字认错的当场改;同一家的几个名字改成同一个,追加时会并作一行;")
    print("  要的行「取否」写 y。核完:")
    print('    %s xlsx --from "%s"' % (SELF, out))
    return 0


def _vault_dir(args):
    """--vault,或环境变量 GAZ_VAULT。库在你自己的机器上,路径只有你知道。"""
    v = getattr(args, "vault", None) or os.environ.get("GAZ_VAULT")
    if not v:
        sys.exit("要指出库里放笔记的目录 —— 是库里的一个子文件夹,不是库根:\n"
                 "  --vault <你的库>/厂所\n"
                 "或设个环境变量,以后就不必每回写了:\n"
                 "  Windows  [Environment]::SetEnvironmentVariable(\"GAZ_VAULT\", \"<你的库>\\厂所\", \"User\")\n"
                 "  其他     export GAZ_VAULT=<你的库>/厂所")
    return os.path.expanduser(v)


def cmd_push(args):
    """工作簿 → 库。全部厂所各写一则笔记,字段摆在 frontmatter 里等你改。"""
    VAULT.push(args.xlsx, _vault_dir(args), geocode_js=DEFAULT_GEOCODE, force=args.force)
    print("改完哪则,`%s pull` 推回工作簿(先 --dry-run 看清单)。" % SELF)
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
        label = args.book or os.path.splitext(os.path.basename(args.from_xlsx))[0]
    else:
        rd = review_dir(workdir(args))
        bundle = {}
        for tag, fn in (("units", "units.tsv"), ("semi", "semi.tsv"),
                        ("comp", "comp.tsv"), ("names", "names.tsv")):
            p = os.path.join(rd, fn)
            bundle[tag] = tsvio.kept(tsvio.read(p)) if os.path.exists(p) else []
        where = "四张 TSV 的 keep 列"
        seen = {}
        label = args.book or args.slug
    total = sum(len(v) for v in bundle.values())
    if not total:
        print("%s里没有一行写着 y —— 什么也没做。" % where)
        print("这是有意为之:没经你点头的记载,不进工作簿。")
        return 1
    # 分母要写出来 —— 「103/103」一眼看得出是整列都点了头,「12/103」才是核过的样子
    tally = "、".join(
        "%d/%d %s" % (len(bundle[k]), seen[k], zh) if k in seen else "%d %s" % (len(bundle[k]), zh)
        for k, zh in (("units", "家单位"), ("semi", "条器件"),
                      ("comp", "条整机"), ("names", "段名称沿革")))
    print("将追加:%s" % tally)
    if seen.get("units") and len(bundle["units"]) == seen["units"] and seen["units"] > 20:
        print("  注意:%d 家一家不落全点了头。核名字本是要挑的,整列填 y 与不核无异。"
              % seen["units"])
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
        # 跳过的分两类:单位按名字(连别名一起)比,产品与沿革按整条记录比
        units_hit = [x for x in rep["skipped"] if not x.startswith(("semi:", "comp:", "names:"))]
        rows_hit = [x for x in rep["skipped"] if x.startswith(("semi:", "comp:", "names:"))]
        if units_hit:
            print("表内已有、跳过 %d 家:%s" % (len(units_hit), "、".join(units_hit[:6])))
        if rows_hit:
            print("表内已有、跳过 %d 条记录:%s" % (len(rows_hit), "、".join(rows_hit[:6])))
        print("确要重复登记,加 --allow-dup。")
    if rep.get("near"):
        print("\n型号内核相同、写法不同的 %d 条 —— 已经收下了,但值得看一眼:" % len(rep["near"]))
        for new_nm, old_nm in rep["near"][:10]:
            print("   新收「%s」 ↔ 表内「%s」" % (new_nm, old_nm))
        print("   同一台机器就把一条并掉,另一个名字填进「别名」列;")
        print("   真是两台(如 DJS-130 与 DJS-130B)就不用管。gaz dups 随时再查。")
    # 一行一条 —— PowerShell 5.1 不认 &&
    print("核对无误后提交:")
    print("  git add -A")
    print('  git commit -m "补录 %s"' % label)
    print("  git push")
    if args.from_xlsx:
        print("追错了要退回:git checkout -- %s(或用上面那份备份覆盖回去)"
              % os.path.basename(args.xlsx))
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
    print("  3. %s xlsx --slug %s" % (SELF, slug))
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

    p = sub.add_parser("verify", help="手改过工作簿之后验一验(只报,不动手)",
                       parents=[common])
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("dups", help="找出工作簿里疑似重复的行(只报,不动手)", parents=[common])
    p.set_defaults(func=cmd_dups)

    p = sub.add_parser("guide", help="《流程》—— 打印出来,或写进 Obsidian 库", parents=[common])
    p.add_argument("--vault", help="写进这个目录(也可设 GAZ_VAULT);不给就打印到屏幕")
    p.add_argument("--force", action="store_true", help="已存在且不同也照覆盖")
    p.set_defaults(func=cmd_guide)

    p = sub.add_parser("inspect", help="看一眼现成的 .md 转换稿:标题、页码、套语", parents=[common])
    p.add_argument("md", help="已转好的 Markdown 文件")
    p.set_defaults(func=cmd_inspect)

    def _book_opts(p):
        p.add_argument("--out", help="Excel 存到哪(默认与 .md 同目录同名)")
        p.add_argument("--city", default="Shanghai", help="City 列的值,如 Beijing")
        p.add_argument("--book", help="出处里写的书名(默认取《》里那一截)")
        p.add_argument("--stats-year", type=int, default=1990)
        p.add_argument("--min-mentions", type=int, default=2)
        p.add_argument("--auto-keep", type=float)
        p.add_argument("--fixes", help="字形订正表(TSV:错<TAB>对);volume 会自己找")
        p.add_argument("--page-pattern", help="指定页码写法,不用自动认")
        p.add_argument("--reflow", default="auto", choices=["auto", "on", "off"],
                       help="接回硬断的行(默认 auto:看了再定)")
        return p

    p = sub.add_parser("volume", help="按关键词找稿子跑一本 —— 每本志一条命令",
                       parents=[common])
    p.add_argument("key", nargs="+",
                   help="稿子名里的一截,如「第三章」;写好几截也行,不必加引号")
    p.add_argument("--dir", help="转换稿放在哪(也可设 GAZ_DRAFTS 环境变量)")
    _book_opts(p)
    p.set_defaults(func=cmd_volume)

    p = sub.add_parser("book", help="指名道姓地跑一份 .md", parents=[common])
    p.add_argument("md", help="已转好的 Markdown 文件")
    _book_opts(p)
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
                   help="读 book 那一步生成的工作簿(你核过的),而不是 TSV")
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
