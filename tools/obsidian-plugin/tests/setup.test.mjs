/* 头一回用那张卡片背后的认路逻辑。
 *
 * 认路最容易出错 —— 分隔符两种、盘符到顶、往上找几层。写成纯函数就为了
 * 在这儿对得动:插件里认错了路,只表现为「一步也跑不了」,看不出错在哪儿。
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  branchOf, findRepoRoot, joinPath, parentOf, pickPython,
  repoProblem, sepOf, summarize,
} from "../build/setup.js";

test("分隔符跟着路径本身走", () => {
  assert.equal(sepOf("D:\\Coding\\CN_Map"), "\\");
  assert.equal(sepOf("/home/u/CN_Map"), "/");
});

test("接路径不会多出一个分隔符", () => {
  assert.equal(joinPath("D:\\Coding\\CN_Map", "tools", "gazetteer"),
               "D:\\Coding\\CN_Map\\tools\\gazetteer");
  assert.equal(joinPath("D:\\Coding\\CN_Map\\", "tools"), "D:\\Coding\\CN_Map\\tools");
  assert.equal(joinPath("/home/u/CN_Map/", "tools"), "/home/u/CN_Map/tools");
});

test("往上一层;到了盘符或根就停", () => {
  assert.equal(parentOf("D:\\Coding\\CN_Map\\tools"), "D:\\Coding\\CN_Map");
  assert.equal(parentOf("D:\\Coding"), "D:\\");
  assert.equal(parentOf("D:\\"), null, "盘符再往上就没有了");
  assert.equal(parentOf("/home/u"), "/home");
  assert.equal(parentOf("/home"), "/");
  assert.equal(parentOf("CN_Map"), null, "没有分隔符,无从往上");
});

/** 假的「这个文件在不在」—— 只认这几条路 */
const fake = (present) => (p) => present.includes(p);

const WIN_GAZ = "D:\\Coding\\CN_Map\\tools\\gazetteer\\gaz.py";
const NIX_GAZ = "/home/u/CN_Map/tools/gazetteer/gaz.py";

test("挑了仓库根本身,当场就认出来", () => {
  assert.equal(findRepoRoot("D:\\Coding\\CN_Map", fake([WIN_GAZ])), "D:\\Coding\\CN_Map");
});

test("挑了仓库里深处一个文件,一层层往上找得到", () => {
  assert.equal(
    findRepoRoot("D:\\Coding\\CN_Map\\src\\components\\App.jsx", fake([WIN_GAZ])),
    "D:\\Coding\\CN_Map",
  );
});

test("挑了工作簿 —— 最顺手的那一个,也认得", () => {
  assert.equal(
    findRepoRoot("D:\\Coding\\CN_Map\\CN_Electronic_Industry.xlsx", fake([WIN_GAZ])),
    "D:\\Coding\\CN_Map",
  );
});

test("挑的就是 gaz.py 自己,照样认得", () => {
  assert.equal(findRepoRoot(WIN_GAZ, fake([WIN_GAZ])), "D:\\Coding\\CN_Map");
});

test("斜杠那一路也一样", () => {
  assert.equal(findRepoRoot("/home/u/CN_Map/README.md", fake([NIX_GAZ])), "/home/u/CN_Map");
});

test("挑到仓库外头去了,找不着就回 null,不硬认", () => {
  assert.equal(findRepoRoot("D:\\别处\\随便.txt", fake([WIN_GAZ])), null);
});

test("一路找到盘符也不会死循环", () => {
  assert.equal(findRepoRoot("D:\\a\\b\\c\\d\\e\\f.txt", fake([])), null);
});

test("末尾多一个分隔符不影响", () => {
  assert.equal(findRepoRoot("D:\\Coding\\CN_Map\\", fake([WIN_GAZ])), "D:\\Coding\\CN_Map");
});

test("这个目录像不像仓库,说人话", () => {
  assert.match(repoProblem("", false), /还没选/);
  assert.match(repoProblem("D:\\别处", false), /gaz\.py|选错/);
  assert.equal(repoProblem("D:\\Coding\\CN_Map", true), null);
});

test("python 按顺序试,谁先应声算谁", () => {
  assert.equal(pickPython([{ cmd: "python", ok: true }]), "python");
  assert.equal(pickPython([{ cmd: "python", ok: false }, { cmd: "py", ok: true }]), "py");
  assert.equal(pickPython([{ cmd: "python", ok: false }]), null, "都不应声就是没有");
  assert.equal(pickPython([]), null);
});

test("分支名读得出;没挂在分支上的 HEAD 不算", () => {
  assert.equal(branchOf("claude/local-gazetteer-ocr-md-extract-po9dtk\n"),
               "claude/local-gazetteer-ocr-md-extract-po9dtk");
  assert.equal(branchOf("main"), "main");
  assert.equal(branchOf("HEAD\n"), "", "游离状态不是分支名");
  assert.equal(branchOf(""), "");
});

test("认出来的几样摆给人看,缺的也明说", () => {
  const s = summarize({ repoDir: "D:\\Coding\\CN_Map", python: "", branch: "", vaultUnits: "" });
  assert.match(s, /D:\\Coding\\CN_Map/);
  assert.match(s, /没找着/, "python 没找着要说出来,不能默默空着");
  const t = summarize({
    repoDir: "D:\\Coding\\CN_Map", python: "python",
    branch: "main", vaultUnits: "D:\\Archive\\厂所",
  });
  assert.match(t, /python/);
  assert.match(t, /厂所/);
});

// ---------------------------------------------------------------- 自己找

import { candidateRoots, scanForRepo } from "../build/setup.js";

/** 假的文件系统:给一份「目录 → 子目录」的图,外加哪几个文件在 */
function fakeFs(tree, files) {
  return {
    exists: (p) => files.includes(p) || Object.hasOwn(tree, p),
    listDirs: (p) => tree[p] ?? [],
  };
}

const TREE = {
  "D:\\": ["Coding", "Archive", "$Recycle.Bin", "Windows"],
  "D:\\Coding": ["CN_Map", "别的项目"],
  "D:\\Coding\\CN_Map": ["src", "tools", "node_modules"],
  "D:\\Archive": ["厂所", "材料"],
};
const FS = fakeFs(TREE, ["D:\\Coding\\CN_Map\\tools\\gazetteer\\gaz.py"]);

test("自己找:浅处的仓库找得着", () => {
  assert.equal(scanForRepo(["D:\\"], FS), "D:\\Coding\\CN_Map");
});

test("自己找:起点就是仓库本身,当场就中", () => {
  assert.equal(scanForRepo(["D:\\Coding\\CN_Map"], FS), "D:\\Coding\\CN_Map");
});

test("自己找:不进 node_modules、$Recycle.Bin、Windows 这类", () => {
  const visited = [];
  const spy = {
    exists: FS.exists,
    listDirs: (p) => { visited.push(p); return FS.listDirs(p); },
  };
  scanForRepo(["D:\\"], spy);
  assert.ok(!visited.some((p) => p.includes("node_modules")), "不该进 node_modules");
  assert.ok(!visited.some((p) => p.includes("$Recycle.Bin")), "不该进回收站");
  assert.ok(!visited.some((p) => p.includes("Windows")), "不该进 Windows");
});

test("自己找:深度到头就收手,不会一直往下翻", () => {
  const deep = {
    "C:\\": ["a"], "C:\\a": ["b"], "C:\\a\\b": ["c"],
    "C:\\a\\b\\c": ["d"], "C:\\a\\b\\c\\d": [],
  };
  const fs = fakeFs(deep, ["C:\\a\\b\\c\\d\\tools\\gazetteer\\gaz.py"]);
  assert.equal(scanForRepo(["C:\\"], fs, 3), null, "第 4 层的够不着 —— 限了深度");
  assert.equal(scanForRepo(["C:\\"], fs, 4), "C:\\a\\b\\c\\d", "放宽一层就够得着");
});

test("自己找:看够了本数就停 —— 宁可找不着,不可把 Obsidian 卡死", () => {
  const wide = { "C:\\": [] };
  for (let i = 0; i < 500; i++) {
    wide["C:\\"].push("d" + i);
    wide["C:\\d" + i] = [];
  }
  const fs = fakeFs(wide, []);
  let looked = 0;
  const counted = { exists: (p) => { looked++; return fs.exists(p); }, listDirs: fs.listDirs };
  assert.equal(scanForRepo(["C:\\"], counted, 3, 50), null);
  assert.ok(looked <= 120, "本数限住了,看的次数不该失控(实看 " + looked + ")");
});

test("自己找:起点不存在就跳过,不报错", () => {
  assert.equal(scanForRepo(["Z:\\", "D:\\"], FS), "D:\\Coding\\CN_Map");
});

test("从哪几处找起:库在哪个盘,那个盘排头一个", () => {
  const r = candidateRoots("E:\\库\\Archive");
  assert.equal(r[0], "E:\\");
  assert.ok(r.includes("D:\\") && r.includes("C:\\"));
  assert.equal(new Set(r).size, r.length, "不该有重的");
});

test("从哪几处找起:库就在 D 盘时不重复列 D", () => {
  const r = candidateRoots("D:\\Archive");
  assert.equal(r[0], "D:\\");
  assert.equal(r.filter((x) => x === "D:\\").length, 1);
});
