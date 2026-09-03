/* ============================================================
   坐标与别名对照表
   ------------------------------------------------------------
   数据源 CN_Electronic_Industry.xlsx 只记录门牌地址,不含经纬度。
   本文件把地址换算成地图上的落点,**全部为人工近似值**:

     street   —— 按路名与门牌号推定到街段,误差约数百米
     district —— 只能定到区,误差数公里
     city     —— 原表无地址,落在市中心并在界面上标注「坐标待定位」

   这些坐标只用于制图定位,不可当作测绘成果引用。若要用实测坐标,
   有两种改法,任选其一:
     1. 直接改本文件 PLACES 里的 lat / lng / precision;
     2. 在 CN_Electronic_Industry.xlsx 的「厂所名录」表
        末尾新增 Lat / Lng 两列并填入数值 —— 表里的值优先级更高,
        会覆盖这里的推定值(见 xlsxio.js)。
   ============================================================ */

/* 市级兜底落点 —— 表内没写地址、PLACES 里也没有对照的单位,落在本市市中心,
   界面上标作「坐标待定位」。**按 City 列分城**:否则新添的北京厂所会一律
   落到上海人民广场去。key 兼收中英两种写法,大小写不论(见 cityAt)。 */
export const CITY_FALLBACK = {
  Shanghai: { lat: 31.2304, lng: 121.4737, label: "上海" },   // 人民广场
  Beijing: { lat: 39.9042, lng: 116.4074, label: "北京" },     // 天安门
  Tianjin: { lat: 39.1088, lng: 117.2008, label: "天津" },
  Nanjing: { lat: 32.0603, lng: 118.7969, label: "南京" },
  /* 志书里点到的外地协作单位 —— 兰州炼油厂、唐山陡河发电总厂之流。
     没有这几条,它们会掉进 DEFAULT_FALLBACK,给扔到上海人民广场去。 */
  Tangshan: { lat: 39.6304, lng: 118.1804, label: "唐山" },
  Harbin: { lat: 45.8038, lng: 126.5350, label: "哈尔滨" },
  Lanzhou: { lat: 36.0611, lng: 103.8343, label: "兰州" },
  Changsha: { lat: 28.2282, lng: 112.9388, label: "长沙" },
};
/* 中文写法一并挂上,表里写「北京」或「Beijing」都认 */
CITY_FALLBACK["上海"] = CITY_FALLBACK.Shanghai;
CITY_FALLBACK["北京"] = CITY_FALLBACK.Beijing;
CITY_FALLBACK["天津"] = CITY_FALLBACK.Tianjin;
CITY_FALLBACK["南京"] = CITY_FALLBACK.Nanjing;
CITY_FALLBACK["唐山"] = CITY_FALLBACK.Tangshan;
CITY_FALLBACK["哈尔滨"] = CITY_FALLBACK.Harbin;
CITY_FALLBACK["兰州"] = CITY_FALLBACK.Lanzhou;
CITY_FALLBACK["长沙"] = CITY_FALLBACK.Changsha;

export const DEFAULT_FALLBACK = CITY_FALLBACK.Shanghai;

/** City 列 → 兜底落点。认不出的城市仍回落到 DEFAULT_FALLBACK。 */
export function cityAt(city) {
  const raw = String(city == null ? "" : city).trim();
  if (!raw) return DEFAULT_FALLBACK;
  const hit = CITY_FALLBACK[raw]
    || CITY_FALLBACK[raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase()];
  return hit || DEFAULT_FALLBACK;
}

/* key = 原表 A 列的单位名称(去掉括号别名前的完整写法亦可,见 xlsxio.js 的规范化) */
export const PLACES = {
  /* ──────── Shanghai ──────── 26 条 */
  "上海电子计算机厂": { lat: 31.2380, lng: 121.4460, district: "静安", precision: "street" },
  "上海微电脑厂": { lat: 31.1963, lng: 121.4098, district: "长宁", precision: "street" },
  "上海计算机技术服务公司": { lat: 31.2118, lng: 121.4344, district: "徐汇", precision: "street" },
  "上海王安电脑发展公司": { lat: 31.1590, lng: 121.4400, district: "徐汇", precision: "street" },
  "一亚电工实验室": { lat: 31.2245, lng: 121.4455, district: "静安", precision: "street", note: "原福煦路,今延安中路" },
  "一亚电工厂": { lat: 31.2600, lng: 121.4795, district: "虹口", precision: "street" },
  "国营上海精密医疗器械厂": { lat: null, lng: null, precision: "city" },
  "上海公私合营兴东电子工业厂": { lat: null, lng: null, precision: "city" },
  "交直电工厂": { lat: null, lng: null, precision: "city" },
  "上海元件五厂": { lat: 31.2295, lng: 121.4518, district: "静安", precision: "street", note: "1958 年南京西路 893 号,1959 年 6 月迁威海卫路 696 号,此处取后者" },
  "上海无线电七厂": { lat: 31.2730, lng: 121.4885, district: "虹口", precision: "street" },
  "上海无线电十厂": { lat: 31.2385, lng: 121.5675, district: "浦东", precision: "street" },
  "上海无线电十四厂": { lat: 31.1975, lng: 121.4778, district: "黄浦", precision: "street" },
  "上海无线电十七厂": { lat: 31.2120, lng: 121.4960, district: "黄浦", precision: "street", note: "1966 年 9 月由北苏州路 659 号迁董家渡路 175 号,此处取后者" },
  "黄浦仪器厂": { lat: 31.0505, lng: 121.3865, district: "闵行", precision: "street" },
  "上海长江计算机打印厂": { lat: 31.1665, lng: 121.4020, district: "徐汇", precision: "street", note: "漕河泾新兴技术开发区" },
  "上海工业自动化仪表研究所": { lat: 31.1735, lng: 121.4250, district: "徐汇", precision: "street" },
  "上海微电机研究所": { lat: 31.1820, lng: 121.4640, district: "徐汇", precision: "street" },
  "上海传输线研究所": { lat: 31.2790, lng: 121.4995, district: "虹口", precision: "street" },
  "上海市计算技术研究所": { lat: 31.2218, lng: 121.4385, district: "静安", precision: "street" },
  "上海微波技术研究所": { lat: 31.2430, lng: 121.4230, district: "普陀", precision: "street" },
  "上海微波设备研究所": { lat: 31.2700, lng: 121.3480, district: "普陀", precision: "street" },
  "上海市无线电技术研究所": { lat: 31.2010, lng: 121.4225, district: "徐汇", precision: "street" },
  "上海市电子光学技术研究所": { lat: null, lng: null, precision: "city" },
  "上海仪器仪表研究所": { lat: null, lng: null, precision: "city", note: "原表作龙江路 225 号,路段未能核实" },
  "上海光学仪器研究所": { lat: null, lng: null, precision: "city" },

  /* ──────── 未标城市 ──────── 3 条 */
  "沪兴电子有限公司": { lat: 31.0505, lng: 121.3865, district: "闵行", precision: "street", note: "与黄浦仪器厂同址" },
  "华东计算技术研究所": { lat: 31.2378, lng: 121.4690, district: "黄浦", precision: "street", note: "原凤阳路 338 号,后迁嘉定澄桥,此处取前者" },
  "中国科学院上海冶金研究所": { lat: 31.2205, lng: 121.4180, district: "长宁", precision: "street" },

  /* ──────── Beijing ──────── 0 条
     `gaz geocode-city --city Beijing` 出的草稿填好之后粘在这儿。
     41 家有地址、还没坐标,归在 32 条路上,酒仙桥路一条占 10 家。 */
  "北京东方电子集团股份有限公司": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路10号" },
  "北京东光电工厂": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路12号" },
  "北京有线电总厂": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路14号" },
  "北京国际交换系统有限公司": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路14号" },

  "北京无线电工具设备厂": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路2号" },
  "北京晨星无线电器材厂": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路2号" },
  "北京第一无线电器材厂": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路2号" },
 
  "北京第二无线电器材厂": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路4号" },
  "北京电子动力公司": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路4号" },
  "北京飞行电子总公司": { lat: 39.9812, lng: 116.4952, district: "朝阳", precision: "street", note: "酒仙桥路4号" },
};

/* ------------------------------------------------------------
   别名 —— 原表在「Founder」「Research Insti」「Factory」等列里
   大量使用简称与手民之误(如「上五十三」当为「上无十三」)。
   这里把简称挂到正式名下,才能把散在各表的记载连成同一个单位。
   只收录能确证同一性的写法;拿不准的一律不收,宁可少连一条线。
   ------------------------------------------------------------ */
export const ALIASES = {
  "上海电子计算机厂": ["上无十三", "上五十三"],
  "上海元件五厂": ["上海半导体厂", "上元五厂"],
  "上海无线电七厂": ["上无七厂"],
  "上海无线电十厂": ["上无十厂"],
  "上海无线电十四厂": ["上无十四厂", "上无十四"],
  "上海无线电十七厂": ["上无十七厂", "上无十七"],
  "华东计算技术研究所": ["华东计算所", "华东计算机所"],
  "上海市计算技术研究所": ["上海市计算中心", "上海计算中心"],
  "上海市无线电技术研究所": ["上海无线电技术研究所"],
  "上海工业自动化仪表研究所": ["上海自动化仪表研究所"],
  "中国科学院上海冶金研究所": ["中科院冶金所", "上海冶金研究所"],
  "上海长江计算机打印厂": ["长江计算机打印厂"],
  "沪兴电子有限公司": ["沪兴电子"],
  "上海公私合营兴东电子工业厂": ["兴东电子工业厂"],
  "上海王安电脑发展公司": ["王安电脑发展公司"],
};

/* 区名 —— 用于地图上的方位注记 */
export const DISTRICT_ORDER = ["黄浦", "静安", "虹口", "杨浦", "普陀", "长宁", "徐汇", "浦东", "闵行", "嘉定"];
