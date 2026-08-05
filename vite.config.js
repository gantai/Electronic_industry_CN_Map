import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

/* 把 `import x from "…/foo.xlsx?b64"` 变成一段 base64 字符串,数据表因此
   直接编译进产物:线上不必再 fetch 一个 .xlsx,dist/ 直接用 file:// 打开
   也能跑。改了表格重新构建即可(GitHub Actions 每次 push 都会重建),
   开发时改动表格会触发热更新。 */
function xlsxAsBase64() {
  const SUFFIX = "?b64";
  return {
    name: "xlsx-as-base64",
    enforce: "pre",
    resolveId(source, importer) {
      if (!source.endsWith(SUFFIX)) return null;
      const file = source.slice(0, -SUFFIX.length);
      const abs = file.startsWith(".") && importer ? resolve(dirname(importer), file) : resolve(file);
      return abs + SUFFIX;
    },
    load(id) {
      if (!id.endsWith(SUFFIX)) return null;
      const file = id.slice(0, -SUFFIX.length);
      this.addWatchFile(file);
      return `export default ${JSON.stringify(readFileSync(file).toString("base64"))};`;
    },
  };
}

// base:"./" → 相对路径构建:GitHub Pages 项目页、自定义域名或任意子路径均可直接部署
export default defineConfig({
  base: "./",
  plugins: [xlsxAsBase64(), react()],
});
