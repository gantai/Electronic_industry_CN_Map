/* 设置:路径几条,别的一概不问。 */

import { App, PluginSettingTab, Setting } from "obsidian";
import type { Ctx } from "./steps";
import type GazPlugin from "./main";

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

/** 设置齐不齐 —— 缺哪一样,回一句话;齐了回 null */
export function settingsGap(s: GazSettings): string | null {
  if (!s.repoDir.trim()) return "还没说仓库在哪儿 —— 先去设置里填「仓库目录」。";
  return null;
}

export class GazSettingTab extends PluginSettingTab {
  plugin: GazPlugin;

  constructor(app: App, plugin: GazPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  private text(
    name: string,
    desc: string,
    placeholder: string,
    get: () => string,
    set: (v: string) => void,
  ) {
    new Setting(this.containerEl)
      .setName(name)
      .setDesc(desc)
      .addText((t) =>
        t
          .setPlaceholder(placeholder)
          .setValue(get())
          .onChange(async (v) => {
            set(v);
            await this.plugin.saveSettings();
          }),
      );
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("p", {
      cls: "gaz-settings-note",
      text:
        "这个插件不自己抽数据 —— 它替你跑仓库里的 gaz(Python)。" +
        "所以 Python 与 openpyxl 还是要装;装了没有,面板上「本机装了什么」那一条会说。",
    });

    this.text(
      "仓库目录",
      "CN_Map 在哪儿。底下每一条命令都在这个目录里跑。",
      "D:\\Coding\\CN_Map",
      () => this.plugin.settings.repoDir,
      (v) => (this.plugin.settings.repoDir = v.trim()),
    );

    this.text(
      "python 怎么敲",
      "多半就是 python。装了好几个版本、或者用虚拟环境的,写整条路径。",
      "python",
      () => this.plugin.settings.python,
      (v) => (this.plugin.settings.python = v.trim()),
    );

    this.text(
      "转换稿目录",
      "空着就是仓库里的 转换稿\\。稿子放在库里的话,写 D:\\Archive\\转换稿。",
      "(空着用仓库里的)",
      () => this.plugin.settings.draftsDir,
      /* 不走 normalizePath —— 那是给库内相对路径用的,
         拿它套 D:\\Archive\\转换稿 会把反斜杠换成斜杠 */
      (v) => (this.plugin.settings.draftsDir = v.trim()),
    );

    this.text(
      "库里厂所笔记那一支",
      "gaz push / pull 往这儿写。不用这两条就空着。",
      "D:\\Archive\\厂所",
      () => this.plugin.settings.vaultUnits,
      (v) => (this.plugin.settings.vaultUnits = v.trim()),
    );

    this.text(
      "在哪一支上干活",
      "改动提交到这一支;上线是把它合进 main。",
      DEFAULTS.branch,
      () => this.plugin.settings.branch,
      (v) => (this.plugin.settings.branch = v.trim()),
    );

    new Setting(containerEl)
      .setName("只看不动的那几步也先确认")
      .setDesc("默认不问 —— 看状态、验一验这类一个格子也不动,拦一道纯属碍事。")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.confirmReadOnly).onChange(async (v) => {
          this.plugin.settings.confirmReadOnly = v;
          await this.plugin.saveSettings();
        }),
      );
  }
}
