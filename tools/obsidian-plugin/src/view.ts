/* 右边那块面板:八步一条一条摆着,底下是跑出来的字。 */

import { ItemView, WorkspaceLeaf, setIcon } from "obsidian";
import { STEPS, groups, type Cmd, type Step } from "./steps";
import { describe } from "./runner";
import { settingsGap } from "./settings";
import type GazPlugin from "./main";

export const VIEW_TYPE = "gaz-flow";

/** 输出留多少行 —— 一本志转下来能吐上万行,全留着面板会卡 */
const MAX_LINES = 4000;

export class FlowView extends ItemView {
  private logEl!: HTMLElement;
  private setupEl!: HTMLElement;
  private statusEl!: HTMLElement;
  private stopBtn!: HTMLButtonElement;
  private lines = 0;

  constructor(leaf: WorkspaceLeaf, private plugin: GazPlugin) {
    super(leaf);
  }

  getViewType(): string {
    return VIEW_TYPE;
  }
  getDisplayText(): string {
    return "电子工业地图流程";
  }
  getIcon(): string {
    return "map";
  }

  async onOpen(): Promise<void> {
    const root = this.contentEl;
    root.empty();
    root.addClass("gaz-view");

    const head = root.createDiv({ cls: "gaz-head" });
    head.createEl("div", { cls: "gaz-title", text: "电子工业地图流程" });
    head.createEl("div", {
      cls: "gaz-sub",
      text: "志书 PDF → 待核工作簿 → 总表 → 上线",
    });

    this.setupEl = root.createDiv({ cls: "gaz-setup" });

    const steps = root.createDiv({ cls: "gaz-steps" });
    for (const g of groups()) {
      steps.createEl("div", { cls: "gaz-group", text: g });
      for (const s of STEPS.filter((x) => x.group === g)) this.stepRow(steps, s);
    }

    /* git 那几条不在 STEPS 里 —— 它们不是 gaz,确认的方式也不一样 */
    steps.createEl("div", { cls: "gaz-group", text: "上线" });
    this.actionRow(steps, "提交改动", "把眼下改过的存进这一支。", () =>
      this.plugin.doCommit(),
    );
    this.actionRow(steps, "拉取更新", "把远端这一支的新提交拿下来。", () =>
      this.plugin.doPull(),
    );
    this.actionRow(
      steps,
      "第八步 · 合进 main 上线",
      "只有这一步能让线上那张图变。跑之前先摆出要发布的是哪几条。",
      () => this.plugin.doPublish(),
      true,
    );

    const bar = root.createDiv({ cls: "gaz-bar" });
    this.statusEl = bar.createEl("span", { cls: "gaz-status", text: "闲着" });
    this.stopBtn = bar.createEl("button", { cls: "gaz-stop", text: "停" });
    this.stopBtn.disabled = true;
    this.stopBtn.onclick = () => this.plugin.stop();
    const clear = bar.createEl("button", { cls: "gaz-clear", text: "清屏" });
    clear.onclick = () => this.clear();

    this.logEl = root.createDiv({ cls: "gaz-log" });
    this.write("按一条,它跑什么会先摆出来。", "note");
    this.refreshSetup();
  }

  /** 设置齐了就把顶上那张卡片收起来,没齐就摆着 —— 不必等人点了才说 */
  refreshSetup(): void {
    if (!this.setupEl) return;
    this.setupEl.empty();
    const gap = settingsGap(this.plugin.settings);
    if (!gap) {
      this.setupEl.addClass("is-done");
      return;
    }
    this.setupEl.removeClass("is-done");
    this.setupEl.createEl("div", { cls: "gaz-setup-title", text: "还没认仓库" });
    this.setupEl.createEl("div", {
      cls: "gaz-setup-text",
      text: "这个插件替你跑仓库里的 gaz,得先知道仓库在哪儿。按一下,挑个文件就好。",
    });
    const b = this.setupEl.createEl("button", { cls: "mod-cta", text: "认一下仓库" });
    b.onclick = () => void this.plugin.openSetup();
  }

  private stepRow(parent: HTMLElement, s: Step): void {
    const row = parent.createDiv({ cls: "gaz-step" });
    const btn = row.createEl("button", { cls: "gaz-step-btn" });
    const icon = btn.createSpan({ cls: "gaz-step-icon" });
    setIcon(icon, s.readOnly ? "eye" : "play");
    const txt = btn.createDiv({ cls: "gaz-step-text" });
    txt.createEl("div", {
      cls: "gaz-step-name",
      text: (s.n ? s.n + " · " : "") + s.name,
    });
    txt.createEl("div", { cls: "gaz-step-blurb", text: s.blurb });
    btn.onclick = () => this.plugin.runStep(s);
  }

  private actionRow(
    parent: HTMLElement,
    name: string,
    blurb: string,
    go: () => void,
    danger = false,
  ): void {
    const row = parent.createDiv({ cls: "gaz-step" });
    const btn = row.createEl("button", {
      cls: "gaz-step-btn" + (danger ? " gaz-danger" : ""),
    });
    const icon = btn.createSpan({ cls: "gaz-step-icon" });
    setIcon(icon, danger ? "upload-cloud" : "git-branch");
    const txt = btn.createDiv({ cls: "gaz-step-text" });
    txt.createEl("div", { cls: "gaz-step-name", text: name });
    txt.createEl("div", { cls: "gaz-step-blurb", text: blurb });
    btn.onclick = go;
  }

  // ---- 输出

  clear(): void {
    this.logEl.empty();
    this.lines = 0;
  }

  write(text: string, kind: "out" | "err" | "note" | "cmd" = "out"): void {
    const el = this.logEl.createEl("div", { cls: "gaz-line gaz-" + kind });
    el.setText(text || " ");
    this.lines++;
    /* 超了就从头上砍 —— 留着尾巴,人看的总是最后那几行 */
    while (this.lines > MAX_LINES && this.logEl.firstChild) {
      this.logEl.removeChild(this.logEl.firstChild);
      this.lines--;
    }
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  announce(cmd: Cmd): void {
    this.write("› " + describe(cmd), "cmd");
  }

  busy(on: boolean, what = ""): void {
    this.statusEl.setText(on ? "跑着:" + what : "闲着");
    this.statusEl.toggleClass("is-busy", on);
    this.stopBtn.disabled = !on;
  }

  async onClose(): Promise<void> {
    this.contentEl.empty();
  }
}
