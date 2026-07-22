import * as XLSX from "xlsx";
import { TYPE_META, TYPE_FROM_ZH, EVENT_META } from "./consts.js";
import { clone, truthy, splitIds } from "./utils.js";

export const EMPTY_DATA = { entities: [], events: [], citations: [], changelog: [] };

const HDR_E = { "id": "id", "名称": "name", "英文名": "en", "厂号": "code", "类型": "type", "城市": "city", "省份": "province", "纬度": "lat", "经度": "lng", "始建年": "founded", "终止年": "ended", "待考": "uncertain", "同址分组": "hub", "简介": "intro", "引文ID": "cites" };
const HDR_V = { "id": "id", "年份": "year", "类型": "type", "来源单位ID": "from", "去向单位ID": "to", "说明": "note", "待考": "uncertain", "引文ID": "cites" };
const HDR_C = { "id": "id", "类别": "kind", "作者机构": "author", "题名": "title", "出处": "source", "卷期档号页码": "locator", "年份": "year", "链接": "url", "备注": "note", "贡献者": "contributor", "录入日期": "added" };

const mapRow = (row, hdr) => {
  const out = {};
  Object.entries(hdr).forEach(([h, k]) => {
    if (row[h] !== undefined && row[h] !== "") out[k] = row[h];
    else if (row[k] !== undefined && row[k] !== "") out[k] = row[k];
  });
  return out;
};
const pickSheet = (wb, names) => {
  for (const n of names) if (wb.Sheets[n]) return XLSX.utils.sheet_to_json(wb.Sheets[n], { defval: "" });
  return null;
};

/** Parse a workbook (ArrayBuffer / Uint8Array). Sheets that are present
    replace the corresponding section of `base`; absent sheets keep base data. */
export function parseWorkbookBuffer(buf, base) {
  const wb = XLSX.read(buf, { type: "array" });
  const eRows = pickSheet(wb, ["节点", "工厂节点", "entities", "Entities"]);
  const vRows = pickSheet(wb, ["沿革事件", "事件", "events", "Events"]);
  const cRows = pickSheet(wb, ["引文", "citations", "Citations", "引文表"]);
  const next = clone(base || EMPTY_DATA);
  if (!Array.isArray(next.changelog)) next.changelog = [];
  let ne = 0, nv = 0, nc = 0, skipped = 0;
  if (cRows) {
    next.citations = cRows.map((r, i) => {
      const o = mapRow(r, HDR_C);
      return { id: String(o.id || "c" + (i + 1)), kind: String(o.kind || ""), author: String(o.author || ""), title: String(o.title || ""), source: String(o.source || ""), locator: String(o.locator || ""), year: String(o.year || ""), url: String(o.url || ""), note: String(o.note || ""), contributor: String(o.contributor || ""), added: String(o.added || "") };
    }).filter((c) => c.title || c.author);
    nc = next.citations.length;
  }
  if (eRows) {
    const ents = [];
    eRows.forEach((r) => {
      const o = mapRow(r, HDR_E);
      const founded = parseInt(o.founded, 10);
      if (!o.id || !o.name || !isFinite(founded)) { skipped++; return; }
      const lat = parseFloat(o.lat), lng = parseFloat(o.lng);
      const ended = o.ended === "" || o.ended == null ? null : parseInt(o.ended, 10);
      ents.push({
        id: String(o.id), name: String(o.name), en: String(o.en || ""), code: String(o.code || ""),
        type: TYPE_FROM_ZH[o.type] || (["factory", "institute", "group"].includes(o.type) ? o.type : "factory"),
        city: String(o.city || ""), province: String(o.province || ""),
        lat: isFinite(lat) ? lat : 35, lng: isFinite(lng) ? lng : 104,
        founded, ended: isFinite(ended) ? ended : null,
        uncertain: truthy(o.uncertain) || !isFinite(lat), hub: o.hub ? String(o.hub) : null,
        intro: String(o.intro || "") + (!isFinite(lat) ? "(坐标待定位)" : ""),
        cites: splitIds(o.cites),
      });
    });
    if (ents.length) { next.entities = ents; ne = ents.length; }
  }
  if (vRows) {
    const evs = [];
    vRows.forEach((r, i) => {
      const o = mapRow(r, HDR_V);
      const yy = parseInt(o.year, 10);
      if (!isFinite(yy)) { skipped++; return; }
      evs.push({
        id: String(o.id || "v" + (i + 1)), year: yy,
        type: EVENT_META[o.type] ? o.type : "协作",
        from: splitIds(o.from), to: splitIds(o.to),
        uncertain: truthy(o.uncertain), note: String(o.note || ""), cites: splitIds(o.cites),
      });
    });
    next.events = evs; nv = evs.length;
  }
  return { next, counts: { ne, nv, nc, skipped, any: !!(eRows || vRows || cRows) } };
}

export const README_ROWS = [
  ["工作表", "字段", "说明"],
  ["(总则)", "", "本工作簿即网站的数据源:仓库中的 public/data.xlsx 会在站点启动时自动载入;在「引文」页也可手动导入预览。ID 在各表内须唯一;多个引文ID用分号分隔;「待考」一栏填「是」表示史实待核(图上以虚线标示)。"],
  ["节点", "id", "唯一标识,建议用短拼音或编号,如 e738"],
  ["节点", "名称 / 英文名 / 厂号", "厂号即代号(如 738);无则留空"],
  ["节点", "类型", "工厂 / 研究所 / 联合体"],
  ["节点", "城市 / 省份", "显示用文字"],
  ["节点", "纬度 / 经度", "十进制度,如 39.976 / 116.488"],
  ["节点", "始建年 / 终止年", "整数年份;仍存续则「终止年」留空"],
  ["节点", "待考", "填「是」则该条目标为待考"],
  ["节点", "同址分组", "同一片区多厂共用一个分组ID(如 jxq),地图上会自动散开排布;可留空"],
  ["节点", "简介 / 引文ID", "简介为气泡正文;引文ID指向「引文」表,用分号分隔"],
  ["沿革事件", "年份 / 类型", "类型:分立 / 合并 / 援建 / 迁建 / 协作"],
  ["沿革事件", "来源单位ID / 去向单位ID", "填「节点」表中的 id,多个用分号分隔;「协作」类可只填来源"],
  ["沿革事件", "说明 / 待考 / 引文ID", "同上"],
  ["引文", "id", "如 c1、c2,供节点与事件引用"],
  ["引文", "类别", "档案 / 方志 / 专著 / 期刊 / 丛书 / 口述 / 内部资料 / 网络 / 待整理"],
  ["引文", "作者机构 / 题名 / 出处 / 卷期档号页码 / 年份 / 链接 / 备注", "按类别酌情填写;档案请写全宗-目录-案卷号"],
  ["引文", "贡献者 / 录入日期", "便于审核追溯"],
];

export function exportWorkbook(data, filename) {
  const wb = XLSX.utils.book_new();
  const eRows = data.entities.map((e) => ({
    "id": e.id, "名称": e.name, "英文名": e.en || "", "厂号": e.code || "", "类型": (TYPE_META[e.type] || {}).label || e.type,
    "城市": e.city || "", "省份": e.province || "", "纬度": e.lat, "经度": e.lng,
    "始建年": e.founded, "终止年": e.ended == null ? "" : e.ended, "待考": e.uncertain ? "是" : "",
    "同址分组": e.hub || "", "简介": e.intro || "", "引文ID": (e.cites || []).join("; "),
  }));
  const vRows = data.events.map((v) => ({
    "id": v.id, "年份": v.year, "类型": v.type, "来源单位ID": (v.from || []).join("; "), "去向单位ID": (v.to || []).join("; "),
    "说明": v.note || "", "待考": v.uncertain ? "是" : "", "引文ID": (v.cites || []).join("; "),
  }));
  const cRows = data.citations.map((c) => ({
    "id": c.id, "类别": c.kind, "作者机构": c.author, "题名": c.title, "出处": c.source,
    "卷期档号页码": c.locator, "年份": c.year, "链接": c.url, "备注": c.note, "贡献者": c.contributor, "录入日期": c.added,
  }));
  const ws1 = XLSX.utils.json_to_sheet(eRows); ws1["!cols"] = [{ wch: 8 }, { wch: 24 }, { wch: 26 }, { wch: 8 }, { wch: 8 }, { wch: 14 }, { wch: 10 }, { wch: 9 }, { wch: 9 }, { wch: 8 }, { wch: 8 }, { wch: 6 }, { wch: 9 }, { wch: 60 }, { wch: 14 }];
  const ws2 = XLSX.utils.json_to_sheet(vRows); ws2["!cols"] = [{ wch: 6 }, { wch: 6 }, { wch: 6 }, { wch: 28 }, { wch: 28 }, { wch: 50 }, { wch: 6 }, { wch: 12 }];
  const ws3 = XLSX.utils.json_to_sheet(cRows); ws3["!cols"] = [{ wch: 6 }, { wch: 8 }, { wch: 20 }, { wch: 30 }, { wch: 18 }, { wch: 22 }, { wch: 7 }, { wch: 24 }, { wch: 30 }, { wch: 10 }, { wch: 11 }];
  const ws4 = XLSX.utils.aoa_to_sheet(README_ROWS); ws4["!cols"] = [{ wch: 10 }, { wch: 26 }, { wch: 90 }];
  XLSX.utils.book_append_sheet(wb, ws1, "节点");
  XLSX.utils.book_append_sheet(wb, ws2, "沿革事件");
  XLSX.utils.book_append_sheet(wb, ws3, "引文");
  XLSX.utils.book_append_sheet(wb, ws4, "字段说明");
  XLSX.writeFile(wb, filename || "电子工业地图数据.xlsx");
}
