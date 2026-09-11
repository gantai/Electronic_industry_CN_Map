/* 把打好的插件装进库里。
 *
 *   node deploy.mjs "D:\Archive"
 *
 * 装的是三个文件:main.js（打包出来的）、manifest.json、styles.css。
 * 去处是 <库>\.obsidian\plugins\<插件 id>\ —— Obsidian 只认这一处。
 *
 * 头一回装完要在 Obsidian 里「设置 → 第三方插件」把它打开;往后再装就是
 * 覆盖那三个文件,重启 Obsidian(或在插件列表里关一下再开)即可生效。
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const here = path.dirname(new URL(import.meta.url).pathname);
const manifest = JSON.parse(fs.readFileSync(path.join(here, "manifest.json"), "utf8"));

const vault = process.argv[2] || process.env.GAZ_VAULT_ROOT;
if (!vault) {
  console.error("要说装到哪个库:node deploy.mjs \"D:\\\\Archive\"");
  console.error("(也可以设环境变量 GAZ_VAULT_ROOT)");
  process.exit(1);
}
if (!fs.existsSync(path.join(vault, ".obsidian"))) {
  console.error("这里头没有 .obsidian —— " + vault + " 不像是个 Obsidian 库。");
  console.error("库是你在 Obsidian 里打开的那个文件夹,不是仓库。");
  process.exit(1);
}

const dest = path.join(vault, ".obsidian", "plugins", manifest.id);
fs.mkdirSync(dest, { recursive: true });

const files = ["main.js", "manifest.json", "styles.css"];
const missing = files.filter((f) => !fs.existsSync(path.join(here, f)));
if (missing.length) {
  console.error("少了:" + missing.join("、") + " —— 先跑 npm run build");
  process.exit(1);
}
for (const f of files) {
  fs.copyFileSync(path.join(here, f), path.join(dest, f));
  console.log("  → " + path.join(dest, f));
}
console.log("装好了。头一回装,还要去 设置 → 第三方插件 把「" + manifest.name + "」打开。");
