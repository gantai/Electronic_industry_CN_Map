/* 八步各是哪一条命令 —— 这个文件里没有一行 Obsidian 的东西。
   拆开是为了**测得动**:命令拼错了,插件里看不出来,跑起来才知道,
   而那时候已经动了工作簿。拼命令这件事在 tests/ 里逐条对过。

   对照《电子工业地图流程》(tools/gazetteer/电子工业地图流程.md)。
   那份文档仍是正本 —— 这里改了参数,记得回去改文档。 */

export interface Ctx {
  /** 仓库在哪儿,如 D:\Coding\CN_Map */
  repoDir: string;
  /** python 怎么敲。多半就是 "python" */
  python: string;
  /** 转换稿目录。空着就是仓库里的 转换稿\ */
  draftsDir: string;
  /** 库里厂所笔记那一支,如 D:\Archive\厂所 —— gaz push/pull 要 */
  vaultUnits: string;
  /** 在哪一支上干活 */
  branch: string;
}

export interface Cmd {
  exe: string;
  args: string[];
  cwd: string;
}

export type FieldType = "text" | "number" | "path" | "pick" | "select" | "toggle";

export interface Field {
  key: string;
  label: string;
  type: FieldType;
  /** 填错了会怎样 —— 一句话写在输入框底下 */
  hint?: string;
  placeholder?: string;
  required?: boolean;
  value?: string;
  options?: { value: string; label: string }[];
  /** path / pick 专用:只看这几种后缀 */
  exts?: string[];
  /** pick 专用:从哪个目录里列文件。眼下只有「转换稿」一处 */
  pickFrom?: "drafts";
}

export type Vals = Record<string, string>;

export interface Step {
  id: string;
  /** 面板上归在哪一段 */
  group: string;
  /** 「第三步」之类;准备与收尾的没有 */
  n?: string;
  name: string;
  /** 一句话:这一步做什么 */
  blurb: string;
  fields?: Field[];
  /** 只看不动的,面板上不必吓唬人 */
  readOnly?: boolean;
  /** 拼出要跑的命令。一步可以是好几条,按顺序跑 */
  build(v: Vals, ctx: Ctx): Cmd[];
}

export const GAZ_REL = ["tools", "gazetteer", "gaz.py"];

/** 仓库里 gaz.py 的整条路径。分隔符跟着仓库路径走 —— Windows 上是 \ */
export function gazPath(ctx: Ctx): string {
  const sep = ctx.repoDir.includes("\\") ? "\\" : "/";
  return [ctx.repoDir.replace(/[\\/]+$/, ""), ...GAZ_REL].join(sep);
}

/** 一条 gaz 命令。
 *  **参数按数组传,不拼成一行字。** 路径里有空格、有中文、有括号
 *  (`《北京工业志·电子志》2001 第四篇.md` 三样全占),拼成一行就得自己操心
 *  引号 —— 那正是 PowerShell 里最容易出岔的地方。数组交给系统去传,不必引。 */
export function gaz(ctx: Ctx, args: string[]): Cmd {
  return { exe: ctx.python, args: [gazPath(ctx), ...args], cwd: ctx.repoDir };
}

export function git(ctx: Ctx, args: string[]): Cmd {
  return { exe: "git", args, cwd: ctx.repoDir };
}

/** 填了才加这个选项;空着就当没说过 —— 让 gaz 自己用默认值。 */
function opt(args: string[], flag: string, v: string | undefined): string[] {
  const s = (v ?? "").trim();
  return s ? [...args, flag, s] : args;
}

function on(v: string | undefined): boolean {
  return v === "true" || v === "1" || v === "on";
}

const CITY_HINT =
  "图上认得的市:Beijing、Shanghai、Tianjin、Nanjing、Tangshan、Harbin、" +
  "Lanzhou、Changsha。**别的市要先添进 geocode.js**,不然那一市的厂全落到上海人民广场去。";

export const STEPS: Step[] = [
  {
    id: "update",
    group: "动手之前",
    name: "看状态:手里这份是什么时候的",
    blurb: "取远端、报版本、看工作簿动过没有。一个格子也不动。",
    readOnly: true,
    build: (_v, ctx) => [
      git(ctx, ["fetch", "origin"]),
      gaz(ctx, ["version"]),
      gaz(ctx, ["diff"]),
    ],
  },
  {
    id: "check",
    group: "动手之前",
    name: "本机装了什么、缺什么",
    blurb: "openpyxl、zhiconv、git 署名、Node,一样一样报。",
    readOnly: true,
    build: (_v, ctx) => [gaz(ctx, ["check"])],
  },

  {
    id: "convert",
    group: "抽录",
    n: "第一步",
    name: "把 PDF 转成稿子",
    blurb: "扫描件 → Markdown。全程最慢的一步,挂着让它跑。",
    fields: [
      {
        key: "pdf", label: "志书 PDF", type: "path", required: true,
        exts: ["pdf"], placeholder: "D:\\Archive\\材料\\某某志.pdf",
        hint: "整条路径贴进来最稳 —— 在资源管理器里点一下地址栏空白处,路径就成了" +
              "可复制的文字。「浏览…」有的机器上弹不出窗。",
      },
      {
        key: "first", label: "起页", type: "number", required: true,
        hint: "**阅读器显示的页数,不是书上印的那个。** 封面、序、目录都占着 PDF 的页," +
              "书上第 1 页常是 PDF 的第 15、20 页 —— 这里错了,转出来的是另一章。",
      },
      { key: "last", label: "止页", type: "number", required: true,
        hint: "两头各多转几页,胜过少转半章回头重来。" },
      {
        key: "out", label: "稿子写到哪儿", type: "text", required: true,
        placeholder: "转换稿\\《某某志》1999 第三章.md",
        hint: "直接写进 `转换稿`,第二步那道搬家就免了。相对路径按仓库算。",
      },
      {
        key: "lang", label: "识别语种", type: "select", value: "ch",
        options: [
          { value: "ch", label: "简体 (ch)" },
          { value: "chinese_cht", label: "繁体 (chinese_cht)" },
        ],
      },
      { key: "force", label: "转过一遍也重转", type: "toggle" },
    ],
    build: (v, ctx) => {
      let a = ["convert", v.pdf, "--first", v.first, "--last", v.last, "--out", v.out];
      a = opt(a, "--lang", v.lang);
      if (on(v.force)) a.push("--force");
      return [gaz(ctx, a)];
    },
  },
  {
    id: "inspect",
    group: "抽录",
    n: "第二步",
    name: "看一眼稿子的成色",
    blurb: "标题层级、页码锚点、有没有硬断行。本来就是 .md 的稿子也要跑。",
    readOnly: true,
    fields: [
      { key: "md", label: "稿子", type: "pick", required: true, exts: ["md"],
        pickFrom: "drafts", placeholder: "转换稿\\《某某志》1999 第三章.md",
        hint: "转换稿目录里的稿子都列在这儿。不在列里就把整条路径贴进来。" },
    ],
    build: (v, ctx) => [gaz(ctx, ["inspect", v.md])],
  },
  {
    id: "volume",
    group: "抽录",
    n: "第三步",
    name: "抽成待核工作簿",
    blurb: "按名字找稿子,抽出一份待核 Excel。总表这时还没动。",
    fields: [
      /* 跟第二步挑的是同一份稿子 —— 上一步挑过,这一步就已经填好了。
         先前这儿要人手打「稿子名里的一截」,等于把刚挑好的文件再描述一遍。 */
      { key: "md", label: "稿子", type: "pick", required: true, exts: ["md"],
        pickFrom: "drafts", placeholder: "转换稿\\《某某志》1999 第三章.md",
        hint: "第二步挑的那一份 —— 这儿会自己带过来。" },
      { key: "city", label: "City 列(市志填这个)", type: "text",
        placeholder: "Beijing", hint: CITY_HINT },
      { key: "province", label: "省名(省志填这个)", type: "text",
        placeholder: "江苏省",
        hint: "**省志填这一栏,把上头那栏空着。** 一本省志里十几个市,没有哪一个能当" +
              "全书的默认 —— 填了省,市就由每一家自己定(标题 / 厂址 / 名录表)," +
              "定不下来的空着、只记省,**决不拿省会顶替**。省名写全称,如 江苏省。" },
      { key: "statsYear", label: "统计年", type: "number", placeholder: "1995",
        hint: "志书各章截取的年份不一致(上海多是 1990,北京第四篇是 1995)。空着用默认。" },
      {
        key: "reflow", label: "接回硬断的行", type: "select", value: "auto",
        options: [
          { value: "auto", label: "auto —— 看了再定(默认)" },
          { value: "on", label: "on —— 一定接" },
          { value: "off", label: "off —— 一定不接" },
        ],
        hint: "稿子照原书行宽硬断的话不接回去,厂名会被断成两截,整家认不出来。",
      },
    ],
    /* 用 `gaz book <稿子>` 而不是 `gaz volume <关键词>`:
       两条命令干的是同一件事,只是找稿子的法子不同 —— volume 按名字里的
       一截去搜,book 指名道姓。面板上第二步已经把那一份挑出来了,再让人
       描述一遍没道理。`--dir` 也因此不必了:路径是整条给的。 */
    build: (v, ctx) => {
      let a = ["book", v.md];
      // 省志与市志二选一 —— 两个都填的话以省为准,那是更要紧的那一个
      a = (v.province ?? "").trim()
        ? [...a, "--province", v.province.trim()]
        : opt(a, "--city", v.city);
      a = opt(a, "--stats-year", v.statsYear);
      a = opt(a, "--reflow", v.reflow);
      return [gaz(ctx, a)];
    },
  },
  {
    id: "review",
    group: "核校",
    n: "第四步",
    name: "核对 —— 只有人能干的活",
    blurb: "打开待核工作簿,「取否」写 y 的行才收。插件代不了这一步。",
    fields: [
      { key: "xlsx", label: "待核工作簿", type: "pick", required: true, exts: ["xlsx"],
        pickFrom: "drafts", placeholder: "转换稿\\《某某志》1999 第三章.xlsx" },
    ],
    /* 用系统默认的程序开它 —— 多半是 Excel。这一条不是 gaz,见 main.ts 的特判 */
    build: () => [],
  },
  {
    id: "merge",
    group: "核校",
    n: "第五步",
    name: "并进总表",
    blurb: "核过的行追加进 CN_Electronic_Industry.xlsx。只添不改,先自动备份。",
    fields: [
      { key: "from", label: "核过的待核工作簿", type: "pick", required: true, exts: ["xlsx"],
        pickFrom: "drafts" },
      { key: "dryRun", label: "先空跑一遍(不写)", type: "toggle", value: "true",
        hint: "**头一回先空跑。** 看清楚要添几行、跳过几行,再关掉这个开关真跑。" },
    ],
    build: (v, ctx) => {
      const a = ["xlsx", "--from", v.from];
      if (on(v.dryRun)) a.push("--dry-run");
      return [gaz(ctx, a)];
    },
  },
  {
    id: "verify",
    group: "核校",
    n: "第六步",
    name: "验一验",
    blurb: "日期、坐标、出处、隶属取值、沿革 —— 只报,一个格子也不动。",
    readOnly: true,
    fields: [
      { key: "all", label: "连从前认过的一起报", type: "toggle",
        hint: "默认只报新的。旧账压着不显,是免得新毛病被埋掉。" },
    ],
    build: (v, ctx) => {
      const a = ["verify"];
      if (on(v.all)) a.push("--all");
      return [gaz(ctx, a), gaz(ctx, ["dups"])];
    },
  },
  {
    id: "tidy",
    group: "核校",
    name: "理一理沿革表",
    blurb: "按单位与年份排好,编序号、补「至」。动过沿革表就跑一遍。",
    fields: [
      { key: "dryRun", label: "先空跑一遍(不写)", type: "toggle", value: "true" },
    ],
    build: (v, ctx) => {
      const a = ["tidy"];
      if (on(v.dryRun)) a.push("--dry-run");
      return [gaz(ctx, a)];
    },
  },

  {
    id: "geocode",
    group: "落点",
    n: "第七步",
    name: "落点草稿",
    blurb: "新单位 → src/geocode.js 的条目草稿。只有写明厂址的章才做。",
    fields: [
      { key: "all", label: "连已有的一起出", type: "toggle" },
    ],
    build: (v, ctx) => {
      const a = ["geocode"];
      if (on(v.all)) a.push("--all");
      return [gaz(ctx, a)];
    },
  },
  {
    id: "geocodeCheck",
    group: "落点",
    name: "核一核落点",
    blurb: "填好的坐标落在哪个区,跟表里写的对不对得上。差一个区它一定报。",
    readOnly: true,
    build: (_v, ctx) => [gaz(ctx, ["geocode-check"])],
  },

  {
    id: "vaultPush",
    group: "库",
    name: "工作簿 → 库",
    blurb: "全部厂所各写一则笔记,字段在 frontmatter。",
    fields: [
      { key: "force", label: "库里改过的也照盖", type: "toggle",
        hint: "不开的话,库里有未推回的改动它会拦住 —— 那正是要拦的。" },
    ],
    build: (v, ctx) => {
      const a = ["push", "--vault", ctx.vaultUnits];
      if (on(v.force)) a.push("--force");
      return [gaz(ctx, a)];
    },
  },
  {
    id: "vaultPull",
    group: "库",
    name: "库 → 工作簿",
    blurb: "在库里改过的字段写回原行。",
    fields: [
      { key: "dryRun", label: "先空跑一遍(不写)", type: "toggle", value: "true" },
    ],
    build: (v, ctx) => {
      const a = ["pull", "--vault", ctx.vaultUnits];
      if (on(v.dryRun)) a.push("--dry-run");
      return [gaz(ctx, a)];
    },
  },
];

export function stepById(id: string): Step | undefined {
  return STEPS.find((s) => s.id === id);
}

/** 面板上分几段,按 STEPS 里头一次出现的次序 */
export function groups(): string[] {
  const out: string[] = [];
  for (const s of STEPS) if (!out.includes(s.group)) out.push(s.group);
  return out;
}

/** 必填的填了没有 —— 回一句话说缺什么,齐了回 null */
export function missing(step: Step, v: Vals): string | null {
  for (const f of step.fields ?? []) {
    if (f.required && !(v[f.key] ?? "").trim()) return "还没填:" + f.label;
  }
  return null;
}


/** 转换稿在哪个目录。设置里没填就是仓库里的 `转换稿\` —— 跟 gaz 的默认一致 */
export function draftsDir(ctx: Ctx): string {
  const sep = ctx.repoDir.includes("\\") ? "\\" : "/";
  return ctx.draftsDir.trim() || (ctx.repoDir.replace(/[\\/]+$/, "") + sep + "转换稿");
}


/** 一份稿子抽出来的待核工作簿在哪儿 —— 跟稿子同目录同名,只换个后缀。
 *  (`gaz book` 的 `--out` 默认就是这么定的,见 gaz.py 里 cmd_book。)
 *  第四、五步据此把稿子那一份带过来,不必再挑一遍。 */
export function reviewBookOf(md: string): string {
  const t = String(md || "").trim();
  return t && /\.md$/i.test(t) ? t.replace(/\.md$/i, ".xlsx") : "";
}
