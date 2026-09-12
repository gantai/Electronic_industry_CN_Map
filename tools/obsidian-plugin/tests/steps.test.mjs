/* 拼命令拼对了没有。
 *
 * 插件里看不出命令拼错 —— 跑起来才知道,而那时候工作簿已经动过了。
 * 所以 steps.ts / gitops.ts 两处都不碰 Obsidian,好在这儿逐条对。
 *
 * 跑:npm test（在 tools/obsidian-plugin 底下）
 */
import test from "node:test";
import assert from "node:assert/strict";

import { STEPS, gaz, gazPath, missing, stepById, groups } from "../build/steps.js";
import { blockPublish, parseLog, parseStatus, publishPlan } from "../build/gitops.js";

const WIN = {
  repoDir: "D:\\Coding\\CN_Map",
  python: "python",
  draftsDir: "",
  vaultUnits: "D:\\Archive\\厂所",
  branch: "claude/local-gazetteer-ocr-md-extract-po9dtk",
};
const NIX = { ...WIN, repoDir: "/home/u/CN_Map", vaultUnits: "/home/u/Archive/厂所" };

const run = (id, v = {}, ctx = WIN) => stepById(id).build(v, ctx);

test("gaz.py 的路径跟着仓库路径的分隔符走", () => {
  assert.equal(gazPath(WIN), "D:\\Coding\\CN_Map\\tools\\gazetteer\\gaz.py");
  assert.equal(gazPath(NIX), "/home/u/CN_Map/tools/gazetteer/gaz.py");
  // 末尾多一个分隔符不该多出一段空的
  assert.equal(gazPath({ ...WIN, repoDir: "D:\\Coding\\CN_Map\\" }),
               "D:\\Coding\\CN_Map\\tools\\gazetteer\\gaz.py");
});

test("命令在仓库目录里跑,不在库里跑", () => {
  const c = gaz(WIN, ["version"]);
  assert.equal(c.cwd, "D:\\Coding\\CN_Map");
  assert.equal(c.exe, "python");
});

test("参数是数组,带空格与中文的路径不必自己加引号", () => {
  const [c] = run("inspect", { md: "转换稿\\《北京工业志·电子志》2001 第四篇.md" });
  // 整条路径必须是**一个**参数 —— 拆成两个,gaz 就会说找不到文件
  assert.equal(c.args.at(-1), "转换稿\\《北京工业志·电子志》2001 第四篇.md");
  assert.equal(c.args.filter((a) => a.includes("第四篇")).length, 1);
});

test("第一步 转 PDF:页码与去处都传上了", () => {
  const [c] = run("convert", {
    pdf: "D:\\Archive\\材料\\某某志.pdf",
    first: "250", last: "320",
    out: "转换稿\\《某某志》1999 第三章.md",
    lang: "ch",
  });
  assert.deepEqual(c.args.slice(1), [
    "convert", "D:\\Archive\\材料\\某某志.pdf",
    "--first", "250", "--last", "320",
    "--out", "转换稿\\《某某志》1999 第三章.md",
    "--lang", "ch",
  ]);
});

test("第一步:没开「重转」就不该有 --force", () => {
  const [a] = run("convert", { pdf: "x.pdf", first: "1", last: "2", out: "o.md" });
  assert.ok(!a.args.includes("--force"));
  const [b] = run("convert", { pdf: "x.pdf", first: "1", last: "2", out: "o.md", force: "true" });
  assert.ok(b.args.includes("--force"));
});

test("第三步 抽:关键词拆成几个,城市传上", () => {
  const [c] = run("volume", { key: "第四篇", city: "Beijing", statsYear: "1995" });
  assert.deepEqual(c.args.slice(1), [
    "volume", "第四篇", "--city", "Beijing", "--stats-year", "1995",
  ]);
});

test("第三步:关键词写好几截,一截一个参数", () => {
  const [c] = run("volume", { key: "北京 第四篇", city: "Beijing" });
  assert.deepEqual(c.args.slice(1, 4), ["volume", "北京", "第四篇"]);
});

test("第三步:空着的选项一个也不传 —— 让 gaz 用自己的默认值", () => {
  const [c] = run("volume", { key: "第三章", city: "Shanghai", statsYear: "", reflow: "", dir: "" });
  assert.ok(!c.args.includes("--stats-year"));
  assert.ok(!c.args.includes("--reflow"));
  assert.ok(!c.args.includes("--dir"));
});

test("第三步:设置里填了转换稿目录就跟着传", () => {
  const ctx = { ...WIN, draftsDir: "D:\\Archive\\转换稿" };
  const [c] = run("volume", { key: "第三章", city: "Shanghai" }, ctx);
  assert.deepEqual(c.args.slice(-2), ["--dir", "D:\\Archive\\转换稿"]);
});

test("第五步 并表:默认先空跑 —— 头一回不该真写", () => {
  const step = stepById("merge");
  const dry = step.fields.find((f) => f.key === "dryRun");
  assert.equal(dry.value, "true", "「先空跑」这个开关默认要是开着的");
  const [c] = step.build({ from: "a.xlsx", dryRun: "true" }, WIN);
  assert.ok(c.args.includes("--dry-run"));
  const [d] = step.build({ from: "a.xlsx", dryRun: "false" }, WIN);
  assert.ok(!d.args.includes("--dry-run"));
});

test("第六步 验:verify 与 dups 两条,都不写", () => {
  const cs = run("verify", {});
  assert.equal(cs.length, 2);
    assert.deepEqual(cs.map((c) => c.args[1]), ["verify", "dups"]);
  assert.ok(stepById("verify").readOnly, "验一验是只读的");
});

test("库:push 带着设置里那条库路径", () => {
  const [c] = run("vaultPush", {});
  assert.deepEqual(c.args.slice(1), ["push", "--vault", "D:\\Archive\\厂所"]);
});

test("必填的没填,拦下来并说缺哪一样", () => {
  const step = stepById("convert");
  assert.match(missing(step, {}), /起页|志书 PDF/);
  assert.equal(
    missing(step, { pdf: "a.pdf", first: "1", last: "2", out: "o.md" }),
    null,
  );
  // 只有空格也算没填
  assert.notEqual(missing(step, { pdf: "   ", first: "1", last: "2", out: "o.md" }), null);
});

test("每一步的 id 不重样,分组次序照 STEPS 排", () => {
  const ids = STEPS.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.deepEqual(groups()[0], "动手之前");
  assert.ok(groups().includes("上线") === false, "上线那几条是 git,不在 STEPS 里");
});

// ---------------------------------------------------------------- git

test("上线那一串:六句,顺序不许动", () => {
  const p = publishPlan(WIN);
  assert.deepEqual(
    p.cmds.map((c) => c.args.join(" ")),
    [
      "fetch origin main",
      "checkout main",
      "merge --ff-only origin/main",
      "merge " + WIN.branch,
      "push origin main",
      "checkout " + WIN.branch,
    ],
  );
});

test("上线:少了 --ff-only 那一句就是从前那次的 non-fast-forward", () => {
  /* 这一条看着多余,可那次出事正是因为漏了它 —— 本地 main 落后三十七个提交。
     写成测试,往后谁改这一串都得先绊一下。 */
  const p = publishPlan(WIN);
  const i = p.cmds.findIndex((c) => c.args.join(" ") === "merge --ff-only origin/main");
  const j = p.cmds.findIndex((c) => c.args.join(" ") === "merge " + WIN.branch);
  assert.ok(i > -1, "必须有 merge --ff-only origin/main");
  assert.ok(i < j, "追平远端要排在合分支之前");
});

test("上线:切回干活那一支是最后一句 —— 不切回去,下回就改在 main 上了", () => {
  const p = publishPlan(WIN);
  assert.deepEqual(p.cmds.at(-1).args, ["checkout", WIN.branch]);
});

test("git status 读得出干净不干净", () => {
  assert.deepEqual(parseStatus(""), { clean: true, files: [] });
  const st = parseStatus(" M CN_Electronic_Industry.xlsx\n?? 转换稿/新稿.md\n");
  assert.equal(st.clean, false);
  assert.deepEqual(st.files, ["CN_Electronic_Industry.xlsx", "转换稿/新稿.md"]);
});

test("git log 数得出几条", () => {
  assert.equal(parseLog("").n, 0);
  assert.equal(parseLog("a1b2c3 一\nd4e5f6 二\n").n, 2);
});

test("有没提交的改动就不许上线 —— 底下要切分支", () => {
  const stop = blockPublish(" M CN_Electronic_Industry.xlsx\n", "a1b2c3 一条\n");
  assert.ok(stop);
  assert.match(stop, /先提交/);
});

test("没有什么可上线的,也拦下来", () => {
  const stop = blockPublish("", "");
  assert.ok(stop);
  assert.match(stop, /一模一样|没有什么可上线/);
});

test("干净、且确有要发布的,才放行", () => {
  assert.equal(blockPublish("", "a1b2c3 补录某某志\n"), null);
});

test("第三步:省志填省名,不填 City —— 省会不该当全书的默认", () => {
  const [c] = run("volume", { key: "第三章", province: "江苏省" });
  assert.ok(c.args.includes("--province"));
  assert.ok(!c.args.includes("--city"), "填了省就不该再传 --city");
  assert.deepEqual(c.args.slice(-2), ["--province", "江苏省"]);
});

test("第三步:市志照旧只传 --city", () => {
  const [c] = run("volume", { key: "第四篇", city: "Beijing" });
  assert.ok(c.args.includes("--city"));
  assert.ok(!c.args.includes("--province"));
});

test("第三步:两个都填,以省为准", () => {
  const [c] = run("volume", { key: "x", city: "Beijing", province: "江苏省" });
  assert.ok(c.args.includes("--province"));
  assert.ok(!c.args.includes("--city"));
});

// ---------------------------------------------------------------- 挑稿子那几栏

import { draftsDir } from "../build/steps.js";

test("转换稿目录:设置里没填就是仓库里那一个", () => {
  assert.equal(draftsDir(WIN), "D:\\Coding\\CN_Map\\转换稿");
  assert.equal(draftsDir(NIX), "/home/u/CN_Map/转换稿");
  assert.equal(draftsDir({ ...WIN, draftsDir: "D:\\Archive\\转换稿" }), "D:\\Archive\\转换稿");
});

test("稿子与待核工作簿从目录里挑,不指望那个选文件框", () => {
  /* 「浏览…」在这台机器上按了没反应 —— Electron 的选文件框本来就不保准。
     这三栏的文件都在转换稿那一个已知目录里,列出来挑才稳当。 */
  for (const [id, key] of [["inspect", "md"], ["review", "xlsx"], ["merge", "from"]]) {
    const f = stepById(id).fields.find((x) => x.key === key);
    assert.equal(f.type, "pick", id + " 的「" + f.label + "」该从目录里挑");
    assert.equal(f.pickFrom, "drafts");
    assert.ok(f.exts?.length, "得说清楚挑哪种后缀");
  }
});

test("PDF 那一栏留着手填 —— 原件不在转换稿里,而且要说明浏览不保准", () => {
  const f = stepById("convert").fields.find((x) => x.key === "pdf");
  assert.equal(f.type, "path");
  assert.match(f.hint, /贴|浏览/, "得告诉人贴路径最稳");
});
