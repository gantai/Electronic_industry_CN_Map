/* 把仓库里打包好的插件抄进库 —— 也就是 `装.ps1` 干的那件事,搬进面板里。

   从前更新一回插件要:拉取 → 开 PowerShell 跑 `.\装.ps1` → 回 Obsidian
   把插件关一下再开。三样里漏掉任何一样,面板上看着就是「什么也没变」——
   而且**看不出**是没装上,人只会以为改动没生效。这个项目里为这件事来回过三趟。

   规矩是「除了装更新,动手一律走插件」(见仓库根的 CLAUDE.md)。头一回装
   还得靠 `装.ps1`（那时插件还不在库里,没有面板可点),**装过一回之后的更新
   就归这儿**:抄文件、重载插件,一按了事。

   这个模块一行 Obsidian、一行 fs 也不碰 —— 抄文件、算摘要都由外头传进来,
   所以测得动。 */

export const PLUGIN_ID = "dianzi-gongye-ditu";

/** 装一套插件就这三个文件 —— 跟 `装.ps1` 抄的是同一份 */
export const PLUGIN_FILES = ["main.js", "manifest.json", "styles.css"];

export interface Pair {
  name: string;
  /** 仓库里那一份 */
  from: string;
  /** 库里那一份 */
  to: string;
}

function join(base: string, parts: string[]): string {
  const b = base.replace(/[\\/]+$/, "");
  const sep = b.includes("\\") ? "\\" : "/";
  return [b, ...parts].join(sep);
}

/** 仓库里插件源码那一层 */
export function srcDir(repoDir: string): string {
  return join(repoDir, ["tools", "obsidian-plugin"]);
}

/** 库里插件装到哪一层 */
export function destDir(vaultRoot: string): string {
  return join(vaultRoot, [".obsidian", "plugins", PLUGIN_ID]);
}

/** 要抄的三对路径。仓库或库不知道在哪儿就空着 —— 抄不了,也不该瞎猜 */
export function plan(repoDir: string, vaultRoot: string): Pair[] {
  if (!repoDir || !vaultRoot) return [];
  return PLUGIN_FILES.map((name) => ({
    name,
    from: join(srcDir(repoDir), [name]),
    to: join(destDir(vaultRoot), [name]),
  }));
}

export interface Diff {
  name: string;
  /** 仓库里那一份在不在 */
  hasSrc: boolean;
  /** 库里那一份在不在 */
  hasDest: boolean;
  /** 两边一模一样 */
  same: boolean;
}

/** 库里装着的,跟仓库里那一份一样不一样。
 *
 *  `digest` 读一个文件回它的摘要;文件不在回 null。 */
export function compare(pairs: Pair[], digest: (p: string) => string | null): Diff[] {
  return pairs.map((p) => {
    const a = digest(p.from);
    const b = digest(p.to);
    return { name: p.name, hasSrc: a !== null, hasDest: b !== null, same: a !== null && a === b };
  });
}

export type InstallState = "same" | "stale" | "missing" | "nosrc" | "unknown";

/** 一句话说清眼下是哪种情形 —— 面板上就摆这一句。 */
export function state(diffs: Diff[]): InstallState {
  if (!diffs.length) return "unknown";
  if (diffs.some((d) => !d.hasSrc)) return "nosrc";
  if (diffs.every((d) => !d.hasDest)) return "missing";
  return diffs.every((d) => d.same) ? "same" : "stale";
}

export function stateText(st: InstallState): string {
  switch (st) {
    case "same":
      return "插件是仓库里那一份,没有更新要装。";
    case "stale":
      return "**仓库里的插件比装着的新** —— 按「装上新的」,一按了事(会自己重载)。";
    case "missing":
      return "库里还没装过这个插件?头一回请在 PowerShell 里跑 tools\\obsidian-plugin\\装.ps1。";
    case "nosrc":
      return "仓库里找不着打包好的 main.js —— 先「拉取更新」把仓库拉全。";
    default:
      return "还说不上 —— 仓库或库的位置没认出来。";
  }
}
