#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gaz —— 把一本地方志变成这张地图上的数据。

    gaz guide   --vault D:\\Archive  《电子工业地图流程》:一份 .md 到地图更新
    gaz version                   手里这一份工具是什么时候的、该不该更新
    gaz diff                      工作簿跟 git 里那份差在哪儿(二进制,git 只说「变了」)
    gaz verify                    验一验(只报,不动手;默认只报新的)
    gaz tidy                      把沿革表理顺:按单位与年份排好,编序号、补「至」
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

# 认得哪些子命令 —— gaz version 拿它对照:少了哪一个,手里这份就是旧的
SUBCOMMANDS = []

# 扫描件 → Markdown 不在这个仓里。同一批 PDF 另一个项目也要转,那边把转换
# 单拆成了 zhiconv 一个包,专门伺候这两处;这边再写一份只会更差。
ZHICONV_INSTALL = (
    # 装的是整个 historian-archive-management(zhiconv 是它里头的一个包)。
    # 别写成 "zhiconv @ git+…" —— pip 会拿这个名字跟包自报的名字对,对不上就不装。
    # 分支也得写明:那边的 main 眼下只剩一个 LICENSE,活都在这一支上。
    'pip install "git+https://github.com/gantai/Historian_Archive_Management@claude/historian-archive-obsidian-9impe4"\n'
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


def run_out(*cmd, **kw):
    """跑一条外部命令,拿它的输出;跑不起来、或返回非零,就是 None。

    **编码写死 UTF-8,不许跟着本机的。** subprocess 的 text=True 是按本地编码
    解的 —— 简体中文 Windows 上那是 GBK,而 git 吐出来的提交说明是 UTF-8。
    里头但凡有一个 GBK 认不得的字节(破折号、间隔号、⊂ 都够),读输出的那个
    线程当场就炸,stdout 成了 None,底下再 .strip() 就是一句莫名其妙的
    AttributeError。errors="replace" 是第二道保险:认不得的字换成 �,
    不让一个字符拦住整条命令。
    """
    import subprocess
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=15,
                             encoding="utf-8", errors="replace", **kw)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or out.stdout is None:
        return None
    return out.stdout.strip()


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

    # 底下这两样不归 pip 管,却是真绊过人的:没设 user.name 提交会被拒,
    # 没装 Node 看不了本地那张图
    run = run_out

    print("\n仓库这一头:\n")
    if run("git", "--version") is None:
        print("  [ ] git          没装 —— https://git-scm.com/download/win")
    else:
        who = run("git", "config", "user.name")
        mail = run("git", "config", "user.email")
        if who and mail:
            print("  [✓] git          提交署名:%s <%s>" % (who, mail))
        else:
            print("  [ ] git          没设署名,git commit 会拒绝\n"
                  '       装法:git config --global user.name "你的名字"\n'
                  '            git config --global user.email "你的邮箱"')

    npm = run("npm", "--version") or run("npm.cmd", "--version")
    node = run("node", "--version")
    if npm and node:
        print("  [✓] Node/npm     node %s、npm %s —— npm run dev 看本地那张图"
              % (node, npm))
    else:
        print("  [ ] Node/npm     没装,本地看不了图(线上不受影响 —— "
              "GitHub 那头自带)\n"
              "       装法:winget install OpenJS.NodeJS.LTS,装完新开终端")
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


def cmd_version(args):
    """手里这一份工具是什么时候的 —— 拿旧版跑,少的那道关卡不会吭声。"""

    def git(*a):
        return run_out("git", "-C", REPO, *a)

    head = git("log", "-1", "--format=%h  %cd  %s", "--date=format:%Y-%m-%d %H:%M")
    if not head:
        print("这儿不像个 git 仓库,认不出版本。")
        return 1
    print("仓库   %s" % REPO)
    print("版本   %s" % head)
    print("分支   %s" % (git("rev-parse", "--abbrev-ref", "HEAD") or "?"))

    dirty = git("status", "--porcelain")
    if dirty:
        n = len([x for x in dirty.splitlines() if x.strip()])
        print("改动   本地有 %d 个文件改过没提交" % n)
        for line in dirty.splitlines()[:6]:
            print("         %s" % line)
    else:
        print("改动   干净")

    up = git("rev-parse", "--abbrev-ref", "@{u}")
    if up:
        behind = git("rev-list", "--count", "HEAD..@{u}")
        ahead = git("rev-list", "--count", "@{u}..HEAD")
        if behind and int(behind):
            print("落后   比 %s 少 %s 个提交 —— 该更新了(见下)" % (up, behind))
        elif ahead and int(ahead):
            print("领先   比 %s 多 %s 个提交(还没推)" % (up, ahead))
        else:
            print("同步   与 %s 齐平" % up)
        print("       (这是上次 git fetch 时的账;要看准数,先 git fetch)")

    print("\n认得的命令:%s" % "、".join(SUBCOMMANDS))
    print("少了哪一个,就是这一份旧了。更新:")
    print("  git -C %s pull origin %s"
          % (REPO, git("rev-parse", "--abbrev-ref", "HEAD") or "<分支>"))
    return 0


def cmd_diff(args):
    """两份工作簿差在哪儿 —— 默认拿手里这份跟 git 里那份比。

    `.xlsx` 是二进制,git 只会说「变了」,不说变了什么。于是 pull 撞车时,
    没人答得上「我本地那点改动到底是什么、值不值得留」。"""
    import subprocess
    import tempfile

    new_path = args.xlsx
    old_path, tmp = args.against, None
    if old_path is None:
        rev = args.rev or "HEAD"
        rel = os.path.relpath(os.path.abspath(new_path), REPO).replace(os.sep, "/")
        try:
            out = subprocess.run(("git", "-C", REPO, "show", "%s:%s" % (rev, rel)),
                                 capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            sys.exit("取不到 git 里那一份:%s" % e)
        if out.returncode != 0:
            sys.exit("取不到 %s:%s 的那一份 —— %s"
                     % (rev, rel, out.stderr.decode("utf-8", "replace").strip()))
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.write(out.stdout)
        tmp.close()
        old_path = tmp.name
        print("比:%s 里那一份  →  手里这一份" % rev)
    else:
        print("比:%s  →  %s" % (os.path.basename(old_path), os.path.basename(new_path)))

    try:
        d = toxlsx.diff_workbooks(old_path, new_path,
                                  skip_cols=() if args.all_cols else ("序", "至"))
    finally:
        if tmp:
            os.unlink(tmp.name)

    if not d:
        print("\n一样 —— 数据上没有分别。")
        print("(「序」「至」是算出来的,不算数据变动;要连它们一起比,加 --all-cols)")
        return 0

    for sheet, r in d.items():
        print("\n【%s】新增 %d、消失 %d、改过 %d"
              % (sheet, len(r["added"]), len(r["gone"]), len(r["changed"])))
        # 一行拿什么称呼它 —— 各表的抬头不一样,机构沿革压根没有 Unit 那一栏
        def who_of(x):
            if x.get("前身") or x.get("后继"):
                return "%s → %s" % (x.get("前身") or "?", x.get("后继") or "?")
            return x.get("Unit") or x.get("Product") or x.get("Name") or "?"

        for x in r["added"][:12]:
            print("   + %s" % who_of(x))
        if len(r["added"]) > 12:
            print("     …… 还有 %d 条" % (len(r["added"]) - 12))
        for x in r["gone"][:12]:
            print("   - %s" % who_of(x))
        if len(r["gone"]) > 12:
            print("     …… 还有 %d 条" % (len(r["gone"]) - 12))
        for who, fields in r["changed"][:12]:
            for lab, a, b in fields[:4]:
                print("   ~ %s  %s:%s → %s"
                      % (who, lab, ("（空）" if a == "" else a)[:30],
                         ("（空）" if b == "" else b)[:30]))
        if len(r["changed"]) > 12:
            print("     …… 还有 %d 行改过" % (len(r["changed"]) - 12))
    return 0


def cmd_tidy(args):
    """把沿革表理一理 —— 同一单位的几段挨在一处,按年份排好,编上序号。"""
    r = toxlsx.tidy_names(args.xlsx, dry_run=args.dry_run)
    if not r["rows"]:
        print("沿革表是空的,没什么可理。")
        return 0
    print("%d 段名称,%d 行挪过位置。" % (r["rows"], r["moved"]))
    print("  「序」是同一单位里的第几个名字,「至」是这个名字用到哪一年"
          "(下一段启用那年)。")
    print("  两列都是算出来的 —— 手工插过行就再跑一遍。")
    if args.dry_run:
        print("  (--dry-run:一个格子也没动)")
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
            # 厂所那一类的钥匙就是两个厂名,截到 10 个字什么也看不出
            wide = sheet == "厂所"
            print("   %-14s %-*s 行 %-12s %s"
                  % (sheet, 34 if wide else 10, key[:34 if wide else 10],
                     str(rows), who[:46]))
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
    "沿革": "改名链上立不住的段落",
    "机构": "合并、分立、划归、合资 —— 这张表是明写的,写错就直接错在图上",
    "名录": "这些名字在厂所表里查无此人。打错字、把动词粘进了名字、"
            "或者这一家本来就没登记 —— 连不上的那条线,地图上什么也看不出来",
}


def cmd_verify(args):
    """手改过工作簿之后验一验 —— 只报,一个格子也不动。

    默认只报**新的**。从前看过、认下的那些记在《已核》里,不再翻出来 ——
    二十八条「没写出处」的旧账每回都摆在头里,新伤就没人看得见了。"""
    bad = toxlsx.verify(args.xlsx, geocode_js=DEFAULT_GEOCODE)

    if args.accept:
        path, n = toxlsx.save_accepted(args.xlsx, bad)
        print("这 %d 处都记作看过了,写进 %s" % (n, os.path.basename(path)))
        print("往后 %s verify 只报新的;要全部重看,加 --all。" % SELF)
        return 0

    seen = set() if args.all else toxlsx.load_accepted(args.xlsx)
    fresh = [t for t in bad if (t[0], t[3]) not in seen]
    old_n = len(bad) - len(fresh)

    if not fresh:
        if old_n:
            print("没有新的。(另有 %d 处是从前认过的,要看加 --all)" % old_n)
        else:
            print("没看出问题。")
        return 0
    by = {}
    for kind, where, why, _key in fresh:
        by.setdefault(kind, []).append((where, why))
    print("%d 处可疑:" % len(fresh))
    for kind in ("名录", "机构", "沿革", "日期", "坐标", "出处"):
        rows = by.pop(kind, [])
        if not rows:
            continue
        print("\n【%s】%d 处 —— %s" % (kind, len(rows), VERIFY_NOTE.get(kind, "")))
        for where, why in rows[:30]:
            print("   %s%s%s" % (where, " " * max(1, 30 - _w(where)), why))
        if len(rows) > 30:
            print("   …… 还有 %d 处" % (len(rows) - 30))
    if old_n:
        print("\n(另有 %d 处是从前认过的,没再报 —— 要看加 --all)" % old_n)
    print("\n看过了、都认了:%s verify --accept —— 往后只报新的。" % SELF)
    return 0


def cmd_guide(args):
    """把《流程》写进库里 —— 照着办的那一份,该跟笔记摆在一处。"""
    docs = [("电子工业地图流程.md", "电子工业地图流程.md")]
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
    # 稿子的正经去处就是仓库里的 转换稿 —— 没别的指示就用它,不必先设环境变量
    default = os.path.join(REPO, "转换稿")
    root = args.dir or os.environ.get("GAZ_DRAFTS")
    if not root and os.path.isdir(default):
        root = default
        print("转换稿目录:%s(没设 GAZ_DRAFTS,用的仓库里这一个)" % root)
    if not root:
        sys.exit("找不到转换稿目录。稿子放进 %s 就行 —— 那是默认去处,\n"
                 "目录建起来、稿子放进去,这条命令就跑得动了。\n"
                 "\n放在别处的话,指给它:--dir …,或设个环境变量,以后不必再写:\n"
                 "  Windows  [Environment]::SetEnvironmentVariable("
                 "\"GAZ_DRAFTS\", \"D:\\Coding\\CN_Map\\转换稿\", \"User\")\n"
                 "  其他     export GAZ_DRAFTS=~/转换稿" % default)
    if not os.path.isdir(root):
        sys.exit("找不到目录:%s\n(稿子的默认去处是 %s)" % (root, default))
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

    # 型号里的连字符被认成汉字「一」是转换的通病(TQ一16、DJS一131)。不改,
    # 型号认不出来,更要紧的是跟总表里的 DJS-131 对不上,判重拦不住。
    text, dashes = BOOK.fix_model_dash(text)
    if dashes:
        print("型号里的「一」改回连字符 %d 处(TQ一16 → TQ-16)" % dashes)

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
    global SUBCOMMANDS

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

    p = sub.add_parser("verify", help="验一验(只报,不动手;默认只报新的)",
                       parents=[common])
    p.add_argument("--all", action="store_true",
                   help="连从前认过的一并报")
    p.add_argument("--accept", action="store_true",
                   help="眼下这些都看过了,记下来,往后不再报")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("diff", help="两份工作簿差在哪儿(默认跟 git 里那份比)",
                       parents=[common])
    p.add_argument("--against", help="跟指定的另一个 .xlsx 比")
    p.add_argument("--rev", help="跟哪个提交里的那份比(默认 HEAD)")
    p.add_argument("--all-cols", action="store_true",
                   help="连「序」「至」这些算出来的列也比")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("version", help="手里这一份工具是什么时候的", parents=[common])
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("tidy", help="把沿革表理顺:按单位与年份排好,编序号、补「至」",
                       parents=[common])
    p.add_argument("--dry-run", action="store_true", help="只看会怎么排,不写回")
    p.set_defaults(func=cmd_tidy)

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

    SUBCOMMANDS = list(sub.choices)
    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
