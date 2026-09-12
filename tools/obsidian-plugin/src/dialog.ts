/* 系统的选文件框。

   **这一处栽过三次了。** 从前是拿一个藏起来的 `<input type=file>` 去
   `.click()` —— 那是网页的办法,在 Obsidian(Electron)里时灵时不灵:有的机器
   上按了一点反应也没有,不报错、不弹窗,什么都不发生。藏法改过一轮
   (display:none → 挪到屏幕外)仍不保准,因为病根不在藏法:渲染进程里那个
   input 要弹出系统对话框,得 Electron 那头许可,而 Obsidian 并不保证。

   正路是 Electron 自己的 `dialog.showOpenDialog`。新版 Obsidian 把它搁在
   `@electron/remote`,老版搁在 `electron.remote` —— 两处都试,都没有就**说一句**,
   别让人对着一个按了没反应的按钮猜。

   这个模块一行 Obsidian 的东西也不碰,`require` 从外头传进来,所以测得动。 */

/** 拿模块用的那个 require。传得进来,才好在测试里换成假的 */
export type Req = (mod: string) => unknown;

export interface OpenOpts {
  title?: string;
  /** 只看这几种后缀(不带点):["pdf"] */
  exts?: string[];
  /** 打开时停在哪个目录 */
  startIn?: string;
}

interface ElectronDialog {
  showOpenDialog(opts: Record<string, unknown>): Promise<{ canceled: boolean; filePaths: string[] }>;
}

/** 这套 Obsidian 里,系统对话框搁在哪儿。找不着回 null。
 *
 *  顺序要紧:`@electron/remote` 是新版的正路,`electron.remote` 是老版的 ——
 *  老版里 `require("@electron/remote")` 直接抛,所以各自包在 try 里。 */
export function findDialog(req: Req): ElectronDialog | null {
  for (const get of [
    () => (req("@electron/remote") as { dialog?: ElectronDialog }).dialog,
    () => (req("electron") as { remote?: { dialog?: ElectronDialog } }).remote?.dialog,
    () => (req("electron") as { dialog?: ElectronDialog }).dialog,
  ]) {
    try {
      const d = get();
      if (d && typeof d.showOpenDialog === "function") return d;
    } catch {
      /* 这一路不通,试下一路 */
    }
  }
  return null;
}

export interface PickResult {
  /** 挑中的整条路径;取消了是 "" */
  path: string;
  /** 这套 Obsidian 里压根开不出对话框 —— 该跟人说清楚,不是静悄悄没反应 */
  unavailable?: boolean;
}

/** 开一次选文件框。**开不出就直说**,由调用方摆到界面上。 */
export async function pickFile(opts: OpenOpts, req: Req): Promise<PickResult> {
  const dialog = findDialog(req);
  if (!dialog) return { path: "", unavailable: true };
  const filters = opts.exts?.length
    ? [{ name: opts.exts.join(" / "), extensions: opts.exts },
       { name: "所有文件", extensions: ["*"] }]
    : undefined;
  try {
    const r = await dialog.showOpenDialog({
      title: opts.title ?? "挑一个文件",
      properties: ["openFile"],
      ...(filters ? { filters } : {}),
      ...(opts.startIn ? { defaultPath: opts.startIn } : {}),
    });
    if (r.canceled || !r.filePaths?.length) return { path: "" };
    return { path: r.filePaths[0] };
  } catch {
    // 有就该开得出来;开不出来跟没有一样,照样明说
    return { path: "", unavailable: true };
  }
}
