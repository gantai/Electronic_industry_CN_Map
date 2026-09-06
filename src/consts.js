/* 全站常量。行业 / 单位类型 / 沿革事件的取值直接对应数据源
   CN_Electronic_Industry.xlsx 中出现的中文词汇,新增取值请同步补充这里。 */

/* 年份区间由数据自动推算(见 xlsxio.js),这里只作为兜底与下限保护 */
export const YEAR_FALLBACK = { min: 1925, max: 1995 };

/* 时间轴最早画到哪一年。
   本该由数据说了算,可眼下有五条记录写着 1902/1904 —— DJS050 是七十年代的
   机器,长城0520A 是八十年代的,断无可能。一条错年份就把整条轴拽长四十年,
   前半截空着没有一个点。在查清之前先定个下限。
   早于此年的记录并不丢:仍在表里、仍搜得到,谱系页的横条从轴的左端起画。 */
export const YEAR_FLOOR = 1940;

/* 「Industry」列 —— 决定节点颜色 */
export const INDUSTRY_META = {
  "电子计算机": { color: "#F2C14E", en: "Computers" },
  "半导体": { color: "#7ED8E8", en: "Semiconductors" },
  "外围设备": { color: "#C9B8FF", en: "Peripherals" },
  "研究所": { color: "#8FD9A8", en: "Research institutes" },
};
export const INDUSTRY_FALLBACK = { color: "#9FB8D4", en: "Other" };
export const industryMeta = (k) => INDUSTRY_META[k] || INDUSTRY_FALLBACK;

/* 单位类型 —— 决定节点形状(由 Industry / Founder 推断,见 xlsxio.js)。
   color 只在国家尺度的柱状图上用得着:图上的点按行业着色,柱子按类型分段。
   研究所两处同色,是有意的 —— 同一类东西不该换两身衣裳。 */
export const TYPE_ORDER = ["factory", "institute", "jv"];
export const TYPE_META = {
  factory: { label: "工厂", shape: "circle", color: "#7ED8E8" },
  institute: { label: "研究所", shape: "square", color: "#8FD9A8" },
  jv: { label: "合资企业", shape: "ring", color: "#C9B8FF" },
};

/* 沿革事件类型 —— 由「Founder」列的措辞推定 */
export const EVENT_META = {
  "合并": { color: "#7ED8E8", dash: null, slug: "merge" },
  "分立": { color: "#F2C14E", dash: null, slug: "split" },
  "合资": { color: "#C9B8FF", dash: null, slug: "jv" },
  "划归": { color: "#D8E7F6", dash: [6, 5], slug: "transfer" },
  "更名": { color: "#9FB8D4", dash: [2, 5], slug: "rename" },
  "协作": { color: "#8FD9A8", dash: [1, 6], slug: "collab" },
};
export const EVENT_FALLBACK = "协作";
export const eventMeta = (k) => EVENT_META[k] || EVENT_META[EVENT_FALLBACK];

/* 「1990」统计块 —— key 与 xlsxio.js 的表头映射一致;
   量纲一律以原表为准,故此处不写单位,只在界面上注明。 */
export const STAT_FIELDS = [
  { key: "staff", label: "职工总数" },
  { key: "tech", label: "技术人员" },
  { key: "plant", label: "厂房面积" },
  { key: "floor", label: "建筑面积" },
  { key: "assets", label: "固定资产" },
  { key: "output", label: "工业总产值" },
  { key: "sales", label: "销售收入" },
  { key: "profit", label: "实现利润" },
];

/* 坐标精度 —— 见 geocode.js */
export const PRECISION_LABEL = {
  street: "街道级近似",
  district: "区级近似",
  city: "市级近似(地址待考)",
};
