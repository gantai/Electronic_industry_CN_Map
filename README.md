# 中国电子工业历史地图 · Historical Atlas of China's Electronics Industry

单人维护的交互式历史地图:时间轴上的厂所兴废、分立与合并谱系、可检索的引文表。纯静态站点,只读展示,无任何在线编辑或投稿功能——**只有你能改数据,方式是覆盖仓库里的一个 Excel 文件**。

## 结构

```
public/data.xlsx     唯一数据源(节点 / 沿革事件 / 引文 / 字段说明 四张表)
src/
  App.jsx            界面(地图 · 谱系 · 引文)
  xlsxio.js          Excel 读写      consts.js / utils.js
  china.geo.json     省界底图        seed.js  内置示例数据(仅在 data.xlsx 载入失败时兜底)
.github/workflows/deploy.yml   push 即自动构建并发布到 GitHub Pages
```

## 一次性部署到 GitHub Pages

1. 新建 GitHub 仓库(如 `electronics-atlas`),把本目录**全部内容**推送到 `main` 分支:

   ```bash
   git init && git add -A && git commit -m "初始提交"
   git branch -M main
   git remote add origin https://github.com/<用户名>/electronics-atlas.git
   git push -u origin main
   ```

2. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**。

几十秒后站点上线:`https://<用户名>.github.io/electronics-atlas/`。构建使用相对路径,项目页、根域名或自定义域名都能直接跑。**自定义域名**在 Settings → Pages → Custom domain 填写并按提示配 DNS 即可。

## 日常更新数据(唯一的维护动作)

数据全在 `public/data.xlsx`,字段含义见其中「字段说明」表。

**方式一 · 网页端(不用装任何东西)**:在 GitHub 仓库页进入 `public/` → 点 `data.xlsx` → 右上 **Upload files** 上传同名新文件覆盖 → Commit。Actions 自动重新部署,一两分钟后线上更新。

**方式二 · 本地**:改完 `public/data.xlsx` 后 `git add -A && git commit -m "更新数据" && git push`。

改动前想核对表格有没有写错,可在站点「引文」页点「导入 Excel」——**只在你自己的浏览器里预览**,线上数据不受影响,右上角会出现「● 本地预览」提示,点它即可退出。「导出 Excel」则把站点当前数据导回一份规范的 `data.xlsx`,适合作为编辑起点。

Git 的提交历史顺带成了数据的修订史,任何一次改动都能回溯或还原。

## 本地开发(只在改代码时需要)

需要 Node.js 18+:

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # 产物在 dist/
```

注意别用 `file://` 直接打开 `dist/index.html`(浏览器禁止本地 fetch,读不到 data.xlsx);本地看构建结果请在 `dist/` 里跑 `python3 -m http.server 8000`。

## 已知事项

- 当前 `public/data.xlsx` 为**示例数据**(多处标注「示例 / 待考」),仅演示格式,请以真实数据覆盖。
- 底图为当代省级政区(含 1997 年后的重庆直辖市)。需要历史政区可将 CHGIS 等边界转为 GeoJSON 替换 `src/china.geo.json`(要求:FeatureCollection,`properties.name` 为政区名)。
- 首屏 JS 约 753 KB(gzip 约 251 KB),主要来自 d3 与 SheetJS。
- `npm audit` 会提示 SheetJS(`xlsx@0.18.5`)的原型污染通告;该风险针对解析不可信工作簿,本站只解析你自己仓库中的 `data.xlsx` 与你本人选择的文件。
