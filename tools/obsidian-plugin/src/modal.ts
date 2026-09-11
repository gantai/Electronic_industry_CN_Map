/* 两个对话框:填参数的、问一句「真跑?」的。 */

import { App, Modal, Setting } from "obsidian";
import type { Field, Step, Vals } from "./steps";
import { missing } from "./steps";

/** Electron 给 File 挂了个 path,标准浏览器里没有 —— 选文件拿整条路径全靠它 */
type ElectronFile = File & { path?: string };

export class StepFormModal extends Modal {
  private vals: Vals = {};
  private err: HTMLElement | null = null;

  constructor(
    app: App,
    private step: Step,
    private seed: Vals,
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
      /* Obsidian 里开系统的选文件框,靠的是一个藏起来的 <input type=file>。
         Electron 给选中的 File 挂了 .path,拿的就是那条整路径。 */
      const picker = parent.createEl("input", { type: "file" });
      picker.style.display = "none";
      if (f.exts?.length) picker.accept = f.exts.map((e) => "." + e).join(",");
      picker.addEventListener("change", () => {
        const file = picker.files?.[0] as ElectronFile | undefined;
        if (file?.path) {
          this.vals[f.key] = file.path;
          if (box) box.value = file.path;
        }
      });
      s.addButton((b) => b.setButtonText("浏览…").onClick(() => picker.click()));
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
