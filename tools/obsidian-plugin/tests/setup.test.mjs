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
