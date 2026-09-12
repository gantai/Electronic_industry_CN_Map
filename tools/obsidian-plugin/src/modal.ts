/* 两个对话框:填参数的、问一句「真跑?」的。 */

import { App, Modal, Setting } from "obsidian";
import { existsSync, readdirSync, statSync } from "node:fs";
import type { Ctx, Field, Step, Vals } from "./steps";
import { draftsDir, missing } from "./steps";
import { baseName, listDrafts, type Fs } from "./setup";

/** Electron 给 File 挂了个 path,标准浏览器里没有 —— 选文件拿整条路径全靠它 */
type ElectronFile = File & { path?: string };

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

    if (f.type === "path") {
      /* Obsidian 里开系统的选文件框,靠的是一个 <input type=file>。
         **别拿 display:none 藏它** —— 藏成那样,Electron 有的机器上压根不弹窗,
         按了没反应(头一回设置那张卡片上栽过一次)。挪到屏幕外头,还点得动。
         就算这样也不保准,所以贴路径那条永远开着。 */
      const picker = parent.createEl("input", { type: "file" });
      picker.style.position = "fixed";
      picker.style.left = "-10000px";
      picker.style.width = "1px";
      picker.style.height = "1px";
      picker.style.opacity = "0";
      if (f.exts?.length) picker.accept = f.exts.map((e) => "." + e).join(",");
      picker.addEventListener("change", () => {
        const file = picker.files?.[0] as ElectronFile | undefined;
        if (!file?.path) {
          s.setDesc("这台机器上弹不出选文件框 —— 把整条路径贴进上头那一栏。");
          return;
        }
        this.vals[f.key] = file.path;
        if (box) box.value = file.path;
      });
      s.addButton((b) =>
        b.setButtonText("浏览…")
          .setTooltip("有的机器上弹不出窗;弹不出就贴路径")
          .onClick(() => picker.click()));
    }

    if (f.type === "pick") {
      /* 稿子与待核工作簿都在转换稿那一个目录里 —— 列出来让人挑,
         不必去碰那个不保准的选文件框。列不出来(目录空着、还没转稿子)
         就说一句,那一栏照旧手填。 */
      const dir = draftsDir(this.ctx);
      const found = listDrafts(dir, f.exts ?? [], REAL_FS);
      if (!found.length) {
        s.setDesc((f.hint ? f.hint + " " : "") +
          "(" + dir + " 里眼下没有 " + (f.exts ?? []).join(" / ") + " —— 手填整条路径)");
        return;
      }
      s.addDropdown((d) => {
        d.addOption("", "—— 挑一份(" + found.length + " 份)——");
        for (const full of found) d.addOption(full, baseName(full));
        d.setValue(found.includes(this.vals[f.key]) ? this.vals[f.key] : "");
        d.onChange((v) => {
          if (!v) return;
          this.vals[f.key] = v;
          if (box) box.value = v;
        });
      });
    }
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
