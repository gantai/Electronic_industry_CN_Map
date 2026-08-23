# gaz —— 把一本地方志变成这张地图上的数据

扫描件 → 逐页文本 → 带页码的 Markdown → 待核记录 → `CN_Electronic_Industry.xlsx`。

志书是这张图最大的一处矿脉:厂所各占一节,始建、沿革、厂址、产品、职工人数
都写在里头。手抄一本要几个月,这套东西把**誊录**的活儿包了,**判断**的活儿
仍旧留给你 —— 抽出来的每一条都带着原页码与原文,`keep` 一栏你不写 `y`,
它就进不了工作簿。

> 志书在架上,程序在你自己的机器上跑。仓库里这份只是工具,不含任何志书原文。

## 装

Python 3.9 以上。先看看缺什么:

```bash
python3 tools/gazetteer/gaz.py check
```

它会逐项报告并给出装法。最省事的一套:

```bash
pip install openpyxl pymupdf                 # 必装:回写工作簿、读 PDF
pip install paddleocr paddlepaddle           # 中文 OCR 首选
# 或者用 tesseract 作备胎:
#   macOS  brew install tesseract tesseract-lang
#   Debian apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra
```

**PDF 本身带字的话,一样 OCR 引擎都不用装。** 书同文、超星、国图数字方志的
PDF 多半带文本层,`gaz` 会逐页检查,有字就直接取,又快又准。

## 跑

```bash
cd /path/to/Electronic_industry_CN_Map

# 一气跑到待核这一步（ocr → md → extract → notes）
python3 tools/gazetteer/gaz.py run ~/志书/上海电子仪表工业志.pdf \
        --slug 上海电子仪表工业志 --book 上海电子仪表工业志

# 只想先试三十页
python3 tools/gazetteer/gaz.py run ~/志书/上海电子仪表工业志.pdf \
        --slug 试跑 --first 200 --last 230
```

跑完东西都在 `gaz-work/<slug>/` 底下:

```
pages/            逐页文本。**断了接着跑**靠它 —— 已识别的页不会重做
meta.json         每页由哪条路径取的字（文本层 / paddleocr / tesseract）
<slug>.md         转好的 Markdown,丢进 Obsidian 库里就能读
<slug>.fixes.tsv  字形订正流水,逐条可查
review/           四张待核 TSV + geocode 落点草稿
vault/            每单位一则笔记 + 一则索引
```

### 然后是只有人能干的活

打开 `review/units.tsv`（Excel、Numbers、VS Code 都行,制表符分隔),
逐行看 `evidence` 那一栏 —— 那是抽取所据的原文。核对无误,把 `keep` 改成 `y`。
`role` 一栏说明这条记载的来路:

| role | 意思 |
| --- | --- |
| `专条` | 志中有它的专节,标题即厂名 —— 最可靠 |
| `点名` | 没有专节,但行文点了名 |
| `提及` | 只在讲别家时被顺带说起 —— 多半是前身或协作单位,**字段一律不填**,请自行核实 |

改完:

```bash
python3 tools/gazetteer/gaz.py xlsx --slug 上海电子仪表工业志 --dry-run   # 先看要加什么
python3 tools/gazetteer/gaz.py xlsx --slug 上海电子仪表工业志            # 真写（自动先备份）
python3 tools/gazetteer/gaz.py geocode --slug 上海电子仪表工业志          # 新单位的落点条目草稿
git add -A && git commit -m "补录上海电子仪表工业志" && git push
```

`geocode` 那一步生成 `review/geocode-stub.js`:照 `src/geocode.js` 的体例
把格子开好、地址与出处摆好,坐标留白 —— **落点得你来定**,志书只写门牌。
不填也不要紧,站点会把它落在市中心并标「坐标待定位」。

## 抽出来的东西对着哪张表

| TSV | 工作表 | 抽的是 |
| --- | --- | --- |
| `units.tsv` | `Fact and Comp-Shanghai` | 厂名、行业、产品、始建 / 终止、沿革、门牌、1990 年统计块八项 |
| `semi.tsv` | `Semi-Product` | 器件投产:产品、厂、年份、人员 |
| `comp.tsv` | `Comp-Product` | 整机研制:字长、内存、运算速度、研制单位、协作厂 |
| `names.tsv` | `Name-History` | 名称沿革,一行一段,出处是**志书页码**而非「据 Founder 列推定」 |

日期一律折成本仓库的八位写法(`19580600` = 1958 年 6 月),
「一九六五年」「民国二十六年」这类纪年都认得。
`Founder` 列照原表体例串成 `甲->19660300改名乙->19700000划归四机部`。

## 几条立得住的规矩

**一、每条都回注得到原页。** Markdown 里每页正文前有 `<!-- p.123 -->`,
抽取时据以生成 `Source`(如 `上海电子仪表工业志·p.101`)。查得回去的记载才算数。

**二、一句话讲的是谁,分得清。** 「上海元件十四厂……1985年12月撤销,并入上海
无线电十九厂」——撤销的是元件十四厂。若不分身份,十九厂就平白多个终止年。
所以每句话按「落在谁的标题底下」定归属,只被顺带提到的单位不予立字段。
同理,「撤销并入某厂」是终局,记进 `Remark`,**不写进 `Founder`** —— 写进去,
站点会把它当成前身,连出一条方向相反的沿革线。

**三、字形订正只做不涉判断的事。** 全角转半角一类照做,其余一概不动。
要改别的字,自备一张 `fixes.tsv`(制表符分隔:`错<TAB>对`),`--fixes` 指给它;
每一处改动都记在 `<slug>.fixes.tsv` 里备查,绝不悄悄改字。

**四、表格不硬认。** 数字成列、少有句读的页判为表格,原样照录在代码块里并注明
「未作还原」,交给人处置 —— 认错的表比没认的表难查。

## 在 Obsidian 里

`vault/` 里一单位一则笔记:frontmatter 是能进工作簿的字段(Dataview 直接查),
正文是原文佐证与页码,沿革与备注里提到的别家单位连成 `[[wikilink]]` ——
点开一家厂,前身、后身、协作对象都在眼前。`<slug>.md` 是全书,也丢进库里,
笔记末尾的出处便指得过去。

把 `gaz-work/` 整个放进库,或只把 `vault/` 与 `<slug>.md` 拷进去,都行。

## 命令一览

```
gaz check                     本机环境自检
gaz ocr    <pdf|图目录>        扫描件 → 逐页文本      --engine auto|text|paddle|tesseract
                                                    --first/--last/--dpi/--force
gaz md     --slug X           逐页文本 → Markdown    --fixes/--show-furniture/--keep-furniture
gaz extract --slug X          Markdown → 四张 TSV    --book/--stats-year/--min-mentions/--auto-keep
gaz notes  --slug X           → Obsidian 笔记        --all（不问 keep 全写出）
gaz geocode --slug X          → geocode.js 落点草稿
gaz xlsx   --slug X           keep=y 的行 → 工作簿    --dry-run/--allow-dup
gaz run    <pdf>              前四步一气跑完
```

`--work` 改工作目录(默认 `gaz-work/`),`--xlsx` 改目标工作簿。

## 有数没数的地方

- **`--stats-year` 默认 1990**,与原表的统计断面一致。志书里别的年份的数字不会
  写进统计块,只记在 `Remark` 里注明年份,免得两个断面的数混作一谈。
- **竖排、繁体**:`--lang chinese_cht` 可换 PaddleOCR 的繁体模型;竖排识别率
  一般,老志书(1949 年前)建议先试三十页看看成色。
- **表格里的统计数字取不到** —— 志书的厂所一览表多半是表格,本工具只标出
  「疑似表格」,不作还原。那部分仍要手录。
- **人名、产品名的抽取偏保守**,宁可漏,不愿错。漏掉的自己往 TSV 里补一行即可。
- 抽取全是**规则**,不是模型:它认得志书的套语(「前身为」「改名为」「划归」),
  遇上别出心裁的行文就认不出。这也是 `evidence` 一栏必须逐条过目的原因。

## 回归测试

```bash
python3 tools/gazetteer/tests/test_pipeline.py
```

拿三页仿志书体例的样张跑完整条流水线,盯住几处最容易张冠李戴的地方
(见 `tests/fixture/README.md`)。改过抽取规则,跑一遍再提交。
