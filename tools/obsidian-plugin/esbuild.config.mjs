/* 打包成 main.js —— Obsidian 只认一个文件。
   obsidian、electron、node 的内置模块都由宿主提供,打进去反而会冲突。 */
import esbuild from "esbuild";
import process from "node:process";
import builtins from "node:module";

const prod = process.argv[2] === "production";

const ctx = await esbuild.context({
  entryPoints: ["src/main.ts"],
  bundle: true,
  external: ["obsidian", "electron", ...builtins.builtinModules,
             ...builtins.builtinModules.map((m) => "node:" + m)],
  format: "cjs",
  target: "es2022",
  logLevel: "info",
  sourcemap: prod ? false : "inline",
  treeShaking: true,
  outfile: "main.js",
  minify: prod,
});

if (prod) {
  await ctx.rebuild();
  await ctx.dispose();
} else {
  await ctx.watch();
}
