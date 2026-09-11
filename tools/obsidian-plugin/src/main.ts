/* 插件本体:把面板、对话框、跑命令这三头接起来。

   它自己不抽一条数据 —— 抽数据的是仓库里的 gaz(Python)。这边只管
   少让人敲字:该问的问清楚,该拦的拦住,跑出来的字摆在眼前。 */

import { Notice, Plugin, WorkspaceLeaf } from "obsidian";
import { DEFAULTS, GazSettingTab, ctxOf, settingsGap, type GazSettings } from "./settings";
import { STEPS, missing, type Cmd, type Step, type Vals } from "./steps";
import { blockPublish, commitPlan, pendingCmd, publishPlan, pullPlan, statusCmd, type Plan } from "./gitops";
import { capture, describe, runAll, type RunHandle } from "./runner";
import { ConfirmModal, PromptModal, StepFormModal } from "./modal";
import { FlowView, VIEW_TYPE } from "./view";

export default class GazPlugin extends Plugin {
  settings: GazSettings = { ...DEFAULTS };
  /** 上回每一步填过什么 —— 同一章往往要跑好几遍,不该每次从头填 */
  private seeds: Record<string, Vals> = {};
  private running: RunHandle | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.registerView(VIEW_TYPE, (leaf: WorkspaceLeaf) => new FlowView(leaf, this));
    this.addSettingTab(new GazSettingTab(this.app, this));

    this.addRibbonIcon("map", "电子工业地图流程", () => void this.openPanel());
    this.addCommand({
      id: "open-panel",
      name: "打开流程面板",
      callback: () => void this.openPanel(),
    });

    /* 每一步各自也是一条命令 —— Ctrl+P 敲得到,配得上快捷键 */
    for (const s of STEPS) {
      this.addCommand({
        id: "step-" + s.id,
        name: (s.n ? s.n + " · " : "") + s.name,
        callback: () => void this.runStep(s),
      });
    }
    this.addCommand({ id: "git-commit", name: "提交改动", callback: () => void this.doCommit() });
    this.addCommand({ id: "git-pull", name: "拉取更新", callback: () => void this.doPull() });
    this.addCommand({
      id: "git-publish",
      name: "第八步 · 合进 main 上线",
      callback: () => void this.doPublish(),
    });
  }

  onunload(): void {
    this.running?.stop();
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULTS, await this.loadData());
  }
  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  // ---------------------------------------------------------------- 面板

  async openPanel(): Promise<FlowView | null> {
    const { workspace } = this.app;
    let leaf = workspace.getLeavesOfType(VIEW_TYPE)[0];
    if (!leaf) {
      const right = workspace.getRightLeaf(false);
      if (!right) return null;
      await right.setViewState({ type: VIEW_TYPE, active: true });
      leaf = right;
    }
    workspace.revealLeaf(leaf);
    const view = leaf.view;
    return view instanceof FlowView ? view : null;
  }

  private async view(): Promise<FlowView | null> {
    return this.openPanel();
  }

  stop(): void {
    this.running?.stop();
  }

  // ---------------------------------------------------------------- 跑

  /** 设置齐不齐。不齐就说一句,并把设置页打开 —— 光一句「没配好」太不客气 */
  private ready(): boolean {
    const gap = settingsGap(this.settings);
    if (gap) {
      new Notice(gap, 8000);
      return false;
    }
    return true;
  }

  async runStep(step: Step): Promise<void> {
    if (!this.ready()) return;

    /* 「核对」那一步不跑命令,是拿系统默认的程序把工作簿开起来 —— 多半是 Excel。
       这一步没有捷径,也不该有:判断的活儿归人。 */
    if (step.id === "review") {
      new StepFormModal(this.app, step, this.seeds[step.id] ?? {}, (v) => {
        this.seeds[step.id] = v;
        void this.openExternally(v.xlsx);
      }).open();
      return;
    }

    const go = (v: Vals) => {
      this.seeds[step.id] = v;
      const cmds = step.build(v, ctxOf(this.settings));
      const needAsk = !step.readOnly || this.settings.confirmReadOnly;
      if (!needAsk) return void this.exec(cmds, step.name);
      new ConfirmModal(
        this.app,
        {
          title: (step.n ? step.n + " · " : "") + step.name,
          why: step.blurb,
          lines: cmds.map(describe),
          cta: "跑",
        },
        () => void this.exec(cmds, step.name),
      ).open();
    };

    if (!step.fields?.length) {
      go({});
      return;
    }
    new StepFormModal(this.app, step, this.seeds[step.id] ?? {}, (v) => {
      const gap = missing(step, v);
      if (gap) {
        new Notice(gap);
        return;
      }
      go(v);
    }).open();
  }

  private async openExternally(path: string): Promise<void> {
    try {
      /* electron 由宿主提供,打包时排除在外(见 esbuild.config.mjs) */
      const electron = require("electron");
      await electron.shell.openPath(path);
      new Notice("开了 " + path + " —— 核完存盘,回来跑第五步。");
    } catch (e) {
      new Notice("开不了:" + String(e), 8000);
    }
  }

  private async exec(cmds: Cmd[], what: string): Promise<number> {
    if (this.running) {
      new Notice("还有一条在跑,等它完,或者按「停」。");
      return -1;
    }
    const v = await this.view();
    if (!v) return -1;
    v.busy(true, what);
    this.running = runAll(cmds, {
      line: (t, s) => v.write(t, s === "err" ? "err" : "out"),
      start: (c) => v.announce(c),
    });
    const code = await this.running.done;
    this.running = null;
    v.busy(false);
    v.write(code === 0 ? "—— 完了。" : "—— 没成(退出码 " + code + ")。", code === 0 ? "note" : "err");
    return code;
  }

  private async runPlan(plan: Plan, opts: { facts?: string; danger?: boolean; cta?: string } = {}) {
    new ConfirmModal(
      this.app,
      {
        title: plan.title,
        why: plan.why,
        lines: plan.cmds.map(describe),
        facts: opts.facts,
        danger: opts.danger,
        cta: opts.cta ?? "跑",
      },
      () => void this.exec(plan.cmds, plan.title),
    ).open();
  }

  // ---------------------------------------------------------------- git

  async doCommit(): Promise<void> {
    if (!this.ready()) return;
    const ctx = ctxOf(this.settings);
    const st = await capture(statusCmd(ctx));
    if (st.code !== 0) {
      new Notice("git 跑不动 —— 仓库目录填对了吗?", 8000);
      return;
    }
    if (!st.out.trim()) {
      new Notice("没有要提交的 —— 一个文件也没动。");
      return;
    }
    new PromptModal(
      this.app,
      {
        title: "提交改动",
        label: "这一笔记什么",
        placeholder: "补录《某某志》第三章",
      },
      (msg) => void this.runPlan(commitPlan(ctx, msg), { facts: st.out.trim() }),
    ).open();
  }

  async doPull(): Promise<void> {
    if (!this.ready()) return;
    const ctx = ctxOf(this.settings);
    const st = await capture(statusCmd(ctx));
    const facts = st.out.trim()
      ? "有改动还没提交:\n" + st.out.trim() + "\n\n(工作簿是二进制,撞上了只能留一边 —— 先提交更稳妥。)"
      : undefined;
    await this.runPlan(pullPlan(ctx), { facts });
  }

  /** 上线。**拦一道再跑** —— 这一串从前手敲错过,见 gitops.ts。 */
  async doPublish(): Promise<void> {
    if (!this.ready()) return;
    const ctx = ctxOf(this.settings);
    const v = await this.view();
    v?.busy(true, "看要上线什么");
    const st = await capture(statusCmd(ctx));
    await capture({ exe: "git", args: ["fetch", "origin", "main"], cwd: ctx.repoDir });
    const pend = await capture(pendingCmd(ctx));
    v?.busy(false);

    if (st.code !== 0 || pend.code !== 0) {
      new Notice("git 问不出状态 —— 仓库目录填对了吗?", 8000);
      return;
    }
    const stop = blockPublish(st.out, pend.out);
    if (stop) {
      new Notice(stop, 12000);
      v?.write("上线拦下了:" + stop, "err");
      return;
    }
    const lines = pend.out.trim().split("\n").filter(Boolean);
    await this.runPlan(publishPlan(ctx), {
      facts: "这 " + lines.length + " 条要上线:\n" + lines.join("\n"),
      danger: true,
      cta: "上线",
    });
  }
}
