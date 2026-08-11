/* ============================================================
   中英双语
   ------------------------------------------------------------
   界面文字在此集中,数据本身不翻译:厂所名、地址、产品名、备注与出处
   都是史料原文,照录中文。若要英文厂名,可在「Fact and Comp-Shanghai」
   表加一列 `Name EN`,英文界面下自会取用(见 xlsxio.js)。
   受控词表(行业 / 类型 / 事件 / 统计项 / 精度 / 依据)是站点自己的分类,
   故给出对照译名。
   ============================================================ */

export const LANGS = [
  { code: "zh", label: "中文", switchTo: "EN" },
  { code: "en", label: "English", switchTo: "中文" },
];

/* ---------- 受控词表 ---------- */
export const INDUSTRY_EN = {
  "电子计算机": "Computers",
  "半导体": "Semiconductors",
  "外围设备": "Peripherals",
  "研究所": "Research institutes",
};
export const TYPE_EN = { factory: "Factory", institute: "Institute", jv: "Joint venture" };
export const EVENT_EN = {
  "合并": "Merger", "分立": "Split-off", "合资": "Joint venture",
  "划归": "Transfer", "更名": "Rename", "协作": "Collaboration",
};
export const STAT_EN = {
  staff: "Employees", tech: "Technical staff", plant: "Plant area", floor: "Floor area",
  assets: "Fixed assets", output: "Gross output", sales: "Sales revenue", profit: "Profit",
};
export const PRECISION_EN = {
  street: "street-level approximation",
  district: "district-level approximation",
  city: "city-level (address unrecorded)",
};
export const BASIS_EN = {
  "名称沿革表": "Name-History sheet",
  "原表沿革链": "Founder chain",
  "表内名称": "table name",
};
export const DISTRICT_EN = {
  "黄浦": "Huangpu", "静安": "Jing'an", "虹口": "Hongkou", "杨浦": "Yangpu",
  "普陀": "Putuo", "长宁": "Changning", "徐汇": "Xuhui", "浦东": "Pudong",
  "闵行": "Minhang", "嘉定": "Jiading", "宝山": "Baoshan", "松江": "Songjiang",
  "青浦": "Qingpu", "金山": "Jinshan", "奉贤": "Fengxian", "崇明": "Chongming",
  "浦东新": "Pudong",
};
export const CITY_ZH = { Shanghai: "上海", shanghai: "上海" };

/* ---------- 界面文字 ---------- */
const zh = {
  title: "中国电子工业历史地图",
  docTitle: "中国电子工业历史地图 · Historical Atlas of China's Electronics Industry",
  otherTitle: "HISTORICAL ATLAS OF CHINA'S ELECTRONICS INDUSTRY",
  tabs: { map: "地图", lineage: "谱系", products: "产品", directory: "名录" },
  navLabel: "页面切换",
  langLabel: "切换到英文",
  coverage: (n) => "现有数据:上海 · " + n + " 家厂所",
  previewChip: (f) => "● 本地预览:" + f + " ✕",
  previewTitle: "当前显示的是你导入的本地文件,线上数据未改变。点击可放弃预览。",

  /* 地图 */
  mapLabel: "中国电子工业历史地图",
  zoomIn: "放大", zoomOut: "缩小", fitData: "回到数据范围",
  districtSuffix: (d) => d + "区",
  clusterTitle: (label, n) => label + " · 当前存续 " + n + " 个单位,点击放大",
  locVague: " · 坐标待定位",
  listedAs: (n) => "表内作「" + n + "」",
  born: "始建", renamed: "改称",
  attribution: "区县界线取自 geoBoundaries(gbOpen CHN ADM3,simplified),CC BY 4.0",
  legendIndustry: "行业 INDUSTRY(点击筛选)",
  legendFactory: "工厂", legendInstitute: "研究所", legendJv: "合资", legendVague: "坐标待定位",

  /* 年份标尺 */
  rulerLabel: (y) => "年份标尺,当前 " + y + " 年,左右方向键调整",
  play: "播放", pause: "暂停", prevYear: "上一年", nextYear: "下一年",

  /* 谱系 */
  lineageCap: "横条 = 存续区间 · 竖线 = 沿革事件(据原表「Founder」列与整机研制记录推定) · 绿点 = 产品投产/研制年 · 点击横条查看详情,点击空白处改变年份",
  famOther: "其他 · 未见沿革关联",
  famLineage: " 系", famGroup: " 群 · 仅协作关联",
  undatedNote: (n) => "另有 " + n + " 家未标年份的单位未列入本表,见「名录」页。",

  /* 详情 */
  close: "关闭",
  undatedSpan: "年份待考",
  noAddress: "地址未著录",
  placedAs: "落点:", placedGiven: "表内给定坐标",
  secScope: "产品方向 SCOPE", secNames: "名称沿革 NAMES", secPredecessors: "前身沿革 PREDECESSORS",
  secLinks: "沿革关系 LINKS", secProducts: "产品记录 PRODUCTS",
  secStats: (y) => (y || "") + " 年概况 STATISTICS",
  secNotes: "备注与出处 NOTES",
  noLinks: "名录内暂无可连接的沿革关系。",
  inferred: "推定",
  dirIn: "由", dirOut: "→", dirWith: "与",
  unrecorded: "(未著录)",
  collab: "协作", solo: "自研",
  word: "字长", memory: "内存", speed: "速度",
  statsNote: "数值与量纲悉依原表。",
  sourcePrefix: "出处:",
  nameThatYear: (y, n) => y + " 年时称「" + n + "」",
  yearFrom: (y) => y + "年时称",

  /* 产品页 */
  segSemi: "半导体器件", segComp: "计算机整机",
  searchProducts: "检索产品、单位、人员…", searchProductsLabel: "检索产品",
  countItems: (a, b) => a + " / " + b + " 条",
  productsNote: (file, sheet) => "本页直录 " + file + " 的「" + sheet + "」表。单位名称按别名对照连回名录(如「上无十三」即上海电子计算机厂);未收入名录的协作单位以原文呈现,不作链接。",
  thYear: "年份", thTime: "时间", thProduct: "产品", thModel: "机型",
  thMaker: "生产单位", thResearch: "研制单位", thListed: "名录内",
  thPersonnel: "人员", thRemark: "备注", thSource: "出处",
  noRecords: "没有匹配的记录。",

  /* 名录页 */
  searchUnits: "检索单位、地址、沿革…", searchUnitsLabel: "检索名录",
  countUnits: (a, b) => a + " / " + b + " 家",
  importExcel: "导入 Excel", exportExcel: "导出 Excel",
  directoryNote: (file) => "全站数据来自仓库根目录的 " + file + "(Fact and Comp-Shanghai / Semi-Product / Comp-Product,另有可选的 Name-History),构建时编入产物。更新流程:改表 → 用「导入 Excel」在本机预览核对 → 覆盖仓库中的同名文件并 push,Actions 自动重建。导入只影响你自己这一次浏览。",
  statsNoteYear: (y) => " 统计列为 " + y + " 年数值,量纲悉依原表。",
  thUnit: "单位", thIndustry: "行业", thType: "类型", thSpan: "起讫", thAddress: "地址",
  noAddressShort: "未著录", vagueShort: "坐标待定位",
  noUnits: "没有匹配的单位。",

  /* 提示 */
  localFile: "本地文件",
  importOk: (c) => "已载入本地预览:厂所 " + c.units + " · 半导体产品 " + c.semi +
    " · 整机 " + c.comp + " · 推定沿革 " + c.events + "。仅本次浏览可见。",
  importFail: (m) => "导入失败:" + m,
  cannotParse: "无法解析该文件",
  exportFail: (m) => "导出失败:" + m,

  /* 读取失败 */
  bootFail: "数据表读取失败",
  bootHint: (file) => "请检查仓库根目录下的 " + file + " 是否仍含「Fact and Comp-Shanghai / Semi-Product / Comp-Product」三张表(Name-History 可有可无)。",

  /* 使用说明 */
  introTitle: "使用说明",
  intro1: "拖动下方年份标尺或按 ▶ 播放,观察厂所的兴建、分立与合并;滚轮缩放、点击节点查看详情。首屏已自动套合到现有数据的范围(上海),缩小即可回到全国视野。",
  intro2a: "节点颜色代表行业,形状区分工厂 / 研究所 / 合资企业。",
  intro2b: "经纬度不在原表之中",
  intro2c: ",是按门牌地址人工推定的近似落点(误差数百米至数公里);带红点者原表未著录地址,暂落在市中心。",
  intro3a: "连线是据原表「Founder」列与整机研制记录",
  intro3b: "推定",
  intro3c: "的沿革与协作关系,详情页均注明依据。",
  introBtn: "查看「谱系」年表 →",
};

const en = {
  title: "Historical Atlas of China's Electronics Industry",
  docTitle: "Historical Atlas of China's Electronics Industry · 中国电子工业历史地图",
  otherTitle: "中国电子工业历史地图",
  tabs: { map: "Map", lineage: "Lineage", products: "Products", directory: "Directory" },
  navLabel: "Switch page",
  langLabel: "Switch to Chinese",
  coverage: (n) => "Coverage: Shanghai · " + n + " units",
  previewChip: (f) => "● Local preview: " + f + " ✕",
  previewTitle: "You are viewing a file you imported. The published data is unchanged. Click to discard the preview.",

  mapLabel: "Historical atlas of China's electronics industry",
  zoomIn: "Zoom in", zoomOut: "Zoom out", fitData: "Fit to data",
  districtSuffix: (d) => d + " District",
  clusterTitle: (label, n) => label + " · " + n + " active here, click to zoom in",
  locVague: " · location approximate",
  listedAs: (n) => "listed as “" + n + "”",
  born: "founded", renamed: "renamed",
  attribution: "District boundaries from geoBoundaries (gbOpen CHN ADM3, simplified), CC BY 4.0",
  legendIndustry: "INDUSTRY (click to filter)",
  legendFactory: "Factory", legendInstitute: "Institute", legendJv: "Joint venture",
  legendVague: "Location approximate",

  rulerLabel: (y) => "Year slider, currently " + y + ", use left and right arrow keys",
  play: "Play", pause: "Pause", prevYear: "Previous year", nextYear: "Next year",

  lineageCap: "Bars = lifespan · Vertical lines = lineage events (inferred from the Founder column and the computer records) · Green dots = year a product entered production · Click a bar for details, click empty space to change the year",
  famOther: "Others · no lineage links found",
  famLineage: " lineage", famGroup: " group · collaboration only",
  undatedNote: (n) => n + " unit(s) without a recorded date are omitted here; see the Directory page.",

  close: "Close",
  undatedSpan: "date unrecorded",
  noAddress: "Address unrecorded",
  placedAs: "Placed by: ", placedGiven: "coordinates given in the table",
  secScope: "SCOPE", secNames: "NAMES", secPredecessors: "PREDECESSORS",
  secLinks: "LINKS", secProducts: "PRODUCTS",
  secStats: (y) => (y ? y + " " : "") + "STATISTICS",
  secNotes: "NOTES AND SOURCES",
  noLinks: "No lineage links to other units in the directory.",
  inferred: "inferred",
  dirIn: "from", dirOut: "→", dirWith: "with",
  unrecorded: "(unrecorded)",
  collab: "Joint", solo: "In-house",
  word: "Word", memory: "Memory", speed: "Speed",
  statsNote: "Figures and units are reproduced from the source table.",
  sourcePrefix: "Source: ",
  nameThatYear: (y, n) => "Known in " + y + " as “" + n + "”",
  yearFrom: (y) => "in " + y,

  segSemi: "Semiconductor devices", segComp: "Computers",
  searchProducts: "Search products, units, people…", searchProductsLabel: "Search products",
  countItems: (a, b) => a + " / " + b + " rows",
  productsNote: (file, sheet) => "This page reproduces the “" + sheet + "” sheet of " + file + ". Unit names are matched back to the directory through the alias table (e.g. 上无十三 = 上海电子计算机厂); collaborating bodies not in the directory appear as written, without links.",
  thYear: "Year", thTime: "Date", thProduct: "Product", thModel: "Model",
  thMaker: "Manufacturer", thResearch: "Developed by", thListed: "In directory",
  thPersonnel: "People", thRemark: "Remark", thSource: "Source",
  noRecords: "No matching records.",

  searchUnits: "Search units, addresses, lineage…", searchUnitsLabel: "Search directory",
  countUnits: (a, b) => a + " / " + b + " units",
  importExcel: "Import Excel", exportExcel: "Export Excel",
  directoryNote: (file) => "All data comes from " + file + " in the repository root (sheets Fact and Comp-Shanghai / Semi-Product / Comp-Product, plus the optional Name-History), compiled into the build. To update: edit the workbook → check it locally with “Import Excel” → overwrite the file in the repository and push; Actions rebuilds automatically. Importing affects only your own browsing session.",
  statsNoteYear: (y) => " Statistics are " + y + " figures; units follow the source table.",
  thUnit: "Unit", thIndustry: "Industry", thType: "Type", thSpan: "Span", thAddress: "Address",
  noAddressShort: "unrecorded", vagueShort: "location approximate",
  noUnits: "No matching units.",

  localFile: "local file",
  importOk: (c) => "Local preview loaded: " + c.units + " units · " + c.semi +
    " semiconductor records · " + c.comp + " computers · " + c.events +
    " inferred links. Visible only in this session.",
  importFail: (m) => "Import failed: " + m,
  cannotParse: "could not parse this file",
  exportFail: (m) => "Export failed: " + m,

  bootFail: "Could not read the data workbook",
  bootHint: (file) => "Check that " + file + " in the repository root still contains the sheets “Fact and Comp-Shanghai / Semi-Product / Comp-Product” (Name-History is optional).",

  introTitle: "How to use",
  intro1: "Drag the year slider below or press ▶ to play, and watch the factories being founded, split and merged; scroll to zoom, click a node for details. The opening view is fitted to the extent of the present data (Shanghai); zoom out for the national view.",
  intro2a: "Node colour shows the industry; the shape distinguishes factories, institutes and joint ventures. ",
  intro2b: "Coordinates are not in the source table",
  intro2c: " — they are approximate positions inferred from street addresses (accurate to a few hundred metres at best). Nodes with a red dot have no address on record and sit at the city centre.",
  intro3a: "The connecting lines are ",
  intro3b: "inferred",
  intro3c: " from the Founder column and the computer development records; every one states its basis in the detail panel.",
  introBtn: "Open the Lineage timeline →",
};

export const STR = { zh, en };

/** 依当前语言取一套文字 */
export const strings = (lang) => STR[lang] || STR.zh;

/** 受控词表的按语言取值 */
export const industryLabel = (k, lang) => (lang === "en" ? INDUSTRY_EN[k] || k : k);
export const typeLabel = (k, lang, zhLabel) => (lang === "en" ? TYPE_EN[k] || k : zhLabel);
export const eventLabel = (k, lang) => (lang === "en" ? EVENT_EN[k] || k : k);
export const statLabel = (key, lang, zhLabel) => (lang === "en" ? STAT_EN[key] || zhLabel : zhLabel);
export const basisLabel = (k, lang) => (lang === "en" ? BASIS_EN[k] || k : k);
export const districtLabel = (d, lang) => (lang === "en" ? DISTRICT_EN[d] || d : d);
export const cityLabel = (c, lang) => (lang === "en" ? c : CITY_ZH[c] || c);

/** 浏览器语言 → 默认界面语言 */
export function detectLang() {
  if (typeof navigator === "undefined") return "zh";
  const l = (navigator.languages && navigator.languages[0]) || navigator.language || "";
  return /^zh/i.test(l) ? "zh" : "en";
}
