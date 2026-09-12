/* 两个对话框:填参数的、问一句「真跑?」的。 */

import { App, Modal, Notice, Setting, TFile } from "obsidian";
import { existsSync, readdirSync, statSync } from "node:fs";
import type { Ctx, Field, Step, Vals } from "./steps";
import { draftsDir, missing } from "./steps";
import { baseName, joinVault, listDrafts, type Fs } from "./setup";
import { pickFile } from "./dialog";

/** 真的文件系统,喂给 setup.ts 里那几个纯函数 */
const REAL_FS: Fs = {
  exists: (p) => existsSync(p),
  listDirs: (p) => kids(p, true),
  listFiles: (p) => kids(p, false),
};

function kids(p: string, wantDirs: boolean): string[] {
  try {
    return readdirSync(p, { withFileTypes: true })
      .filter((e) => {
        // 有的盘上 withFileTypes 认不出类型(网络盘、符号链接),退回去 stat 一次
        if (typeof e.isDirectory === "function" && (e.isDirectory() || e.isFile())) {
          return e.isDirectory() === wantDirs;
        }
        try {
          return statSync(p + "/" + e.name).isDirectory() === wantDirs;
        } catch {
          return false;
        }
      })
      .map((e) => e.name);
  } catch {
    return [];
  }
}

export class StepFormModal extends Modal {
  private vals: Vals = {};
  private err: HTMLElement | null = null;

  constructor(
    app: App,
    private step: Step,
    private seed: Vals,
    private ctx: Ctx,
    private onGo: (v: Vals) => void,
  ) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.addClass("gaz-form");
    contentEl.createEl("h3", { text: (this.step.n ? this.step.n + " · " : "") + this.step.name });
    contentEl.createEl("p", { cls: "gaz-blurb", text: this.step.blurb });

    for (const f of this.step.fields ?? []) {
      this.vals[f.key] = this.seed[f.key] ?? f.value ?? "";
      this.row(contentEl, f);
    }

    this.err = contentEl.createEl("div", { cls: "gaz-err" });

    new Setting(contentEl)
      .addButton((b) =>
        b
          .setButtonText("跑")
          .setCta()
          .onClick(() => {
            const gap = missing(this.step, this.vals);
            if (gap) {
              if (this.err) this.err.setText(gap);
              return;
            }
            this.close();
            this.onGo({ ...this.vals });
          }),
      )
      .addButton((b) => b.setButtonText("算了").onClick(() => this.close()));
  }

  private row(parent: HTMLElement, f: Field): void {
    const s = new Setting(parent).setName(f.label + (f.required ? " *" : ""));
    if (f.hint) s.setDesc(f.hint);

    if (f.type === "toggle") {
      s.addToggle((t) =>
        t
          .setValue(this.vals[f.key] === "true")
          .onChange((v) => (this.vals[f.key] = v ? "true" : "false")),
      );
      return;
    }
    if (f.type === "select") {
      s.addDropdown((d) => {
        for (const o of f.options ?? []) d.addOption(o.value, o.label);
        d.setValue(this.vals[f.key] || (f.options?.[0]?.value ?? ""));
        d.onChange((v) => (this.vals[f.key] = v));
      });
      return;
    }

    let box: HTMLInputElement | null = null;
    s.addText((t) => {
      t.setPlaceholder(f.placeholder ?? "")
        .setValue(this.vals[f.key])
        .onChange((v) => (this.vals[f.key] = v));
      if (f.type === "number") t.inputEl.type = "number";
      box = t.inputEl;
    });

    const take = (v: string) => {
      this.vals[f.key] = v;
      if (box) box.value = v;
    };

    if (f.type === "path" || f.browse) {
      /* 开的是 Electron 自己的 `dialog.showOpenDialog`,不是藏起来的
         `<input type=file>` —— 那个在有的机器上按了一点反应也没有,
         这个坑这个项目里栽过三次(见 dialog.ts 开头)。
         开不出来就当场说一句,决不静悄悄什么也不发生。 */
      s.addButton((b) =>
        b.setButtonText("浏览…").onClick(async () => {
          const r = await pickFile(
            { title: f.label, exts: f.exts, startIn: this.vaultRoot() },
            (m) => require(m),
          );
          if (r.unavailable) {
            const say = "这套 Obsidian 里开不出系统的选文件框 —— " +
                        "从下头的单子里挑,或者把整条路径贴进上头那一栏。";
            s.setDesc(say);
            new Notice(say, 8000);
            return;
          }
          if (r.path) take(r.path);
        }));
    }

    if (f.type === "pick") {
      /* **列表是正路。** 稿子与待核工作簿都在转换稿那一个目录里,志书原件在库里 ——
         列出来让人挑,一步也不经系统的对话框,所以一定列得出来。
         列不出来(目录空着、库里没有那种文件)就说一句,那一栏照旧手填。 */
      const fromVault = f.pickFrom === "vault";
      const found = fromVault ? this.vaultFiles(f.exts ?? [])
                              : listDrafts(draftsDir(this.ctx), f.exts ?? [], REAL_FS);
      const where = fromVault ? "库里" : draftsDir(this.ctx) + " 里";
      if (!found.length) {
        s.setDesc((f.hint ? f.hint + " " : "") +
          "(" + where + "眼下没有 " + (f.exts ?? []).join(" / ") + " —— 手填整条路径)");
        return;
      }
      s.addDropdown((d) => {
        d.addOption("", "—— 挑一份(" + found.length + " 份)——");
        for (const full of found) d.addOption(full, baseName(full));
        d.setValue(found.includes(this.vals[f.key]) ? this.vals[f.key] : "");
        d.onChange((v) => {
          if (v) take(v);
        });
      });
    }
  }

  /** 库自己在硬盘上的哪儿。问不出就算了 —— 拼不出整条路径,列表就空着。 */
  private vaultRoot(): string {
    const a = this.app.vault.adapter as { getBasePath?: () => string };
    return typeof a.getBasePath === "function" ? a.getBasePath() : "";
  }

  /** 库里这几种后缀的文件,连整条路径。
   *
   *  Obsidian 自己就把库里的文件都索引着(PDF 它本来就认得、还能翻),
   *  所以这一份单子不必去读磁盘,更不必去碰那个不保准的选文件框。 */
  private vaultFiles(exts: string[]): string[] {
    const base = this.vaultRoot();
    if (!base) return [];
    const want = new Set(exts.map((e) => e.toLowerCase()));
    return this.app.vault
      .getFiles()
      .filter((t: TFile) => want.has((t.extension || "").toLowerCase()))
      .map((t: TFile) => joinVault(base, t.path))
      .sort();
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

export class ConfirmModal extends Modal {
  constructor(
    app: App,
    private opts: {
      title: string;
      why: string;
      /** 要跑的命令,一行一条 —— 摆出来,别让人闭着眼点 */
      lines: string[];
      /** 摆在最上头的一段实情(有几条要上线、工作簿动过没有) */
      facts?: string;
      cta?: string;
      danger?: boolean;
    },
    private onGo: () => void,
  ) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.addClass("gaz-confirm");
    contentEl.createEl("h3", { text: this.opts.title });
    for (const line of this.opts.why.split("\n")) {
      contentEl.createEl("p", { cls: "gaz-blurb", text: line });
    }
    if (this.opts.facts) {
      contentEl.createEl("pre", { cls: "gaz-facts", text: this.opts.facts });
    }
    contentEl.createEl("div", { cls: "gaz-cmds-label", text: "要跑的是这几句:" });
    contentEl.createEl("pre", { cls: "gaz-cmds", text: this.opts.lines.join("\n") });

    new Setting(contentEl)
      .addButton((b) => {
        b.setButtonText(this.opts.cta ?? "跑").onClick(() => {
          this.close();
          this.onGo();
        });
        if (this.opts.danger) b.setWarning();
        else b.setCta();
      })
      .addButton((b) => b.setButtonText("算了").onClick(() => this.close()));
  }

  onClose(): void {
    this.contentEl.empty();
  }
}

export class PromptModal extends Modal {
  private v: string;

  constructor(
    app: App,
    private opts: { title: string; label: string; placeholder?: string; value?: string },
    private onGo: (v: string) => void,
  ) {
    super(app);
    this.v = opts.value ?? "";
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.createEl("h3", { text: this.opts.title });
    new Setting(contentEl).setName(this.opts.label).addText((t) =>
      t
        .setPlaceholder(this.opts.placeholder ?? "")
        .setValue(this.v)
        .onChange((x) => (this.v = x)),
    );
    new Setting(contentEl)
      .addButton((b) =>
        b
          .setButtonText("好")
          .setCta()
          .onClick(() => {
            if (!this.v.trim()) return;
            this.close();
            this.onGo(this.v.trim());
          }),
      )
      .addButton((b) => b.setButtonText("算了").onClick(() => this.close()));
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
