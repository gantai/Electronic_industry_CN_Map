/* 头一回用的那张卡片。
   先前这儿只弹一句「先去设置里填仓库目录」—— 可设置在哪儿,它一个字没说。
   如今设置本身就在这张卡片里办完:挑一个文件,别的几样它自己认。 */

import { App, Modal, Notice, Setting } from "obsidian";
import { existsSync, readdirSync } from "node:fs";
import {
  GAZ_MARK, branchOf, candidateRoots, findRepoRoot, joinPath, pickPython,
  PYTHON_TRIES, repoProblem, scanForRepo, summarize, type Detected, type Fs,
} from "./setup";
import { capture } from "./runner";
import type { GazSettings } from "./settings";

type ElectronFile = File & { path?: string };

/** 喂给 setup.ts 里那几个纯函数的真家伙 */
const REAL_FS: Fs = {
  exists: (p) => existsSync(p),
  listDirs: (p) => {
    try {
      return readdirSync(p, { withFileTypes: true })
        .filter((e) => e.isDirectory())
        .map((e) => e.name);
    } catch {
      // 没权限的目录多得很(系统盘尤其),读不动就当它是空的,别声张
      return [];
    }
  },
};

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
      .setDesc(
        "CN_Map 那个文件夹。在资源管理器里打开它,**地址栏整条路径复制过来**," +
        "粘在这里就行(点一下地址栏空白处,路径会变成可复制的文字)。",
      );
    s.addText((t) => {
      t.setPlaceholder("D:\\Coding\\CN_Map")
        .setValue(this.repo)
        .onChange((v) => {
          this.repo = v.trim();
          this.check();
        });
      this.box = t.inputEl;
      t.inputEl.style.width = "280px";
    });

    /* 挑文件那条路不牢靠 —— Electron 里藏起来的 <input type=file> 有时
       压根不弹窗,按了没反应。所以**自己找**才是正路:粘路径永远管用,
       自动找是省那一道手工;挑文件退居第三,能用就用,不能用不碍事。 */
    s.addButton((b) =>
      b
        .setButtonText("自己找")
        .setTooltip("在几个盘的浅处找搁着 tools\\gazetteer\\gaz.py 的那一层")
        .onClick(() => void this.hunt()),
    );

    this.say = contentEl.createEl("pre", { cls: "gaz-facts" });

    const more = contentEl.createDiv({ cls: "gaz-setup-more" });
    const picker = more.createEl("input", { type: "file" });
    /* 不用 display:none —— 藏成那样,Electron 有时就不弹窗了(按了没反应)。
       挪到屏幕外头,元素还在、还点得动。 */
    picker.style.position = "fixed";
    picker.style.left = "-10000px";
    picker.style.width = "1px";
    picker.style.height = "1px";
    picker.style.opacity = "0";
    picker.addEventListener("change", () => {
      const f = picker.files?.[0] as ElectronFile | undefined;
      if (!f?.path) {
        this.tell("这条路在这台机器上不灵 —— 把路径粘进上头那一栏吧。", true);
        return;
      }
      const root = findRepoRoot(f.path, existsSync);
      if (!root) {
        this.tell(
          "从「" + f.path + "」往上找了十来层,没见着 tools\\gazetteer\\gaz.py。" +
          "挑一个**仓库里**的文件试试 —— CN_Electronic_Industry.xlsx 就行。",
          true,
        );
        return;
      }
      this.setRepo(root);
    });
    const pick = more.createEl("a", {
      cls: "gaz-setup-link",
      text: "或者挑仓库里随便一个文件(有的机器上这个弹不出窗,那就粘路径)",
    });
    pick.onclick = (e) => {
      e.preventDefault();
      picker.click();
    };

    new Setting(contentEl)
      .addButton((b) => {
        this.okBtn = b;
        b.setButtonText("认下来,开工")
          .setCta()
          .onClick(() => void this.save());
        b.setDisabled(true);
      })
      .addButton((b) => b.setButtonText("待会儿再说").onClick(() => this.close()));

    // 一开就自己找 —— 找着了这张卡片等于不用填,找不着再请人粘路径
    if (this.repo) this.check();
    else void this.hunt();
  }

  private setRepo(dir: string): void {
    this.repo = dir;
    if (this.box) this.box.value = dir;
    this.check();
  }

  /** 自己去几个盘的浅处找。找得着就填上,找不着直说,不闷着 */
  private async hunt(): Promise<void> {
    this.tell("找着…(只翻几个盘的浅处,翻不了多久)");
    // 让这一句先画出来,再动手翻盘
    await new Promise((r) => setTimeout(r, 30));
    const found = scanForRepo(candidateRoots(this.vaultRoot), REAL_FS);
    if (!found) {
      this.tell(
        "几个盘的浅处都没见着 tools\\gazetteer\\gaz.py。\n" +
        "仓库大概搁得深了些 —— 在资源管理器里打开 CN_Map,把地址栏那条路径" +
        "复制过来,粘到上头那一栏。",
        true,
      );
      return;
    }
    this.setRepo(found);
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
