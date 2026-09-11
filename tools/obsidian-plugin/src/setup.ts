/* 头一回用:把仓库、python、分支这几样认出来,不让人去设置页里翻。

   照旧不碰 Obsidian —— 认路这件事最容易出错(分隔符、盘符、往上找几层),
   所以写成纯函数,在 tests/ 里对得动。 */

/** 路径用的是哪个分隔符 —— Windows 上是 `\`,别处是 `/` */
export function sepOf(p: string): string {
  return p.includes("\\") ? "\\" : "/";
}

export function joinPath(base: string, ...parts: string[]): string {
  const sep = sepOf(base);
  return [base.replace(/[\\/]+$/, ""), ...parts].join(sep);
}

/** 上一层。到顶了(`D:\` 或 `/`)回 null */
export function parentOf(p: string): string | null {
  const trimmed = p.replace(/[\\/]+$/, "");
  const i = Math.max(trimmed.lastIndexOf("\\"), trimmed.lastIndexOf("/"));
  if (i < 0) return null;
  const up = trimmed.slice(0, i);
  // `D:` 这样只剩盘符的,补回一个反斜杠;再往上就没有了
  if (/^[A-Za-z]:$/.test(up)) return up + "\\";
  if (up === "") return "/";
  return up === trimmed ? null : up;
}

export const GAZ_MARK = ["tools", "gazetteer", "gaz.py"];

/**
 * 从随便一个仓库里的文件(或目录)往上找,找到搁着 `tools/gazetteer/gaz.py`
 * 的那一层 —— 那就是仓库根。找不到回 null。
 *
 * 这么办是为了宽容:让人去挑 `gaz.py` 太难为人,挑整个文件夹又会把
 * `node_modules` 里上万个文件一并枚举一遍,能把窗口卡住。挑仓库里**任意**
 * 一个文件最省事 —— 挑了 README、挑了工作簿,都找得回来。
 */
export function findRepoRoot(
  start: string,
  exists: (p: string) => boolean,
  maxUp = 12,
): string | null {
  // 给的是文件还是目录,不必先分清 —— 原地先试一次,不中再往上,结果一样
  let dir = start.replace(/[\\/]+$/, "");
  for (let i = 0; i <= maxUp; i++) {
    if (exists(joinPath(dir, ...GAZ_MARK))) return dir;
    const up = parentOf(dir);
    if (!up || up === dir) return null;
    dir = up;
  }
  return null;
}

/** 这个目录像不像仓库 —— 不像就说一句人话,像回 null */
export function repoProblem(repoDir: string, hasGaz: boolean): string | null {
  if (!repoDir.trim()) return "还没选仓库在哪儿。";
  if (!hasGaz) {
    return (
      "这个文件夹里没有 tools\\gazetteer\\gaz.py —— 多半是选错了。" +
      "要选的是 CN_Map 那个文件夹本身(里头有 src\\、tools\\、" +
      "CN_Electronic_Industry.xlsx)。"
    );
  }
  return null;
}

/** python 在这台机器上怎么敲 —— 按顺序试,谁先应声算谁 */
export const PYTHON_TRIES = ["python", "py", "python3"];

export function pickPython(tried: { cmd: string; ok: boolean }[]): string | null {
  return tried.find((t) => t.ok)?.cmd ?? null;
}

/** `git rev-parse --abbrev-ref HEAD` 读出来那一支的名字 */
export function branchOf(out: string): string {
  const s = out.trim().split("\n")[0]?.trim() ?? "";
  // 没挂在任何分支上时 git 回 "HEAD",那不是分支名
  return s && s !== "HEAD" ? s : "";
}

export interface Detected {
  repoDir: string;
  python: string;
  branch: string;
  vaultUnits: string;
}

/** 认出来的几样,说成一段给人看的话 */
export function summarize(d: Detected): string {
  const rows: string[] = [
    "仓库目录    " + d.repoDir,
    "python      " + (d.python || "没找着 —— 得自己填"),
    "干活那一支  " + (d.branch || "没认出来 —— 用默认的"),
  ];
  if (d.vaultUnits) rows.push("库里厂所笔记 " + d.vaultUnits);
  return rows.join("\n");
}
