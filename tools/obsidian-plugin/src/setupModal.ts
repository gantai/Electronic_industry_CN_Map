/* 头一回用的那张卡片。
   先前这儿只弹一句「先去设置里填仓库目录」—— 可设置在哪儿,它一个字没说。
   如今设置本身就在这张卡片里办完:挑一个文件,别的几样它自己认。 */

import { App, Modal, Notice, Setting } from "obsidian";
import { existsSync } from "node:fs";
import {
  GAZ_MARK, branchOf, findRepoRoot, joinPath, pickPython,
  PYTHON_TRIES, repoProblem, summarize, type Detected,
} from "./setup";
import { capture } from "./runner";
import type { GazSettings } from "./settings";

type ElectronFile = File & { path?: string };

export class SetupModal extends Modal {
  private repo: string;
  private box: HTMLInputElement | null = null;
  private say: HTMLElement | null = null;
  private okBtn: { setDisabled(v: boolean): unknown } | null = null;
  private found: Detected | null = null;

  constructor(
    app: App,
    settings: GazSettings,
    /** 库自己在哪儿 —— 猜「库里厂所笔记那一支」要用 */
    private vaultRoot: string,
    private onSave: (d: Detected) => Promise<void>,
  ) {
    super(app);
    this.repo = settings.repoDir;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.addClass("gaz-form");
    contentEl.createEl("h3", { text: "头一回用:先认一下仓库在哪儿" });
    contentEl.createEl("p", {
      cls: "gaz-blurb",
      text:
        "这个插件替你跑仓库里的 gaz(Python),所以得先知道仓库在哪儿。" +
        "只此一样要问 —— python 怎么敲、在哪一支上干活,它自己认。",
    });

    const s = new Setting(contentEl)
      .setName("仓库目录")
      .setDesc("CN_Map 那个文件夹,如 D:\\Coding\\CN_Map");
    s.addText((t) => {
      t.setPlaceholder("D:\\Coding\\CN_Map")
        .setValue(this.repo)
        .onChange((v) => {
          this.repo = v.trim();
          this.check();
        });
      this.box = t.inputEl;
      t.inputEl.style.width = "260px";
    });

    /* 让人挑**仓库里随便一个文件**,再从它往上找到仓库根。
       挑整个文件夹会把 node_modules 里上万个文件枚举一遍,能把窗口卡住;
       指名去挑 tools\gazetteer\gaz.py 又太难为人。挑 README、挑工作簿,都行。 */
    const picker = contentEl.createEl("input", { type: "file" });
    picker.style.display = "none";
    picker.addEventListener("change", () => {
      const f = picker.files?.[0] as ElectronFile | undefined;
      if (!f?.path) return;
      const root = findRepoRoot(f.path, existsSync);
      if (!root) {
        this.tell(
          "从「" + f.path + "」往上找了十来层,没见着 tools\\gazetteer\\gaz.py。" +
          "挑一个**仓库里**的文件试试 —— CN_Electronic_Industry.xlsx 就行。",
          true,
        );
        return;
      }
      this.repo = root;
      if (this.box) this.box.value = root;
      this.check();
    });
    s.addButton((b) =>
      b
        .setButtonText("挑个文件…")
        .setTooltip("挑仓库里随便一个文件,它自己往上找到仓库根")
        .onClick(() => picker.click()),
    );

    this.say = contentEl.createEl("pre", { cls: "gaz-facts" });

    new Setting(contentEl)
      .addButton((b) => {
        this.okBtn = b;
        b.setButtonText("认下来,开工")
          .setCta()
          .onClick(() => void this.save());
        b.setDisabled(true);
      })
      .addButton((b) => b.setButtonText("待会儿再说").onClick(() => this.close()));

    if (this.repo) this.check();
    else this.tell("按「挑个文件…」,挑仓库里随便一个文件就行。");
  }

  private tell(text: string, bad = false): void {
    if (!this.say) return;
    this.say.setText(text);
    this.say.toggleClass("is-bad", bad);
  }

  /** 路径像不像仓库 —— 像就接着去认 python 与分支 */
  private check(): void {
    this.okBtn?.setDisabled(true);
    this.found = null;
    const gap = repoProblem(this.repo, this.repo ? existsSync(joinPath(this.repo, ...GAZ_MARK)) : false);
    if (gap) {
      this.tell(gap, !!this.repo);
      return;
    }
    this.tell("认着…");
    void this.detect();
  }

  private async detect(): Promise<void> {
    const repo = this.repo;

    const tried: { cmd: string; ok: boolean }[] = [];
    for (const cmd of PYTHON_TRIES) {
      const r = await capture({ exe: cmd, args: ["--version"], cwd: repo });
      tried.push({ cmd, ok: r.code === 0 });
      if (r.code === 0) break;
    }
    const branch = await capture({
      exe: "git",
      args: ["rev-parse", "--abbrev-ref", "HEAD"],
      cwd: repo,
    });

    // 挑到别的仓库去了就算了,这一遍作废
    if (repo !== this.repo) return;

    const units = joinPath(this.vaultRoot, "厂所");
    this.found = {
      repoDir: repo,
      python: pickPython(tried) ?? "",
      branch: branchOf(branch.out),
      vaultUnits: this.vaultRoot && existsSync(units) ? units : "",
    };
    this.tell(summarize(this.found));
    this.okBtn?.setDisabled(false);
    if (!this.found.python) {
      this.tell(
        summarize(this.found) +
          "\n\npython 这三种敲法都没应声:" + PYTHON_TRIES.join("、") +
          "。先装 Python,或者认下来之后去设置里把整条路径填上。",
        true,
      );
    }
  }

  private async save(): Promise<void> {
    if (!this.found) return;
    await this.onSave(this.found);
    this.close();
    new Notice("认下来了。面板上那些按钮现在能用了。");
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
