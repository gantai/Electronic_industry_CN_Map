import * as XLSX from "xlsx";
import { PLACES, ALIASES, cityAt } from "./geocode.js";
import { YEAR_FALLBACK, EVENT_META } from "./consts.js";
import { parseCNDate, baseName, parenAlias, parenAliases, splitAliases, splitChain,
         stripLeadingDate } from "./utils.js";

/* ============================================================
   CN_Electronic_Industry.xlsx 解析器
   ------------------------------------------------------------
   工作簿即本站唯一数据源,四张表:
     Fact and Comp-Shanghai  厂所名录(含 1990 年统计块,两行表头)
     Semi-Product            半导体器件投产记录
     Comp-Product            计算机整机研制记录
     Name-History            名称沿革(可选,有则名称以此表为准)
   本文件只做「读取 + 归并」,不改写原表语义:地图上的经纬度来自
   geocode.js 的人工近似值,沿革连线由「Founder」列的措辞推定,
   两者在界面上都会显式标注出处,便于核对。
   ============================================================ */

const SHEET_HINTS = {
  units: ["fact and comp-shanghai", "fact", "厂所", "units"],
  semi: ["semi-product", "semi", "半导体"],
  comp: ["comp-product", "comp", "整机", "计算机"],
  names: ["name-history", "names", "名称沿革", "名称"],
};

const norm = (s) => String(s == null ? "" : s).trim().toLowerCase();

function pickSheet(wb, kind) {
  const names = wb.SheetNames;
  const hints = SHEET_HINTS[kind];
  for (const h of hints) {
    const hit = names.find((n) => norm(n) === h);
    if (hit) return wb.Sheets[hit];
  }
  for (const h of hints) {
    const hit = names.find((n) => norm(n).includes(h));
    if (hit) return wb.Sheets[hit];
  }
  return null;
}

const rowsOf = (ws) =>
  ws ? XLSX.utils.sheet_to_json(ws, { header: 1, defval: null, blankrows: false }) : [];

const cell = (row, i) => {
  if (!row || i < 0 || i >= row.length) return "";
  const v = row[i];
  return v == null ? "" : typeof v === "string" ? v.trim() : v;
};
const numCell = (row, i) => {
  const v = cell(row, i);
  if (v === "") return null;
  const n = typeof v === "number" ? v : parseFloat(String(v).replace(/[^\d.\-]/g, ""));
  return isFinite(n) ? n : null;
};

/* ---------- 表头定位 ---------- */
function headerIndex(rows, needle) {
  for (let i = 0; i < Math.min(rows.length, 8); i++) {
    if ((rows[i] || []).some((c) => norm(c) === needle)) return i;
  }
  return 0;
}

function colFinder(...headerRows) {
  return (...labels) => {
    for (const row of headerRows) {
      for (let i = 0; i < (row || []).length; i++) {
        const v = norm(row[i]);
        if (labels.some((l) => v === norm(l))) return i;
      }
    }
    return -1;
  };
}

const STAT_COLS = [
  ["staff", "职工总数"],
  ["tech", "技术人员"],
  ["plant", "厂房面积"],
  ["floor", "建筑面积"],
  ["assets", "固定资产"],
  ["output", "工业总产值"],
  ["sales", "销售收入"],
  ["profit", "实现利润"],
];

/* ---------- 名称 → 单位 的匹配器 ---------- */
function buildMatcher(units) {
  const tokens = [];
  units.forEach((u) => {
    const set = new Set([u.name, u.alt, ...(u.aliases || []), ...(ALIASES[u.name] || [])]);
    set.forEach((t) => { if (t && String(t).length >= 3) tokens.push({ token: String(t), id: u.id }); });
  });
  tokens.sort((a, b) => b.token.length - a.token.length);
  /** 在自由文本中找出所有被提到的单位。长名优先并遮蔽已匹配区段,
      避免「上无十四」把「上无十四厂」拆成两处、或短名嵌进长名里误判。 */
  return function match(text) {
    const s = String(text == null ? "" : text);
    if (!s) return [];
    const used = new Array(s.length).fill(false);
    const hits = [];
    for (const { token, id } of tokens) {
      let from = 0;
      for (;;) {
        const at = s.indexOf(token, from);
        if (at < 0) break;
        let free = true;
        for (let j = at; j < at + token.length; j++) if (used[j]) { free = false; break; }
        if (free) {
          for (let j = at; j < at + token.length; j++) used[j] = true;
          hits.push({ id, at });
        }
        from = at + 1;
      }
    }
    hits.sort((a, b) => a.at - b.at);
    const out = [];
    hits.forEach((h) => { if (!out.includes(h.id)) out.push(h.id); });
    return out;
  };
}

/* ---------- 由「Founder」措辞推定事件类型 ---------- */
function founderEventType(text) {
  const s = String(text || "");
  if (/合资/.test(s)) return "合资";
  if (/车间|部门|研究组|分出|划出/.test(s)) return "分立";
  if (/划归|划入|划转|归属/.test(s)) return "划归";
  if (/合并|并入|组建|抽调|\+/.test(s)) return "合并";
  return "更名";
}

/* ---------- 名称沿革 ----------
   「Founder」列的链条里,一部分步骤是这家单位历年的名字,另一部分是划归、
   并入一类的机构变动。把前者按日期排成一条名称时间线,地图上便能按年显示
   当年的名号 —— 譬如冶金所 1928 年时还叫中央研究院工学研究所。
   只认原表写明的改名;拿不准的一律回落到表内 A 列的名称。 */
const NAME_VERB = /^(?:改名为|更名为|改称为|改名|更名|改称|易名|定名)/;
const EVENT_VERB = /划归|划入|划出|归属|并入|合并|抽调|投资|组建|合资|\+/;

function chainStepName(text) {
  const rest = stripLeadingDate(text).trim();
  if (!rest) return null;
  const m = rest.match(NAME_VERB);
  if (m) return rest.slice(m[0].length).trim() || null;
  return EVENT_VERB.test(rest) ? null : rest;
}

function buildNames(chain, start, tableName) {
  const only = [{ from: start, name: tableName, basis: "表内名称", note: "" }];
  if (!start) return only;
  const steps = chain.map((c) => ({ ...c, nm: chainStepName(c.text) }))
    .filter((c) => !c.date || c.date.y >= start.y);
  const firstDated = steps.findIndex((c) => c.date);
  if (firstDated < 0 || !steps.some((c) => c.date && c.nm)) return only;

  /* 首段:第一个纪年步骤之前、最后一个像名称的无日期步骤 */
  let head = tableName, headBasis = "表内名称";
  for (let i = firstDated - 1; i >= 0; i--) {
    if (steps[i].nm) { head = steps[i].nm; headBasis = "原表沿革链"; break; }
  }
  const segs = [{ from: start, name: head, basis: headBasis, note: "" }];
  steps.forEach((c, i) => {
    if (!c.date) return;
    const isLast = !steps.slice(i + 1).some((t) => t.date);
    const note = stripLeadingDate(c.text);
    if (c.nm) segs.push({ from: c.date, name: c.nm, basis: "原表沿革链", note });
    /* 末尾若是一次机构变动,此后便以表内名称相称 */
    else if (isLast) segs.push({ from: c.date, name: tableName, basis: "表内名称", note });
  });
  return segs.filter((seg, i) => i === 0 || seg.name !== segs[i - 1].name);
}

/* ---------- 厂所名录 ---------- */
function parseUnits(ws) {
  const rows = rowsOf(ws);
  if (!rows.length) return { units: [], statsYear: null };
  const hi = headerIndex(rows, "industry");
  const h1 = rows[hi] || [];
  const h2 = rows[hi + 1] || [];
  const secondIsHeader = STAT_COLS.some(([, label]) => (h2 || []).some((c) => norm(c) === norm(label)));
  const col = colFinder(h1, secondIsHeader ? h2 : []);

  const cIndustry = col("Industry", "行业");
  const cAlias = col("别名", "Alias", "又名");
  const cProduct = col("Product", "产品");
  const cStart = col("Start Date", "始建", "始建年");
  const cEnd = col("End Date", "终止", "终止年");
  const cFounder = col("Founder", "前身", "沿革");
  const cCity = col("City", "城市");
  const cAddr = col("Add.", "Address", "地址");
  const cRemark = col("Remark", "备注");
  const cSource = col("Source", "出处", "资料来源");
  const cNameEn = col("Name EN", "英文名", "English Name");
  const cLat = col("Lat", "Latitude", "纬度");
  const cLng = col("Lng", "Lon", "Longitude", "经度");
  /* A 列无表头,即单位名称 */
  const cName = col("Unit", "Factory", "名称") >= 0 ? col("Unit", "Factory", "名称") : 0;

  const statCols = STAT_COLS.map(([key, label]) => [key, col(label)]).filter(([, i]) => i >= 0);
  let statsYear = null;
  if (statCols.length) {
    const firstStat = Math.min(...statCols.map(([, i]) => i));
    for (let i = firstStat; i >= 0; i--) {
      const y = parseInt(cell(h1, i), 10);
      if (isFinite(y) && y > 1900 && y < 2100) { statsYear = y; break; }
    }
  }

  const body = rows.slice(hi + (secondIsHeader ? 2 : 1));
  const units = [];
  body.forEach((r) => {
    const raw = String(cell(r, cName) || "").trim();
    if (!raw) return;
    const name = baseName(raw) || raw;
    /* 一家单位常有好几个名字:「华北计算技术研究所（四机部15所、电子部15所）」。
       挑一个当正名,别的全留着 —— 都能搜到,面板里都列出来,文中提到哪一个都认得。
       有年份可考的改名归「名称沿革」表,那是按年份显示的;这里放的是没有年份的
       别名、简称、又称。 */
    const aliases = [...parenAliases(raw), ...splitAliases(cell(r, cAlias))]
      .filter((x, i, a) => x && x !== name && a.indexOf(x) === i);
    const alt = parenAlias(raw) || aliases[0] || "";
    const industry = String(cell(r, cIndustry) || "").trim();
    const founder = String(cell(r, cFounder) || "").trim();

    const stats = {};
    let hasStats = false;
    statCols.forEach(([key, i]) => {
      const n = numCell(r, i);
      stats[key] = n;
      if (n != null) hasStats = true;
    });

    const place = PLACES[name] || {};
    /* 兜底落点按 City 列分城,免得外地厂所一律落在上海 */
    const fallback = cityAt(cell(r, cCity));
    const latOverride = cLat >= 0 ? numCell(r, cLat) : null;
    const lngOverride = cLng >= 0 ? numCell(r, cLng) : null;
    const hasOwn = latOverride != null && lngOverride != null;
    const hasPlace = place.lat != null && place.lng != null;

    units.push({
      id: "u" + (units.length + 1),
      raw,
      name,
      /* 可选:表内若有 `Name EN` 一列,英文界面便用它称呼这家单位 */
      nameEn: String(cell(r, cNameEn) || "").trim(),
      alt,
      aliases,
      industry,
      type: industry === "研究所" ? "institute" : /合资/.test(founder) ? "jv" : "factory",
      product: String(cell(r, cProduct) || "").trim(),
      start: parseCNDate(cell(r, cStart)),
      end: parseCNDate(cell(r, cEnd)),
      founder,
      /* 沿革链的每一步都可能自带日期(更名 / 划归多写在步骤开头) */
      chain: splitChain(founder).map((t) => ({ text: t, date: parseCNDate(t) })),
      city: String(cell(r, cCity) || "").trim(),
      address: String(cell(r, cAddr) || "").trim(),
      lat: hasOwn ? latOverride : hasPlace ? place.lat : fallback.lat,
      lng: hasOwn ? lngOverride : hasPlace ? place.lng : fallback.lng,
      precision: hasOwn ? "given" : hasPlace ? place.precision || "district" : "city",
      district: hasPlace || hasOwn ? place.district || "" : "",
      locNote: place.note || "",
      stats,
      hasStats,
      remark: String(cell(r, cRemark) || "").trim(),
      source: String(cell(r, cSource) || "").trim(),
      semi: [],
      comp: [],
    });
    const u = units[units.length - 1];
    u.names = buildNames(u.chain, u.start, u.name);
  });
  return { units, statsYear };
}

/* ---------- 半导体器件 ---------- */
function parseSemi(ws, match) {
  const rows = rowsOf(ws);
  if (!rows.length) return [];
  const hi = headerIndex(rows, "product");
  const col = colFinder(rows[hi] || []);
  const cP = col("Product", "产品"), cF = col("Factory", "厂"), cT = col("Time", "时间");
  const cO = col("产量", "Output");
  const cPer = col("Personnel", "人员"), cR = col("Remark", "备注");
  return rows.slice(hi + 1).map((r, i) => {
    const factoryText = String(cell(r, cF) || "").trim();
    return {
      id: "s" + (i + 1),
      product: String(cell(r, cP) || "").trim(),
      factoryText,
      output: String(cell(r, cO) || "").trim(),
      unitIds: match(factoryText),
      date: parseCNDate(cell(r, cT)),
      timeRaw: String(cell(r, cT) || "").trim(),
      personnel: String(cell(r, cPer) || "").trim(),
      remark: String(cell(r, cR) || "").trim(),
    };
  }).filter((x) => x.product || x.factoryText);
}

/* ---------- 计算机整机 ---------- */
function parseComp(ws, match) {
  const rows = rowsOf(ws);
  if (!rows.length) return [];
  const hi = headerIndex(rows, "product");
  const col = colFinder(rows[hi] || []);
  const cP = col("Product", "产品"), cW = col("字长"), cM = col("内存");
  const cS = col("Speed（次秒）", "Speed", "速度"), cI = col("Research Insti", "研制单位");
  const cF = col("Factory", "厂"), cT = col("Time", "时间");
  const cU = col("用户", "User", "应用单位"), cO = col("产量", "Output");
  const cA = col("别名", "Alias", "又名");
  const cPer = col("Personnel", "人员"), cR = col("Remark", "备注");
  return rows.slice(hi + 1).map((r, i) => {
    const instText = String(cell(r, cI) || "").trim();
    const factoryText = String(cell(r, cF) || "").trim();
    /* 「用户」是机器的去处,不是研制方 —— 决不并进 unitIds,
       否则 deriveEvents 会把用机的人家画成共同研制的「协作」。 */
    const userText = String(cell(r, cU) || "").trim();
    const ids = [];
    [...match(instText), ...match(factoryText)].forEach((id) => { if (!ids.includes(id)) ids.push(id); });
    return {
      id: "c" + (i + 1),
      product: String(cell(r, cP) || "").trim(),
      word: cell(r, cW) === "" ? "" : String(cell(r, cW)),
      memory: cell(r, cM) === "" ? "" : String(cell(r, cM)),
      speed: cell(r, cS) === "" ? "" : String(cell(r, cS)),
      instText,
      factoryText,
      userText,
      output: String(cell(r, cO) || "").trim(),
      aliases: splitAliases(cell(r, cA)),
      unitIds: ids,
      date: parseCNDate(cell(r, cT)),
      timeRaw: String(cell(r, cT) || "").trim(),
      personnel: String(cell(r, cPer) || "").trim(),
      remark: String(cell(r, cR) || "").trim(),
    };
  }).filter((x) => x.product);
}

/* ---------- 名称沿革表(可选) ----------
   有这张表就以它为准,没有才回落到从「Founder」列推定的那条线。
   一行一段名称:Unit 对应名录里的单位,From 是这个名字启用的日期,
   一直用到同一单位的下一行为止。只需登记改过名的单位。 */
function parseNameHistory(ws, match, units) {
  const rows = rowsOf(ws);
  if (!rows.length) return {};
  const hi = headerIndex(rows, "unit");
  const col = colFinder(rows[hi] || []);
  const cU = col("Unit", "单位"), cN = col("Name", "名称"), cF = col("From", "启用", "起始");
  const cNe = col("Name EN", "英文名");
  const cR = col("Remark", "备注"), cS = col("Source", "出处");
  if (cU < 0 || cN < 0) return {};

  const byUnit = {};
  rows.slice(hi + 1).forEach((r) => {
    const who = String(cell(r, cU) || "").trim();
    const name = String(cell(r, cN) || "").trim();
    const date = parseCNDate(cell(r, cF));
    if (!who || !name || !date) return;
    const ids = match(who);
    if (!ids.length) return;
    (byUnit[ids[0]] = byUnit[ids[0]] || []).push({
      from: date, name, nameEn: String(cell(r, cNe) || "").trim(), basis: "名称沿革表",
      note: stripLeadingDate(String(cell(r, cR) || "").trim()),
      source: String(cell(r, cS) || "").trim(),
    });
  });

  const out = {};
  const byId = Object.fromEntries(units.map((u) => [u.id, u]));
  Object.entries(byUnit).forEach(([id, segs]) => {
    segs.sort((a, b) => (a.from.y - b.from.y) || ((a.from.m || 0) - (b.from.m || 0)) || ((a.from.d || 0) - (b.from.d || 0)));
    const u = byId[id];
    /* 表里最早一行若晚于始建年,前面那段仍用表内名称 */
    if (u && u.start && segs[0].from.y > u.start.y) {
      segs.unshift({ from: u.start, name: u.name, nameEn: u.nameEn, basis: "表内名称", note: "", source: "" });
    }
    out[id] = segs.filter((seg, i) => i === 0 || seg.name !== segs[i - 1].name);
  });
  return out;
}

/* ---------- 事件推定 ---------- */
function deriveEvents(units, comp, match) {
  const byId = Object.fromEntries(units.map((u) => [u.id, u]));
  const events = [];

  /* 一、沿革:「Founder」列里提到的、名录中确有其名的单位 → 前身 */
  units.forEach((u) => {
    if (!u.founder) return;
    const from = match(u.founder).filter((id) => id !== u.id);
    if (!from.length) return;
    const dt = u.start || u.end;
    events.push({
      id: "ev" + (events.length + 1),
      type: founderEventType(u.founder),
      year: dt ? dt.y : null,
      date: dt,
      from,
      to: [u.id],
      note: u.founder,
      basis: "据「Founder」列推定",
      derived: true,
      uncertain: !dt,
    });
  });

  /* 二、协作:同一台整机由两个以上名录内单位共同研制 */
  comp.forEach((c) => {
    if (c.unitIds.length < 2) return;
    events.push({
      id: "ev" + (events.length + 1),
      type: "协作",
      year: c.date ? c.date.y : null,
      date: c.date,
      from: c.unitIds.slice(),
      to: [],
      note: c.product + (c.remark ? " · " + c.remark : ""),
      basis: "据「Comp-Product」表推定",
      derived: true,
      uncertain: !c.date,
      productId: c.id,
    });
  });

  return events.filter((e) => e.from.every((id) => byId[id]) && e.to.every((id) => byId[id]));
}

/** 某一年该以什么名字称呼这家单位。lang="en" 时,若表里给了英文名便用英文名。 */
export function nameAt(u, year, lang) {
  const pick = (zh, en) => (lang === "en" && en ? en : zh);
  if (!u.names || !u.names.length) return { name: pick(u.name, u.nameEn), historical: false };
  let seg = u.names[0];
  u.names.forEach((s) => { if (s.from && s.from.y <= year) seg = s; });
  return { name: pick(seg.name, seg.nameEn), historical: seg.name !== u.name, seg };
}

/* ---------- 主入口 ---------- */
export const EMPTY_DATA = {
  units: [], semi: [], comp: [], events: [],
  statsYear: null, yearMin: YEAR_FALLBACK.min, yearMax: YEAR_FALLBACK.max,
  counts: { units: 0, semi: 0, comp: 0, events: 0 },
};

export function parseWorkbook(buf) {
  const wb = XLSX.read(buf, { type: "array" });
  const { units, statsYear } = parseUnits(pickSheet(wb, "units"));
  if (!units.length) throw new Error("未找到「Fact and Comp-Shanghai」厂所名录表");

  const match = buildMatcher(units);
  const explicitNames = parseNameHistory(pickSheet(wb, "names"), match, units);
  units.forEach((u) => { if (explicitNames[u.id]) u.names = explicitNames[u.id]; });
  const semi = parseSemi(pickSheet(wb, "semi"), match);
  const comp = parseComp(pickSheet(wb, "comp"), match);
  const events = deriveEvents(units, comp, match);

  const byId = Object.fromEntries(units.map((u) => [u.id, u]));
  semi.forEach((s) => s.unitIds.forEach((id) => byId[id] && byId[id].semi.push(s)));
  comp.forEach((c) => c.unitIds.forEach((id) => byId[id] && byId[id].comp.push(c)));

  const years = [];
  const push = (y) => { if (isFinite(y) && y > 1800 && y < 2100) years.push(y); };
  units.forEach((u) => { if (u.start) push(u.start.y); if (u.end) push(u.end.y); });
  semi.forEach((s) => s.date && push(s.date.y));
  comp.forEach((c) => c.date && push(c.date.y));
  if (statsYear) push(statsYear);
  const lo = years.length ? Math.min(...years) : YEAR_FALLBACK.min;
  const hi = years.length ? Math.max(...years) : YEAR_FALLBACK.max;

  return {
    units, semi, comp, events, statsYear,
    namedUnits: Object.keys(explicitNames).length,
    yearMin: Math.floor((lo - 3) / 5) * 5,
    yearMax: Math.ceil((hi + 3) / 5) * 5,
    counts: { units: units.length, semi: semi.length, comp: comp.length, events: events.length },
  };
}

/* ---------- 导出:按原表版式回写,另附推定坐标两列 ---------- */
const STAT_LABELS = STAT_COLS.map(([, label]) => label);

export function exportWorkbook(data, filename) {
  const wb = XLSX.utils.book_new();
  const y = data.statsYear || "";

  const head1 = ["", "Industry", "Product", "Start Date", "End Date", "Founder", "City", "Add.", y,
    ...Array(STAT_LABELS.length - 1).fill(""), "Remark", "Source", "Name EN", "Lat", "Lng"];
  const head2 = ["", "", "", "", "", "", "", "", ...STAT_LABELS, "", "", "", "", ""];
  const body = data.units.map((u) => [
    u.raw, u.industry, u.product,
    u.start ? u.start.raw : "", u.end ? u.end.raw : "",
    u.founder, u.city, u.address,
    ...STAT_COLS.map(([k]) => (u.stats[k] == null ? "" : u.stats[k])),
    u.remark, u.source, u.nameEn || "", u.lat, u.lng,
  ]);
  const ws1 = XLSX.utils.aoa_to_sheet([head1, head2, ...body]);
  ws1["!cols"] = [{ wch: 26 }, { wch: 10 }, { wch: 20 }, { wch: 11 }, { wch: 11 }, { wch: 40 }, { wch: 9 }, { wch: 26 },
    ...STAT_LABELS.map(() => ({ wch: 9 })), { wch: 40 }, { wch: 18 }, { wch: 30 }, { wch: 9 }, { wch: 9 }];

  const ws2 = XLSX.utils.aoa_to_sheet([
    ["Product", "Factory", "产量", "Time", "Personnel", "Remark"],
    ...data.semi.map((s) => [s.product, s.factoryText, s.output, s.timeRaw, s.personnel, s.remark]),
  ]);
  ws2["!cols"] = [{ wch: 28 }, { wch: 24 }, { wch: 11 }, { wch: 14 }, { wch: 40 }];

  const ws3 = XLSX.utils.aoa_to_sheet([
    ["Product", "字长", "内存", "Speed（次秒）", "Research Insti", "Factory", "用户", "产量", "别名", "Time", "Personnel", "Remark"],
    ...data.comp.map((c) => [c.product, c.word, c.memory, c.speed, c.instText, c.factoryText, c.userText, c.output, (c.aliases || []).join("、"), c.timeRaw, c.personnel, c.remark]),
  ]);
  ws3["!cols"] = [{ wch: 30 }, { wch: 8 }, { wch: 12 }, { wch: 14 }, { wch: 40 }, { wch: 28 }, { wch: 18 }, { wch: 16 }, { wch: 46 }];

  const nameRows = [];
  data.units.forEach((u) => {
    if (!u.names || u.names.length < 2) return;
    u.names.forEach((seg) => nameRows.push([
      u.raw, seg.name,
      String(seg.from.y * 10000 + (seg.from.m || 0) * 100 + (seg.from.d || 0)).padStart(8, "0"),
      seg.nameEn || "", seg.note || "", seg.source || "",
    ]));
  });
  const ws4 = XLSX.utils.aoa_to_sheet([["Unit", "Name", "From", "Name EN", "Remark", "Source"], ...nameRows]);
  ws4["!cols"] = [{ wch: 26 }, { wch: 30 }, { wch: 11 }, { wch: 30 }, { wch: 44 }, { wch: 22 }];

  XLSX.utils.book_append_sheet(wb, ws1, "Fact and Comp-Shanghai");
  XLSX.utils.book_append_sheet(wb, ws2, "Semi-Product");
  XLSX.utils.book_append_sheet(wb, ws3, "Comp-Product");
  XLSX.utils.book_append_sheet(wb, ws4, "Name-History");
  XLSX.writeFile(wb, filename || "CN_Electronic_Industry.xlsx");
}

export { EVENT_META };
