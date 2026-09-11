/* git 那几步 —— 同样不碰 Obsidian,同样测得动。

   这里最要紧的是**上线**那一串。手敲过一次,漏了 `git merge --ff-only origin/main`
   一句:本地 main 落后三十七个提交,合上去推不动,报 non-fast-forward;
   更糟的是那一次合进去的东西里,压根没有当时要发布的那个改动。
   所以这一串写死在这儿,少一句都不行,顺序也不许动。 */

import { type Cmd, type Ctx, git } from "./steps";

export interface Plan {
  title: string;
  /** 跑之前摆给人看的那段话 */
  why: string;
  cmds: Cmd[];
}

/** `git status --short` 读出来:干净不干净、动了哪几个文件 */
export function parseStatus(out: string): { clean: boolean; files: string[] } {
  const files = out
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => l.replace(/^\S+\s+/, ""));
  return { clean: files.length === 0, files };
}

/** `git log --oneline A..B` 读出来:几条、都是什么 */
export function parseLog(out: string): { n: number; lines: string[] } {
  const lines = out.split("\n").map((l) => l.trim()).filter(Boolean);
  return { n: lines.length, lines };
}

/** 看状态:落后几个、工作簿动过没有。只读。 */
export function statusPlan(ctx: Ctx): Plan {
  return {
    title: "看 git 状态",
    why: "取远端,看这一支跟 main 各自到了哪儿。一个字节也不写。",
    cmds: [
      git(ctx, ["fetch", "origin"]),
      git(ctx, ["status", "--short"]),
      git(ctx, ["log", "--oneline", "-5", ctx.branch]),
    ],
  };
}

/** 还有什么没上线 —— 合进 main 之前先看这个 */
export function pendingCmd(ctx: Ctx): Cmd {
  return git(ctx, ["log", "--oneline", "origin/main.." + ctx.branch]);
}

export function statusCmd(ctx: Ctx): Cmd {
  return git(ctx, ["status", "--short"]);
}

/** 提交:改的东西是这一步存下来的,不是别的哪一步。 */
export function commitPlan(ctx: Ctx, message: string): Plan {
  return {
    title: "提交改动",
    why: "把眼下改过的东西存进这一支。存下来才退得回去。",
    cmds: [
      git(ctx, ["add", "-A"]),
      git(ctx, ["commit", "-m", message]),
      git(ctx, ["push", "-u", "origin", ctx.branch]),
    ],
  };
}

/** 拉取更新。**先提交再拉** —— 工作簿是二进制,冲突了只能留一边。 */
export function pullPlan(ctx: Ctx): Plan {
  return {
    title: "拉取更新",
    why: "把远端这一支的新提交拿下来。工作簿有没提交的改动时,git 会自己拒绝。",
    cmds: [
      git(ctx, ["fetch", "origin", ctx.branch]),
      git(ctx, ["merge", "--ff-only", "origin/" + ctx.branch]),
    ],
  };
}

/**
 * 上线:合进 main。**只有这一步能让线上那张图变。**
 *
 * 六句,一句也不能少:
 *   1 取远端的 main
 *   2 切到 main
 *   3 **`--ff-only` 把本地 main 追平远端** —— 漏了这句就是那次的 non-fast-forward
 *   4 把干活这一支合进来
 *   5 推
 *   6 切回干活这一支 —— 不切回去,下回一动手就改在 main 上了
 */
export function publishPlan(ctx: Ctx): Plan {
  return {
    title: "合进 main 上线",
    why:
      "GitHub 只认 main 上有新提交。合完两三分钟,线上那张图就是新的。\n" +
      "第三句 `merge --ff-only origin/main` 是把本地 main 先追平远端 —— " +
      "从前漏过这一句,推不上去,而且合进去的还不是要发布的那个改动。",
    cmds: [
      git(ctx, ["fetch", "origin", "main"]),
      git(ctx, ["checkout", "main"]),
      git(ctx, ["merge", "--ff-only", "origin/main"]),
      git(ctx, ["merge", ctx.branch]),
      git(ctx, ["push", "origin", "main"]),
      git(ctx, ["checkout", ctx.branch]),
    ],
  };
}

/**
 * 上线之前拦一道。回一句拦住的话,拦不住回 null。
 *
 * 两样过不去:
 * * **工作簿或别的文件改了没提交** —— 底下要 `checkout main`,带着没提交的改动切
 *   分支,轻则切不过去,重则把改动带到 main 上。先提交。
 * * **没有什么可上线的** —— 这一支跟 origin/main 一样,合了也是白合。
 */
export function blockPublish(status: string, pending: string): string | null {
  const st = parseStatus(status);
  if (!st.clean) {
    return (
      "有改动还没提交(" + st.files.slice(0, 3).join("、") +
      (st.files.length > 3 ? " 等 " + st.files.length + " 个" : "") +
      ")。**先提交再上线** —— 底下要切到 main,带着没提交的改动切过去,轻则切不动," +
      "重则把它们带到 main 上。"
    );
  }
  if (parseLog(pending).n === 0) {
    return "这一支跟线上那份一模一样,没有什么可上线的。";
  }
  return null;
}
