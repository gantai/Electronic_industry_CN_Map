/* 设置里**不碰 Obsidian 的那一半**:有哪几栏、取值怎么算、缺没缺。

   拆出来是为了测得动 —— 跟 steps.ts / gitops.ts 同一个道理。画界面的那一半
   在 settings.ts,它得 import obsidian,测试里跑不起来。 */

import type { Ctx } from "./steps";
import { joinVault } from "./setup";

export interface GazSettings {
  repoDir: string;
  python: string;
  draftsDir: string;
  vaultUnits: string;
  branch: string;
  /** 面板上是否连只读的那几步也显示确认 */
  confirmReadOnly: boolean;
}

export const DEFAULTS: GazSettings = {
  repoDir: "",
  python: "python",
  draftsDir: "",
  vaultUnits: "",
  branch: "claude/local-gazetteer-ocr-md-extract-po9dtk",
  confirmReadOnly: false,
};

export function ctxOf(s: GazSettings): Ctx {
  return {
    repoDir: s.repoDir.trim(),
    python: s.python.trim() || "python",
    draftsDir: s.draftsDir.trim(),
    vaultUnits: s.vaultUnits.trim(),
    branch: s.branch.trim() || DEFAULTS.branch,
  };
}

/** 每一栏长什么样、怎么讲。**摆成一份**,设置页与面板上那张卡片共用 ——
 *  两处各写一遍,迟早对不上:改了这边忘了那边,人在另一处看见的就是过时的话。 */
export interface SettingField {
  key: keyof GazSettings;
  name: string;
  desc: string;
  placeholder?: string;
  /** text = 一行字;folder = 一行字外加一个「库里的文件夹」下拉;toggle = 开关 */
  kind: "text" | "folder" | "toggle";
}

export const FIELDS: SettingField[] = [
  {
    key: "repoDir", kind: "text",
    name: "仓库目录",
    desc: "CN_Map 在哪儿。底下每一条命令都在这个目录里跑。",
    placeholder: "D:\\Coding\\CN_Map",
  },
  {
    key: "python", kind: "text",
    name: "python 怎么敲",
    desc: "多半就是 python。装了好几个版本、或者用虚拟环境的,写整条路径。",
    placeholder: "python",
  },
  {
    key: "draftsDir", kind: "folder",
    name: "转换稿目录",
    desc: "空着就是仓库里的 转换稿\\。稿子放在库里的话,从底下挑一个库里的文件夹。",
    placeholder: "(空着用仓库里的)",
  },
  {
    key: "vaultUnits", kind: "folder",
    name: "库里厂所笔记那一支",
    desc: "gaz push / pull 往这儿写。从底下挑一个库里的文件夹,或者自己填整条路径" +
          "(填别的库里的路径也行)。不用这两条就空着。",
    placeholder: "D:\\Archive\\厂所",
  },
  {
    key: "branch", kind: "text",
    name: "在哪一支上干活",
    desc: "改动提交到这一支;上线是把它合进 main。",
    placeholder: DEFAULTS.branch,
  },
  {
    key: "confirmReadOnly", kind: "toggle",
    name: "只看不动的那几步也先确认",
    desc: "默认不问 —— 看状态、验一验这类一个格子也不动,拦一道纯属碍事。",
  },
];


/** 设置齐不齐 —— 缺哪一样,回一句话;齐了回 null */
export function settingsGap(s: GazSettings): string | null {
  if (!s.repoDir.trim()) return "还没说仓库在哪儿 —— 先去设置里填「仓库目录」。";
  return null;
}

/** 库里那些文件夹的整条路径,排好序。
 *
 *  `rel` 是库内的相对路径(Obsidian 那头一律正斜杠),`base` 是库自己在硬盘上
 *  的位置。库根也算一条 —— 笔记就摊在库根的人不少。 */
export function absFolders(base: string, rel: string[]): string[] {
  if (!base) return [];
  const out = [base];
  for (const p of rel) {
    if (p && p !== "/") out.push(joinVault(base, p));
  }
  return out.sort();
}
