/* 跑外头的命令,把输出一行一行喂回面板。

   **编码这一处要当心。** Windows 上 Python 往管道里写字,用的不是控制台那个
   编码,而是系统的 GBK;这边拿 UTF-8 去读,中文就成了乱码 —— 而且不报错,
   只是满屏看不懂。所以给子进程写死 `PYTHONIOENCODING=utf-8`:让它照 UTF-8 写,
   这边照 UTF-8 读,两头对上。
   (gaz 那头另有一道 —— 见 gazetteer/console.py,治的是反过来的毛病:
   GBK 里没有「✓」,写出去就炸。两处合起来才周全。) */

import { spawn } from "node:child_process";
import type { Cmd } from "./steps";

export interface RunHandle {
  /** 叫停。杀的是整棵子进程树能杀到的那一部分 */
  stop(): void;
  /** 跑完了才 resolve;非零退出码也照样 resolve,由调用方看 code */
  done: Promise<number>;
}

export interface RunSink {
  line(text: string, stream: "out" | "err"): void;
  /** 每条命令开跑之前报一声,好让人看出跑到哪一条了 */
  start?(cmd: Cmd): void;
  end?(cmd: Cmd, code: number): void;
}

export function describe(cmd: Cmd): string {
  /* 只为给人看。真跑的时候参数是按数组传的,不经过这一行 —— 所以这里
     加不加引号都不影响结果,加上只是让人看清楚哪几个字是一个参数。 */
  const q = (s: string) => (/[\s"']/.test(s) ? '"' + s + '"' : s);
  return [cmd.exe, ...cmd.args].map(q).join(" ");
}

/** 一条命令。回退出码;起不来(没装 python、路径不对)回 -1,并把缘故喂给 sink。 */
export function runOne(cmd: Cmd, sink: RunSink): RunHandle {
  let child: ReturnType<typeof spawn> | null = null;
  const done = new Promise<number>((resolve) => {
    sink.start?.(cmd);
    try {
      child = spawn(cmd.exe, cmd.args, {
        cwd: cmd.cwd,
        env: {
          ...process.env,
          PYTHONIOENCODING: "utf-8",
          PYTHONUTF8: "1",
          // 颜色码在面板里只会变成一串 ESC[0m
          NO_COLOR: "1",
          GIT_TERMINAL_PROMPT: "0",
        },
        windowsHide: true,
      });
    } catch (e) {
      sink.line("起不来:" + String(e), "err");
      resolve(-1);
      return;
    }
    if (!child) {
      resolve(-1);
      return;
    }

    const feed = (stream: "out" | "err") => {
      let buf = "";
      return (chunk: Buffer) => {
        buf += chunk.toString("utf8");
        const parts = buf.split(/\r?\n/);
        buf = parts.pop() ?? "";
        for (const p of parts) sink.line(p, stream);
      };
    };
    child.stdout?.on("data", feed("out"));
    child.stderr?.on("data", feed("err"));

    child.on("error", (e: NodeJS.ErrnoException) => {
      /* ENOENT 就是「这个命令找不着」。说清楚是哪个 —— 光一句 ENOENT,
         没人猜得到是 python 没装还是仓库路径填错了。 */
      if (e.code === "ENOENT") {
        sink.line(
          "找不到 `" + cmd.exe + "`。python 没装,或者设置里那一栏写的不是它真正的敲法。",
          "err",
        );
      } else {
        sink.line("出错:" + e.message, "err");
      }
      resolve(-1);
    });
    child.on("close", (code: number | null) => {
      const c = code ?? -1;
      sink.end?.(cmd, c);
      resolve(c);
    });
  });

  return { stop: () => child?.kill(), done };
}

/** 一串命令,按顺序跑。**中间哪一条非零就停** —— 前一句没成,后一句多半白跑,
 *  跑下去还可能把事情弄得更糟(比如 checkout 没成却接着 merge)。 */
export function runAll(cmds: Cmd[], sink: RunSink): RunHandle {
  let cur: RunHandle | null = null;
  let stopped = false;
  const done = (async () => {
    for (const cmd of cmds) {
      if (stopped) return -1;
      cur = runOne(cmd, sink);
      const code = await cur.done;
      if (code !== 0) {
        if (cmds.length > 1) sink.line("—— 这一条没成,底下的就不跑了。", "err");
        return code;
      }
    }
    return 0;
  })();
  return {
    stop: () => {
      stopped = true;
      cur?.stop();
    },
    done,
  };
}

/** 跑一条,把输出整个收回来(不喂面板)。给「先看一眼」那种用。 */
export function capture(cmd: Cmd): Promise<{ code: number; out: string }> {
  let out = "";
  const sink: RunSink = { line: (t) => { out += t + "\n"; } };
  return runOne(cmd, sink).done.then((code) => ({ code, out }));
}
