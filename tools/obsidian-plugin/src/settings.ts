/* 设置:路径几条,别的一概不问。 */

import { App, Modal, PluginSettingTab, Setting, TFolder } from "obsidian";
import type GazPlugin from "./main";
import { FIELDS, absFolders } from "./config";

/* 纯的那几样搬去了 config.ts(那边测得动)。这儿照旧转出去,
   别处的 import 一个也不必改。 */
export { DEFAULTS, FIELDS, ctxOf, settingsGap } from "./config";
export type { GazSettings, SettingField } from "./config";

/** 库里的文件夹,连整条路径 —— 「库」那几栏从这儿挑,不必自己打字。
 *  `base` 是库自己在硬盘上的位置;问不出就只好手填。 */
export function vaultFolders(app: App, base: string): string[] {
  const rel: string[] = [];
  for (const f of app.vault.getAllLoadedFiles()) {
    if (f instanceof TFolder) rel.push(f.path);
  }
  return absFolders(base, rel);
}

/** 把那几栏画出来。设置页与面板上那张卡片共用这一份。 */
export function renderFields(
  where: HTMLElement,
  app: App,
  plugin: GazPlugin,
  base: string,
): void {
  for (const f of FIELDS) {
    const s = new Setting(where).setName(f.name).setDesc(f.desc);
    if (f.kind === "toggle") {
      s.addToggle((t) =>
        t.setValue(plugin.settings[f.key] as boolean).onChange(async (v) => {
          (plugin.settings[f.key] as boolean) = v;
          await plugin.saveSettings();
        }),
      );
      continue;
    }
    let box: HTMLInputElement | null = null;
    s.addText((t) => {
      t.setPlaceholder(f.placeholder ?? "")
        .setValue(plugin.settings[f.key] as string)
        .onChange(async (v) => {
          /* 不走 normalizePath —— 那是给库内相对路径用的,
             拿它套 D:\\Archive\\转换稿 会把反斜杠换成斜杠 */
          (plugin.settings[f.key] as string) = v.trim();
          await plugin.saveSettings();
        });
      box = t.inputEl;
    });
    if (f.kind !== "folder") continue;
    const dirs = vaultFolders(app, base);
    if (!dirs.length) continue;
    s.addDropdown((d) => {
      d.addOption("", "—— 挑库里的一个文件夹 ——");
      for (const full of dirs) d.addOption(full, full === base ? "(库根)" : full.slice(base.length + 1));
      d.setValue("");
      d.onChange(async (v) => {
        if (!v) return;
        (plugin.settings[f.key] as string) = v;
        if (box) box.value = v;
        await plugin.saveSettings();
      });
    });
  }
}

/** 面板上那张设置卡片 —— 不必再去 设置 → 第三方插件 里翻。 */
export class SettingsModal extends Modal {
  constructor(app: App, private plugin: GazPlugin, private base: string) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.addClass("gaz-form");
    contentEl.createEl("h3", { text: "设置" });
    contentEl.createEl("p", {
      cls: "gaz-blurb",
      text: "改了就算数,不必按「好」。同样几栏在 设置 → 第三方插件 底下也有。",
    });
    renderFields(contentEl, this.app, this.plugin, this.base);
    new Setting(contentEl).addButton((b) =>
      b.setButtonText("好了").setCta().onClick(() => this.close()),
    );
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

export class GazSettingTab extends PluginSettingTab {
  plugin: GazPlugin;

  constructor(app: App, plugin: GazPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("p", {
      cls: "gaz-settings-note",
      text:
        "这个插件不自己抽数据 —— 它替你跑仓库里的 gaz(Python)。" +
        "所以 Python 与 openpyxl 还是要装;装了没有,面板上「本机装了什么」那一条会说。" +
        "同样几栏在面板顶上「设置」那一条里也改得动。",
    });

    const a = this.app.vault.adapter as { getBasePath?: () => string };
    renderFields(containerEl, this.app, this.plugin,
                 typeof a.getBasePath === "function" ? a.getBasePath() : "");
  }
}
