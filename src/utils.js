export const clone = (o) => JSON.parse(JSON.stringify(o));

export const clampYear = (y, min, max) => Math.max(min, Math.min(max, y));

/** 原表的日期写成 YYYYMMDD,月/日未知处补 0(如 19410000 只知年份)。
    也容得下「1960 late」「19650000-19720500；19730000技术鉴定」这类
    带范围与注文的写法 —— 取其中第一个日期,原文另行保留。 */
export function parseCNDate(v) {
  if (v == null || v === "") return null;
  const raw = String(v).trim();
  const m8 = raw.match(/(\d{4})(\d{2})(\d{2})/);
  if (m8) {
    const y = +m8[1], mo = +m8[2], d = +m8[3];
    if (y >= 1800 && y <= 2100 && mo <= 12 && d <= 31) {
      return { y, m: mo || null, d: d || null, prec: d ? "day" : mo ? "month" : "year", raw };
    }
  }
  const m6 = raw.match(/(\d{4})(\d{2})(?!\d)/);
  if (m6 && +m6[1] >= 1800 && +m6[1] <= 2100 && +m6[2] <= 12) {
    return { y: +m6[1], m: +m6[2] || null, d: null, prec: +m6[2] ? "month" : "year", raw };
  }
  const m4 = raw.match(/(1[89]\d{2}|20\d{2})/);
  if (m4) return { y: +m4[1], m: null, d: null, prec: "year", raw };
  return null;
}

export const fmtDate = (dt) => {
  if (!dt) return "";
  if (dt.prec === "day") return `${dt.y}.${String(dt.m).padStart(2, "0")}.${String(dt.d).padStart(2, "0")}`;
  if (dt.prec === "month") return `${dt.y}.${String(dt.m).padStart(2, "0")}`;
  return String(dt.y);
};

export const fmtNum = (n) =>
  n == null || n === "" || !isFinite(n) ? "—" : String(Math.round(n * 100) / 100);

/** 名称规范化:去掉全/半角括号中的别名与空白,便于对照 */
export const baseName = (s) =>
  String(s || "").trim().replace(/[（(][^）)]*[）)]/g, "").replace(/\s+/g, "");

/** 括号里的别名,如「上海电子计算机厂（上无十三）」→ 上无十三 */
export const parenAlias = (s) => {
  const m = String(s || "").match(/[（(]([^）)]*)[）)]/);
  return m ? m[1].trim() : "";
};

/** 「甲、乙;丙」→ ["甲","乙","丙"]。一家单位、一台机器往往同时有好几个名字,
    不必挑一个 —— 全留着,都能搜到、都显示。 */
export const splitAliases = (s) =>
  String(s || "").split(/[、,，;；/／|]/).map((x) => x.trim()).filter(Boolean);

/** 名字里所有括号中的别名:「甲厂（乙厂、丙厂）」→ ["乙厂","丙厂"] */
export const parenAliases = (s) => {
  const out = [];
  String(s || "").replace(/[（(]([^）)]*)[）)]/g, (_m, g) => {
    out.push(...splitAliases(g));
    return "";
  });
  return out;
};

/** 去掉沿革步骤开头的日期,如「19750200改名上海新跃仪表厂」→「改名上海新跃仪表厂」 */
export const stripLeadingDate = (s) =>
  String(s || "").replace(/^\s*\d{4}(?:\d{2}(?:\d{2})?)?\s*年?\s*/, "");

/** 把「甲->乙->丙」式的沿革链拆成有序步骤 */
export const splitChain = (s) =>
  String(s || "")
    .split(/\s*(?:->|→|—>|-->)\s*/)
    .map((x) => x.trim())
    .filter(Boolean);

/* 同址单位(经纬度完全一致)在图上散开成一朵向日葵花盘,否则彼此叠死。
   从前是一个圆环,半径随家数线性长 —— 只知道城市、落在天安门那一点上的
   一百来家,环半径算出来 332px,比半个屏幕还宽;而一圈匀整的点看着像真有
   那么个环形分布,等于凭排版凭空造出一种格局。
   改成 r = R·√((i+½)/n)、θ = i·黄金角:外沿有上限,点距大致均匀,位置只
   跟序号有关 —— 每次刷新都落在同一处,不靠随机。
   返回屏上像素偏移;调用处按当前缩放倍数折算回图上坐标。 */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

export function rosette(n, { rMax = 92, gap = 15 } = {}) {
  if (n < 2) return [];
  /* 家数少时不必铺到外沿:按目标点距反推一个够用的半径,取小者 */
  const R = Math.min(rMax, gap * Math.sqrt(n / Math.PI) + 12);
  const out = [];
  for (let i = 0; i < n; i++) {
    const r = R * Math.sqrt((i + 0.5) / n);
    const a = i * GOLDEN_ANGLE - Math.PI / 2;
    out.push([Math.cos(a) * r, Math.sin(a) * r]);
  }
  return out;
}
