import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import * as d3 from "d3";
import { Play, Pause, ChevronLeft, ChevronRight, X, Plus, Minus, Upload, Download, Search, Crosshair } from "lucide-react";
import GEO_RAW from "./china.geo.json";
import CITY_RAW from "./city.geo.json";
import { INDUSTRY_META, industryMeta, TYPE_META, EVENT_META, eventMeta, STAT_FIELDS, PRECISION_LABEL } from "./consts.js";
import { clampYear, fmtDate, fmtNum, stripLeadingDate } from "./utils.js";
import { parseWorkbook, exportWorkbook, nameAt, EMPTY_DATA } from "./xlsxio.js";
import { loadBundledWorkbook, SOURCE_FILE } from "./data.js";

/* ============================================================
   中国电子工业历史地图 · Historical Atlas of China's Electronics Industry
   · 数据源 = 仓库根目录的 CN_Electronic_Industry.xlsx,构建时内联进产物
   · 只读展示站点:更新数据 = 覆盖该 xlsx 并 push,Actions 自动重建
   · 「导入 Excel」仅在本人浏览器中预览,不影响线上数据
   ============================================================ */

const EXPAND_PX = 90;   // 同城单位散开所需的屏上跨度
/* 放大上限:约当视野宽 7 km。再放大只会把「街段级近似」的落点显示得
   像实测点位,超出数据本身的精度,故到此为止。 */
const MAX_K = 1200;
const FADE_FROM = 15, FADE_TO = 45;  // 省界底图在城市尺度上淡出

/* ---------- geo: rewind polygons for d3's spherical winding ---------- */
function rewind(fc) {
  const f = JSON.parse(JSON.stringify(fc));
  const rev = (rings) => rings.map((r) => r.slice().reverse());
  f.features.forEach((ft) => {
    const g = ft.geometry;
    if (d3.geoArea({ type: "Feature", geometry: g }) > 2 * Math.PI) {
      if (g.type === "Polygon") g.coordinates = rev(g.coordinates);
      else if (g.type === "MultiPolygon") g.coordinates = g.coordinates.map(rev);
    }
  });
  return f;
}
const GEO = rewind(GEO_RAW);
/* 城市尺度的区界底图(现为上海 16 区);与省界层交叉淡入淡出 */
const CITY = rewind(CITY_RAW);
const CITY_ATTR = CITY_RAW.attribution || "";

/* ---------- helpers ---------- */
const isAlive = (u, year) => !!u.start && u.start.y <= year && (u.end == null || u.end.y > year);
const spanText = (u) =>
  (u.start ? fmtDate(u.start) : "年份待考") + "–" + (u.end ? fmtDate(u.end) : "…");
const cityLabel = (s) => ({ Shanghai: "上海", shanghai: "上海" }[s] || s);

/** 单链聚类:把彼此在 ~60km 内的单位归为一「城」,低倍下折叠成一个徽标。
    用地理距离而非 City 列,新增其他城市的数据时无需另行配置。 */
function clusterUnits(units, thresholdDeg = 0.6) {
  const parent = units.map((_, i) => i);
  const find = (a) => (parent[a] === a ? a : (parent[a] = find(parent[a])));
  for (let i = 0; i < units.length; i++) {
    for (let j = i + 1; j < units.length; j++) {
      const dy = units[i].lat - units[j].lat;
      const dx = (units[i].lng - units[j].lng) * Math.cos((units[i].lat * Math.PI) / 180);
      if (Math.hypot(dy, dx) <= thresholdDeg) {
        const a = find(i), b = find(j);
        if (a !== b) parent[b] = a;
      }
    }
  }
  const g = {};
  units.forEach((u, i) => { const r = find(i); (g[r] = g[r] || []).push(u); });
  return Object.values(g).map((members) => {
    const names = members.map((m) => cityLabel(m.city)).filter(Boolean);
    const tally = {};
    names.forEach((n) => { tally[n] = (tally[n] || 0) + 1; });
    const top = Object.entries(tally).sort((a, b) => b[1] - a[1])[0];
    const dists = Array.from(new Set(members.map((m) => m.district).filter(Boolean)));
    return { ids: members.map((m) => m.id), label: top ? top[0] : dists[0] || "未定位" };
  });
}

/* ============================================================ MAP ============================================================ */
function MapView({ data, byId, year, sel, setSel, flyReq, shown }) {
  const wrapRef = useRef(null);
  const svgRef = useRef(null);
  const zoomRef = useRef(null);
  const didFit = useRef(false);
  const lastData = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [t, setT] = useState(() => d3.zoomIdentity);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((en) => {
      const r = en[0].contentRect;
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const s = d3.select(svg);
    const z = d3.zoom().scaleExtent([1, MAX_K]).on("zoom", (ev) => setT(ev.transform));
    zoomRef.current = z;
    s.call(z);
    return () => { s.on(".zoom", null); };
  }, []);

  const projection = useMemo(() => {
    if (size.w < 60 || size.h < 60) return null;
    return d3.geoConicEqualArea().parallels([25, 47]).rotate([-105, 0])
      .fitExtent([[16, 16], [size.w - 16, size.h - 16]], GEO);
  }, [size]);

  const geoPath = useMemo(() => (projection ? d3.geoPath(projection) : null), [projection]);
  const provPaths = useMemo(
    () => (geoPath ? GEO.features.map((f, i) => ({ d: geoPath(f), key: i, name: f.properties && f.properties.name })) : []),
    [geoPath]
  );
  const cityPaths = useMemo(
    () => (geoPath ? CITY.features.map((f, i) => ({
      d: geoPath(f), key: i, name: f.properties.name, c: geoPath.centroid(f),
    })) : []),
    [geoPath]
  );

  /* 每个单位的地理落点 */
  const basePos = useMemo(() => {
    const m = {};
    if (!projection) return m;
    data.units.forEach((u) => {
      const p = projection([u.lng, u.lat]);
      if (p && isFinite(p[0])) m[u.id] = p;
    });
    return m;
  }, [projection, data.units]);

  /* 同址单位(经纬度完全一致)在放大后呈环形散开,否则彼此叠死 */
  const coloc = useMemo(() => {
    const g = {};
    data.units.forEach((u) => {
      const key = u.lat.toFixed(4) + "," + u.lng.toFixed(4);
      (g[key] = g[key] || []).push(u.id);
    });
    const m = {};
    Object.values(g).forEach((ids) => {
      if (ids.length < 2) return;
      ids.forEach((id, i) => { m[id] = { i, n: ids.length, R: 26 + ids.length * 3 }; });
    });
    return m;
  }, [data.units]);

  const clusters = useMemo(() => clusterUnits(data.units), [data.units]);
  const clusterInfo = useMemo(() => {
    return clusters.map((c) => {
      const pts = c.ids.map((id) => basePos[id]).filter(Boolean);
      if (!pts.length) return null;
      let spread = 0;
      for (let i = 0; i < pts.length; i++)
        for (let j = i + 1; j < pts.length; j++)
          spread = Math.max(spread, Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]));
      return { ...c, cx: d3.mean(pts, (p) => p[0]), cy: d3.mean(pts, (p) => p[1]), spread, R: 12 + c.ids.length * 0.5 };
    }).filter(Boolean);
  }, [clusters, basePos]);

  /* 名字随年份走:1930 年的冶金所还叫中央研究院工学研究所 */
  const labelOf = useCallback((u) => {
    const nm = nameAt(u, year);
    return nm.historical ? nm.name : (u.alt || u.name);
  }, [year]);

  const k = t.k;
  const clusterOf = useMemo(() => {
    const m = {};
    clusterInfo.forEach((c, ci) => c.ids.forEach((id) => { m[id] = ci; }));
    return m;
  }, [clusterInfo]);

  const isExpanded = useCallback(
    (ci) => {
      const c = clusterInfo[ci];
      return !c || c.ids.length < 2 || c.spread * k > EXPAND_PX;
    },
    [clusterInfo, k]
  );

  const posOf = useCallback((id) => {
    const ci = clusterOf[id];
    const c = clusterInfo[ci];
    if (c && !isExpanded(ci)) return [c.cx, c.cy];
    const p = basePos[id];
    if (!p) return null;
    const co = coloc[id];
    if (!co) return p;
    const a = (co.i / co.n) * Math.PI * 2 - Math.PI / 2;
    return [p[0] + (Math.cos(a) * co.R) / k, p[1] + (Math.sin(a) * co.R) / k];
  }, [basePos, coloc, clusterInfo, clusterOf, isExpanded, k]);

  /* 比例尺:取数据中心处 0.1° 经度的投影长度换算 */
  const kmPerPx = useMemo(() => {
    if (!projection || !data.units.length) return null;
    const lat = d3.mean(data.units, (u) => u.lat), lng = d3.mean(data.units, (u) => u.lng);
    const a = projection([lng, lat]), b = projection([lng + 0.1, lat]);
    if (!a || !b) return null;
    const px = Math.hypot(b[0] - a[0], b[1] - a[1]);
    return px > 0 ? (0.1 * 111.32 * Math.cos((lat * Math.PI) / 180)) / px : null;
  }, [projection, data.units]);

  const scaleBar = useMemo(() => {
    if (!kmPerPx) return null;
    const perPx = kmPerPx / k;
    const nice = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000];
    const pick = nice.find((d) => d / perPx >= 60) || nice[nice.length - 1];
    return { km: pick, px: pick / perPx };
  }, [kmPerPx, k]);

  /* 当年「事件簿」:始建的、以及沿革链上注明当年更名 / 划归的单位。
     地图上给它们打一层黄光,播放时间轴时便能看见变动发生在哪一年。 */
  const glowMap = useMemo(() => {
    const m = new Map();
    data.units.forEach((u) => {
      if (u.start && u.start.y === year) { m.set(u.id, { kind: "born", caption: "始建" }); return; }
      const step = u.chain.find((c) => c.date && c.date.y === year);
      if (step) {
        const txt = stripLeadingDate(step.text);
        m.set(u.id, { kind: "rename", caption: txt.length > 16 ? txt.slice(0, 16) + "…" : txt });
      }
    });
    return m;
  }, [data.units, year]);

  const evNear = useMemo(
    () => data.events.filter((v) => v.year != null && Math.abs(v.year - year) <= 2),
    [data.events, year]
  );
  const ghostSet = useMemo(() => {
    const s = new Set();
    evNear.forEach((v) => [...(v.from || []), ...(v.to || [])].forEach((id) => s.add(id)));
    if (sel) s.add(sel);
    return s;
  }, [evNear, sel]);

  const arcs = useMemo(() => {
    const out = [];
    evNear.forEach((v) => {
      const meta = eventMeta(v.type);
      const pairs = [];
      if (v.to && v.to.length) v.from.forEach((f) => v.to.forEach((tt) => pairs.push([f, tt])));
      else for (let i = 1; i < v.from.length; i++) pairs.push([v.from[0], v.from[i]]);
      pairs.forEach(([a, b]) => {
        const ua = byId[a], ub = byId[b];
        if (!ua || !ub) return;
        if (!shown.has(ua.industry) && !shown.has(ub.industry)) return;
        const pa = posOf(a), pb = posOf(b);
        if (!pa || !pb) return;
        const dx = pb[0] - pa[0], dy = pb[1] - pa[1];
        if (Math.hypot(dx, dy) < 0.9) return;
        const mx = (pa[0] + pb[0]) / 2 - dy * 0.22, my = (pa[1] + pb[1]) / 2 + dx * 0.22;
        out.push({
          key: v.id + "-" + a + "-" + b, v, meta,
          d: "M" + pa[0] + "," + pa[1] + " Q" + mx + "," + my + " " + pb[0] + "," + pb[1],
          mid: [(pa[0] + 2 * mx + pb[0]) / 4, (pa[1] + 2 * my + pb[1]) / 4],
          fade: 1 - Math.abs(v.year - year) * 0.32,
        });
      });
    });
    return out;
  }, [evNear, posOf, year, byId, shown]);

  const zoomBy = (f) => {
    if (svgRef.current && zoomRef.current)
      d3.select(svgRef.current).transition().duration(230).call(zoomRef.current.scaleBy, f);
  };
  const flyTo = useCallback((x, y, kk, dur = 620) => {
    if (!svgRef.current || !zoomRef.current || !size.w) return;
    const tr = d3.zoomIdentity.translate(size.w / 2 - kk * x, size.h / 2 - kk * y).scale(kk);
    const s = d3.select(svgRef.current);
    (dur ? s.transition().duration(dur) : s).call(zoomRef.current.transform, tr);
  }, [size]);

  /* 数据全在一城时,国界尺度什么也看不清 —— 首屏自动套合到数据范围 */
  const fitData = useCallback((dur) => {
    if (!projection || !size.w) return;
    const pts = data.units.map((u) => basePos[u.id]).filter(Boolean);
    if (!pts.length) return;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const spanX = Math.max(x1 - x0, 1e-6), spanY = Math.max(y1 - y0, 1e-6);
    const kk = Math.max(1, Math.min(MAX_K, 0.78 * Math.min(size.w / spanX, size.h / spanY)));
    flyTo((x0 + x1) / 2, (y0 + y1) / 2, kk, dur);
  }, [projection, size, data.units, basePos, flyTo]);

  useEffect(() => {
    if (lastData.current !== data) { lastData.current = data; didFit.current = false; }
    if (didFit.current || !projection || !size.w) return;
    didFit.current = true;
    fitData(0);
  }, [projection, size, data, fitData]);

  useEffect(() => {
    if (!flyReq || !projection) return;
    const p = basePos[flyReq.id];
    if (p) flyTo(p[0], p[1], Math.min(MAX_K, Math.max(k, 320)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyReq, projection]);

  const onNodeHover = (ev, id) => {
    const r = wrapRef.current.getBoundingClientRect();
    setHover({ id, x: ev.clientX - r.left, y: ev.clientY - r.top });
  };

  const nodeList = useMemo(() => {
    return data.units
      .filter((u) => basePos[u.id] && shown.has(u.industry))
      .filter((u) => isExpanded(clusterOf[u.id]))
      .map((u) => ({ u, alive: isAlive(u, year), ghost: !isAlive(u, year) && ghostSet.has(u.id) }))
      .filter((n) => n.alive || n.ghost);
  }, [data.units, basePos, shown, isExpanded, clusterOf, year, ghostSet]);

  /* 贪心避让:标注太密时按「产品记录多者优先」保留,其余只在选中/悬停时显示 */
  const labelSet = useMemo(() => {
    const out = new Set();
    if (!size.w) return out;
    const FS = 10.5, boxes = [];
    /* 当年有变动的先占位置,其余按产品记录多寡排队;缩得太小时只标高亮的那几家 */
    const cand = nodeList.filter(({ u }) => k >= 45 || glowMap.has(u.id));
    cand.sort((a, b) => {
      const ga = glowMap.has(a.u.id) ? 1 : 0, gb = glowMap.has(b.u.id) ? 1 : 0;
      if (ga !== gb) return gb - ga;
      const sa = a.u.semi.length + a.u.comp.length, sb = b.u.semi.length + b.u.comp.length;
      return sb - sa || (a.u.start ? a.u.start.y : 9999) - (b.u.start ? b.u.start.y : 9999);
    }).forEach(({ u }) => {
      const p = posOf(u.id);
      if (!p) return;
      const glow = glowMap.get(u.id);
      const sx = t.x + k * p[0] + 9, sy = t.y + k * p[1];
      const text = labelOf(u);
      const w = Math.max(text.length, glow ? glow.caption.length * 0.8 : 0) * FS * 1.02;
      const h = FS + 5 + (glow ? 11 : 0);          // 高亮时下方还有一行小注
      if (sx > size.w || sx + w < 0 || sy < 0 || sy > size.h) return;
      const box = [sx, sy - (FS + 5) / 2, sx + w, sy - (FS + 5) / 2 + h];
      if (boxes.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) return;
      boxes.push(box);
      out.add(u.id);
    });
    return out;
  }, [nodeList, posOf, t, k, size, labelOf, glowMap]);

  const baseOpacity = k <= FADE_FROM ? 1 : Math.max(0, 1 - (k - FADE_FROM) / (FADE_TO - FADE_FROM));
  const cityOpacity = k <= FADE_FROM ? 0 : Math.min(1, (k - FADE_FROM) / (FADE_TO - FADE_FROM));
  const hovU = hover && byId[hover.id];

  return (
    <div className="maparea" ref={wrapRef}>
      <svg ref={svgRef} className="mapsvg" width={size.w || 1} height={size.h || 1}
        onClick={() => setSel(null)} role="img" aria-label="中国电子工业历史地图">
        <defs>
          {Object.values(EVENT_META).map((m) => (
            <marker key={m.slug} id={"arr-" + m.slug} viewBox="0 0 10 10" refX="8" refY="5"
              markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M0,0L10,5L0,10z" fill={m.color} />
            </marker>
          ))}
        </defs>
        <g transform={"translate(" + t.x + "," + t.y + ") scale(" + t.k + ")"}>
          {baseOpacity > 0 && (
            <g opacity={baseOpacity}>
              {provPaths.map((p) => (
                <path key={p.key} d={p.d} className="prov" strokeWidth={0.8 / k}>
                  <title>{p.name}</title>
                </path>
              ))}
            </g>
          )}

          {/* 区界底图:省界淡出的同时淡入,城市尺度上提供方位 */}
          {cityOpacity > 0 && (
            <g opacity={cityOpacity}>
              {cityPaths.map((p) => (
                <path key={p.key} d={p.d} className="city" strokeWidth={0.9 / k}>
                  <title>{p.name}区</title>
                </path>
              ))}
              {cityOpacity > 0.25 && cityPaths.map((p) => (
                isFinite(p.c[0]) && (
                  <text key={"cl" + p.key} x={p.c[0]} y={p.c[1]} textAnchor="middle" fontSize={15 / k}
                    className="maplabel dim" strokeWidth={3.6 / k} pointerEvents="none">{p.name}</text>
                )
              ))}
            </g>
          )}

          {/* 折叠的城市徽标 */}
          {clusterInfo.map((c, ci) => {
            if (isExpanded(ci)) return null;
            const members = c.ids.map((id) => byId[id]).filter((u) => u && shown.has(u.industry));
            const nAlive = members.filter((m) => isAlive(m, year)).length;
            const hasEvent = evNear.some((v) => [...(v.from || []), ...(v.to || [])].some((id) => c.ids.includes(id)))
              || c.ids.some((id) => glowMap.has(id));
            const holdsSel = sel && c.ids.includes(sel);
            if (!nAlive && !hasEvent && !holdsSel) return null;
            return (
              <g key={"cl" + ci} transform={"translate(" + c.cx + "," + c.cy + ")"}
                className="hubbadge" onClick={(ev) => { ev.stopPropagation(); flyTo(c.cx, c.cy, Math.max(k * 6, 60)); }}>
                {hasEvent && <circle r={15 / k} fill="none" stroke="#F2C14E" strokeWidth={1 / k} className="pulse" />}
                <circle r={10 / k} fill="#16345A" stroke={hasEvent ? "#F2C14E" : "#D8E7F6"} strokeWidth={(hasEvent ? 1.8 : 1.2) / k} />
                <text textAnchor="middle" dy={3.4 / k} fontSize={9.5 / k} fill="#EAF2FB" className="mono">{nAlive}</text>
                <text x={13 / k} dy={3.4 / k} fontSize={10 / k} strokeWidth={2.6 / k} className="maplabel">{c.label}</text>
                <title>{c.label + " · 当前存续 " + nAlive + " 个单位,点击放大"}</title>
              </g>
            );
          })}

          {/* 事件连线 */}
          {arcs.map((a) => (
            <g key={a.key} opacity={a.fade} pointerEvents="none">
              <path d={a.d} fill="none" stroke={a.meta.color} strokeWidth={1.7 / k}
                strokeDasharray={a.meta.dash ? a.meta.dash.map((dd) => dd / k).join(" ") : undefined}
                markerEnd={"url(#arr-" + a.meta.slug + ")"}
                pathLength={a.meta.dash ? undefined : 1}
                className={a.meta.dash ? "" : "arcin"} />
              {a.v.uncertain && <circle cx={a.mid[0]} cy={a.mid[1]} r={2.4 / k} fill="#E4573D" />}
              <text x={a.mid[0]} y={a.mid[1] - 5 / k} textAnchor="middle" fontSize={9.5 / k}
                fill={a.meta.color} strokeWidth={2.6 / k} className="maplabel mono">
                {a.v.year} {a.v.type}
              </text>
            </g>
          ))}

          {/* 节点 */}
          {nodeList.map(({ u, ghost }) => {
            const p = posOf(u.id);
            if (!p) return null;
            const meta = industryMeta(u.industry);
            const shape = (TYPE_META[u.type] || TYPE_META.factory).shape;
            const isSel = sel === u.id;
            const born = u.start && u.start.y === year && !ghost;
            const vague = u.precision === "city";
            const glow = glowMap.get(u.id);
            const showLabel = isSel || labelSet.has(u.id) || (hover && hover.id === u.id);
            return (
              <g key={u.id} transform={"translate(" + p[0] + "," + p[1] + ")"}
                className={"node" + (born ? " nb" : "")}
                onClick={(ev) => { ev.stopPropagation(); setSel(u.id); }}
                onMouseMove={(ev) => onNodeHover(ev, u.id)}
                onMouseLeave={() => setHover(null)}>
                {glow && (
                  <g className="glow" pointerEvents="none">
                    <circle r={11 / k} fill="#F2C14E" className="glowcore" />
                    <circle r={11 / k} fill="none" stroke="#F2C14E" strokeWidth={1.5 / k} className="glowring" />
                    <circle r={11 / k} fill="none" stroke="#F2C14E" strokeWidth={1.2 / k} className="glowring d2" />
                  </g>
                )}
                {isSel && <circle r={10.5 / k} fill="none" stroke="#F2C14E" strokeWidth={1.6 / k} />}
                {shape === "square" ? (
                  <rect x={-5.2 / k} y={-5.2 / k} width={10.4 / k} height={10.4 / k} rx={1.4 / k}
                    fill={ghost ? "none" : meta.color} stroke={ghost || vague ? meta.color : "#0E2440"}
                    strokeWidth={1.2 / k} strokeDasharray={ghost || vague ? (3 / k) + " " + (2.4 / k) : undefined}
                    opacity={ghost ? 0.55 : vague ? 0.72 : 1} />
                ) : (
                  <>
                    {shape === "ring" && <circle r={8.6 / k} fill="none" stroke={meta.color} strokeWidth={1 / k} opacity={ghost ? 0.55 : 0.9} />}
                    <circle r={6 / k} fill={ghost ? "none" : meta.color} stroke={ghost || vague ? meta.color : "#0E2440"}
                      strokeWidth={1.2 / k} strokeDasharray={ghost || vague ? (3 / k) + " " + (2.4 / k) : undefined}
                      opacity={ghost ? 0.55 : vague ? 0.72 : 1} />
                    {!ghost && !vague && <circle r={2 / k} fill="#0E2440" />}
                  </>
                )}
                {vague && <circle cx={5.4 / k} cy={-5.4 / k} r={1.8 / k} fill="#E4573D" />}
                {showLabel && (
                  <text x={9 / k} dy={3.6 / k} fontSize={10.5 / k} strokeWidth={2.6 / k} className="maplabel strong">
                    {labelOf(u)}
                  </text>
                )}
                {glow && showLabel && (
                  <text x={9 / k} dy={15 / k} fontSize={8.6 / k} strokeWidth={2.4 / k}
                    className="maplabel mono glowcap">{glow.caption}</text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* tooltip */}
      {hovU && hover && (
        <div className="tooltip" style={{ left: hover.x + 14, top: hover.y + 10 }}>
          <div className="tt-name">{labelOf(hovU)}</div>
          <div className="tt-meta mono">
            {hovU.industry} · {spanText(hovU)}
            {hovU.precision === "city" ? " · 坐标待定位" : ""}
          </div>
          {nameAt(hovU, year).historical && <div className="tt-meta">表内作「{hovU.name}」</div>}
        </div>
      )}

      {/* zoom controls */}
      <div className="mapcontrols">
        <button className="icobtn" onClick={() => zoomBy(1.6)} aria-label="放大"><Plus size={15} /></button>
        <button className="icobtn" onClick={() => zoomBy(1 / 1.6)} aria-label="缩小"><Minus size={15} /></button>
        <button className="icobtn" onClick={() => fitData(420)} aria-label="回到数据范围"><Crosshair size={15} /></button>
      </div>

      {/* scale bar */}
      {scaleBar && (
        <div className="scalebar mono">
          <svg width={scaleBar.px + 2} height="12">
            <line x1="1" y1="8" x2={scaleBar.px + 1} y2="8" stroke="#BBD3EC" strokeWidth="1.4" />
            <line x1="1" y1="3" x2="1" y2="11" stroke="#BBD3EC" strokeWidth="1.4" />
            <line x1={scaleBar.px + 1} y1="3" x2={scaleBar.px + 1} y2="11" stroke="#BBD3EC" strokeWidth="1.4" />
          </svg>
          <span>{scaleBar.km < 1 ? Math.round(scaleBar.km * 1000) + " m" : scaleBar.km + " km"}</span>
        </div>
      )}
      {cityOpacity > 0.25 && CITY_ATTR && <div className="attrib mono">{CITY_ATTR}</div>}
    </div>
  );
}

/* ============================================================ LEGEND + FILTER ============================================================ */
function Legend({ data, shown, setShown }) {
  const industries = useMemo(
    () => Array.from(new Set(data.units.map((u) => u.industry).filter(Boolean))),
    [data.units]
  );
  const toggle = (ind) => {
    const next = new Set(shown);
    if (next.has(ind)) next.delete(ind); else next.add(ind);
    setShown(next.size ? next : new Set(industries));
  };
  return (
    <div className="legend">
      <div className="lg-title mono">行业 INDUSTRY(点击筛选)</div>
      <div className="lg-row">
        {industries.map((ind) => (
          <button key={ind} className={"lg-item lg-btn" + (shown.has(ind) ? "" : " off")} onClick={() => toggle(ind)}>
            <i className="sw" style={{ backgroundColor: industryMeta(ind).color }} />{ind}
          </button>
        ))}
      </div>
      <div className="lg-row">
        <span className="lg-item"><i className="sw" style={{ background: "#BBD3EC" }} />工厂</span>
        <span className="lg-item"><i className="sw sw-square" style={{ background: "#BBD3EC" }} />研究所</span>
        <span className="lg-item"><i className="sw sw-ring" style={{ background: "#BBD3EC" }} />合资</span>
        <span className="lg-item"><i className="sw sw-uncertain" />坐标待定位</span>
      </div>
      <div className="lg-row">
        {Object.entries(EVENT_META).map(([kk, m]) => (
          <span key={kk} className="lg-item">
            <svg width="22" height="8"><line x1="1" y1="4" x2="21" y2="4" stroke={m.color} strokeWidth="1.8"
              strokeDasharray={m.dash ? m.dash.join(" ") : undefined} /></svg>{kk}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ============================================================ TIMELINE RULER ============================================================ */
function Ruler({ data, year, setYear, playing, setPlaying }) {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  const { yearMin, yearMax } = data;
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((en) => setW(en[0].contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const x = useMemo(() => d3.scaleLinear().domain([yearMin, yearMax]).range([14, Math.max(80, w - 14)]), [w, yearMin, yearMax]);

  const evYears = useMemo(() => {
    const m = {};
    data.events.forEach((v) => { if (v.year != null) (m[v.year] = m[v.year] || []).push(v); });
    return m;
  }, [data.events]);
  const prodYears = useMemo(() => {
    const m = {};
    [...data.semi, ...data.comp].forEach((p) => { if (p.date) m[p.date.y] = (m[p.date.y] || 0) + 1; });
    return m;
  }, [data.semi, data.comp]);

  const setFromClient = (cx) => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setYear(clampYear(Math.round(x.invert(cx - r.left)), yearMin, yearMax));
  };
  const dragging = useRef(false);
  const onPD = (e) => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); setFromClient(e.clientX); };
  const onPM = (e) => { if (dragging.current) setFromClient(e.clientX); };
  const onPU = () => { dragging.current = false; };

  const years = [];
  for (let y = yearMin; y <= yearMax; y++) years.push(y);

  return (
    <div className="ruler-row" tabIndex={0} aria-label={"年份标尺,当前 " + year + " 年,左右方向键调整"}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") { setYear(clampYear(year - (e.shiftKey ? 5 : 1), yearMin, yearMax)); e.preventDefault(); }
        else if (e.key === "ArrowRight") { setYear(clampYear(year + (e.shiftKey ? 5 : 1), yearMin, yearMax)); e.preventDefault(); }
        else if (e.key === " ") { setPlaying(!playing); e.preventDefault(); }
      }}>
      <button className="icobtn play" onClick={() => setPlaying(!playing)} aria-label={playing ? "暂停" : "播放"}>
        {playing ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <button className="icobtn" onClick={() => setYear(clampYear(year - 1, yearMin, yearMax))} aria-label="上一年"><ChevronLeft size={15} /></button>
      <button className="icobtn" onClick={() => setYear(clampYear(year + 1, yearMin, yearMax))} aria-label="下一年"><ChevronRight size={15} /></button>
      <svg ref={ref} className="rulersvg" height="48"
        onPointerDown={onPD} onPointerMove={onPM} onPointerUp={onPU} onPointerCancel={onPU}>
        {w > 0 && (
          <g>
            <line x1={x(yearMin)} y1={32} x2={x(yearMax)} y2={32} stroke="rgba(216,231,246,.5)" strokeWidth="1" />
            {years.map((y) => (
              <line key={y} x1={x(y)} y1={32} x2={x(y)} y2={32 - (y % 10 === 0 ? 9 : y % 5 === 0 ? 6.5 : 3.5)}
                stroke={"rgba(216,231,246," + (y % 5 === 0 ? ".65" : ".3") + ")"} strokeWidth="1" />
            ))}
            {years.filter((y) => y % 10 === 0).map((y) => (
              <text key={"t" + y} x={x(y)} y={45} textAnchor="middle" fontSize="9.5" className="mono" fill="#7E9BBD">{y}</text>
            ))}
            {/* 产品记录密度 */}
            {Object.entries(prodYears).map(([y, n]) => (
              <line key={"p" + y} x1={x(+y)} y1={36} x2={x(+y)} y2={36 - Math.min(n, 6) * 0.9 - 1.5}
                stroke="#8FD9A8" strokeWidth="1.6" opacity=".8" />
            ))}
            {Object.entries(evYears).map(([y, vs]) => (
              <g key={"d" + y} className="evdiamond" onClick={(e) => { e.stopPropagation(); setYear(+y); }}>
                {vs.slice(0, 3).map((v, i) => (
                  <path key={i} transform={"translate(" + x(+y) + "," + (13 - i * 6.5) + ") rotate(45)"}
                    d="M-3.2,-3.2h6.4v6.4h-6.4z" fill={eventMeta(v.type).color}
                    stroke="#0E2440" strokeWidth=".7" />
                ))}
                <title>{vs.map((v) => v.year + " " + v.type).join(" / ")}</title>
              </g>
            ))}
            <g pointerEvents="none">
              <line x1={x(year)} y1={4} x2={x(year)} y2={36} stroke="#F2C14E" strokeWidth="2" />
              <path d={"M" + (x(year) - 4.5) + ",40 L" + (x(year) + 4.5) + ",40 L" + x(year) + ",34 Z"} fill="#F2C14E" />
            </g>
          </g>
        )}
      </svg>
      <div className="yeardisp mono" aria-hidden="true">{year}</div>
    </div>
  );
}

/* ============================================================ LINEAGE ============================================================ */
function LineageView({ data, year, setYear, sel, setSel }) {
  const { yearMin, yearMax } = data;
  const dated = useMemo(() => data.units.filter((u) => u.start), [data.units]);

  const layout = useMemo(() => {
    const parent = {};
    dated.forEach((u) => { parent[u.id] = u.id; });
    const find = (a) => (parent[a] === a ? a : (parent[a] = find(parent[a])));
    const uni = (a, b) => { if (parent[a] == null || parent[b] == null) return; a = find(a); b = find(b); if (a !== b) parent[b] = a; };
    data.events.forEach((v) => {
      const all = [...(v.from || []), ...(v.to || [])].filter((id) => parent[id] != null);
      for (let i = 1; i < all.length; i++) uni(all[0], all[i]);
    });
    const fam = {};
    dated.forEach((u) => { const r = find(u.id); (fam[r] = fam[r] || []).push(u); });
    const famList = Object.values(fam).map((list) => {
      list.sort((a, b) => (a.start.y - b.start.y) || a.id.localeCompare(b.id));
      const ids = new Set(list.map((m) => m.id));
      /* 只由「协作」连起来的一族不是同一谱系,标作「群」以免与沿革承继混淆 */
      const hasLineage = data.events.some((v) =>
        v.type !== "协作" && [...(v.from || []), ...(v.to || [])].some((id) => ids.has(id)));
      return { members: list, start: Math.min(...list.map((m) => m.start.y)), label: list[0].name, hasLineage };
    });
    const multi = famList.filter((f) => f.members.length > 1).sort((a, b) => (b.members.length - a.members.length) || (a.start - b.start));
    const singles = famList.filter((f) => f.members.length === 1).flatMap((f) => f.members).sort((a, b) => a.start.y - b.start.y);
    const families = [...multi];
    if (singles.length) families.push({ members: singles, label: "其他 · 未见沿革关联", isOther: true });

    const PXY = 15, LEFT = 18, TOP = 34, ROW = 34;
    const x = (yy) => LEFT + (yy - yearMin) * PXY;
    let cy = TOP;
    const rowsY = {}, headers = [];
    families.forEach((f) => {
      headers.push({ label: f.isOther ? f.label : f.label + (f.hasLineage ? " 系" : " 群 · 仅协作关联"), y: cy + 6 });
      cy += 22;
      f.members.forEach((m) => { rowsY[m.id] = cy + 10; cy += ROW; });
      cy += 16;
    });
    return { x, rowsY, headers, W: LEFT + (yearMax - yearMin + 1) * PXY + 170, H: cy + 8 };
  }, [data.events, dated, yearMin, yearMax]);

  const { x, rowsY, headers, W, H } = layout;

  return (
    <div className="lineage-wrap">
      <div className="lineage-cap mono">
        横条 = 存续区间 · 竖线 = 沿革事件(据原表「Founder」列与整机研制记录推定) · 绿点 = 产品投产/研制年 · 点击横条查看详情,点击空白处改变年份
      </div>
      <div className="lineage-scroll">
        <svg width={W} height={H} className="lineagesvg"
          onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const yy = Math.round(yearMin + (e.clientX - r.left - 18) / 15);
            setYear(clampYear(yy, yearMin, yearMax));
          }}>
          {Array.from({ length: Math.floor(yearMax / 5) - Math.ceil(yearMin / 5) + 1 }, (_, i) => Math.ceil(yearMin / 5) * 5 + i * 5).map((yy) => (
            <g key={yy}>
              <line x1={x(yy)} y1={24} x2={x(yy)} y2={H - 4} stroke="rgba(216,231,246,.09)" strokeWidth="1" />
              {yy % 10 === 0 && <text x={x(yy)} y={16} textAnchor="middle" fontSize="10" className="mono" fill="#7E9BBD">{yy}</text>}
            </g>
          ))}
          {headers.map((hd, i) => (
            <text key={i} x={6} y={hd.y} fontSize="11" className="famhdr">{hd.label}</text>
          ))}
          {dated.map((u) => {
            const ry = rowsY[u.id];
            if (ry == null) return null;
            const meta = industryMeta(u.industry);
            const x1 = x(u.start.y);
            const ongoing = u.end == null;
            const x2 = ongoing ? x(yearMax) + 8 : x(u.end.y);
            const bw = x2 - x1;
            const isSel = sel === u.id;
            const prods = [...u.semi, ...u.comp].filter((p) => p.date);
            return (
              <g key={u.id} className="lbar" onClick={(ev) => { ev.stopPropagation(); setSel(u.id); }}>
                <rect x={x1} y={ry - 7} width={Math.max(bw, 4)} height={14} rx={3}
                  fill={meta.color + "30"} stroke={isSel ? "#F2C14E" : meta.color}
                  strokeWidth={isSel ? 2.2 : 1.2} />
                {ongoing && <path d={"M" + (x2 + 2) + "," + (ry - 5) + " L" + (x2 + 7) + "," + ry + " L" + (x2 + 2) + "," + (ry + 5)}
                  fill="none" stroke={meta.color} strokeWidth="1.4" />}
                {prods.map((p, i) => (
                  <circle key={p.id + i} cx={x(p.date.y)} cy={ry} r="2.1" fill="#8FD9A8" opacity=".9">
                    <title>{p.date.y + " " + p.product}</title>
                  </circle>
                ))}
                <text x={bw >= 150 ? x1 + 7 : x2 + 12} y={ry + 4} fontSize="11"
                  className={"lbl" + (isSel ? " on" : "")}>
                  {u.name}{u.alt ? "(" + u.alt + ")" : ""}
                </text>
                <title>{u.name + " " + spanText(u)}</title>
              </g>
            );
          })}
          {data.events.map((v) => {
            if (v.year == null) return null;
            const meta = eventMeta(v.type);
            const ids = [...(v.from || []), ...(v.to || [])].filter((id) => rowsY[id] != null);
            if (ids.length < 2) return null;
            const ys = ids.map((id) => rowsY[id]);
            const y1 = Math.min(...ys), y2 = Math.max(...ys);
            const xe = x(v.year);
            return (
              <g key={v.id} pointerEvents="none">
                <line x1={xe} y1={y1} x2={xe} y2={y2} stroke={meta.color} strokeWidth="1.7"
                  strokeDasharray={meta.dash ? meta.dash.join(" ") : undefined} />
                {ids.map((id) => <circle key={id} cx={xe} cy={rowsY[id]} r="3" fill={meta.color} stroke="#0E2440" strokeWidth=".8" />)}
                <text x={xe + 6} y={y1 - 6} fontSize="10" className="mono" fill={meta.color}>{v.year} {v.type}</text>
              </g>
            );
          })}
          <g pointerEvents="none">
            <line x1={x(year)} y1={22} x2={x(year)} y2={H - 4} stroke="#F2C14E" strokeWidth="1.6" opacity=".9" />
            <text x={x(year) + 5} y={30} fontSize="11" className="mono" fill="#F2C14E">{year}</text>
          </g>
        </svg>
      </div>
      {dated.length < data.units.length && (
        <div className="dimtext small" style={{ marginTop: 6 }}>
          另有 {data.units.length - dated.length} 家未标年份的单位未列入本表,见「名录」页。
        </div>
      )}
    </div>
  );
}

/* ============================================================ DETAIL PANEL ============================================================ */
function DetailPanel({ u, data, byId, onClose, gotoUnit, statsYear, year }) {
  if (!u) return null;
  const nm = nameAt(u, year);
  const meta = industryMeta(u.industry);
  const evs = data.events
    .filter((v) => (v.from || []).includes(u.id) || (v.to || []).includes(u.id))
    .sort((a, b) => (a.year || 0) - (b.year || 0));
  const stats = STAT_FIELDS.filter((f) => u.stats[f.key] != null);

  return (
    <div className="panel" role="dialog" aria-label={u.name}>
      <div className="panel-h">
        <div>
          <div className="chiprow">
            <span className="chip mono" style={{ borderColor: meta.color, color: meta.color }}>{u.industry || "—"}</span>
            <span className="chip mono">{(TYPE_META[u.type] || {}).label}</span>
            {u.alt && <span className="chip mono">{u.alt}</span>}
            <span className="chip mono">{spanText(u)}</span>
          </div>
          <h2 className="panel-name">{u.name}</h2>
          {nm.historical && <div className="panel-en">{year} 年时称「{nm.name}」</div>}
          <div className="panel-city mono">
            {u.address || "地址未著录"}
            {u.district ? " · " + u.district + "区" : ""}
            {cityLabel(u.city) ? " · " + cityLabel(u.city) : ""}
          </div>
          <div className="dimtext mono small">
            落点:{PRECISION_LABEL[u.precision] || "表内给定坐标"}{u.locNote ? " · " + u.locNote : ""}
          </div>
        </div>
        <button className="icobtn" onClick={onClose} aria-label="关闭"><X size={15} /></button>
      </div>

      {u.product && (
        <div className="panel-sec">
          <div className="sec-t mono">产品方向 SCOPE</div>
          <div className="panel-intro">{u.product}</div>
        </div>
      )}

      {u.names.length > 1 && (
        <div className="panel-sec">
          <div className="sec-t mono">名称沿革 NAMES</div>
          {u.names.map((seg, i) => {
            const till = u.names[i + 1];
            const on = seg === nm.seg;
            return (
              <div key={i} className={"nameline" + (on ? " on" : "")}>
                <span className="mono evyear">
                  {fmtDate(seg.from)}{till ? "–" + fmtDate(till.from) : "–" + (u.end ? fmtDate(u.end) : "…")}
                </span>
                <span>{seg.name}</span>
                {seg.basis === "表内名称" && <span className="chip mono dimchip">表内名称</span>}
              </div>
            );
          })}
        </div>
      )}

      {u.chain.length > 0 && (
        <div className="panel-sec">
          <div className="sec-t mono">前身沿革 PREDECESSORS</div>
          <ol className="chain">
            {u.chain.map((step, i) => (
              <li key={i}>
                {step.date && <span className="mono chaindate">{fmtDate(step.date)}</span>}
                {step.date ? stripLeadingDate(step.text) : step.text}
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="panel-sec">
        <div className="sec-t mono">沿革关系 LINKS</div>
        {evs.length === 0 && <div className="dimtext">名录内暂无可连接的沿革关系。</div>}
        {evs.map((v) => {
          const others = [...(v.from || []), ...(v.to || [])].filter((id) => id !== u.id);
          const incoming = (v.to || []).includes(u.id);
          const outgoing = (v.from || []).includes(u.id) && (v.to || []).length > 0;
          const vm = eventMeta(v.type);
          return (
            <div key={v.id} className="evline">
              <span className="mono evyear">{v.year != null ? v.year : "年份待考"}</span>
              <span className="chip mono" style={{ borderColor: vm.color, color: vm.color }}>{v.type}</span>
              <span className="chip mono dimchip">推定</span>
              <span className="evdir">{incoming ? "由" : outgoing ? "→" : "与"}</span>
              <span className="evothers">
                {others.map((oid) => (
                  <button key={oid} className="linkbtn" onClick={() => gotoUnit(oid, v.year)}>
                    {byId[oid] ? byId[oid].name : oid}
                  </button>
                ))}
              </span>
              {v.note && <div className="evnote">{v.note}</div>}
              <div className="evnote mono small">{v.basis}</div>
            </div>
          );
        })}
      </div>

      {(u.semi.length > 0 || u.comp.length > 0) && (
        <div className="panel-sec">
          <div className="sec-t mono">产品记录 PRODUCTS</div>
          {u.semi.map((p, i) => (
            <div key={"s" + i} className="prodline">
              <span className="mono evyear">{p.date ? p.date.y : "—"}</span>
              <span>{p.product || "(未著录)"}</span>
              {p.remark && <div className="evnote">{p.remark}</div>}
            </div>
          ))}
          {u.comp.map((p, i) => (
            <div key={"c" + i} className="prodline">
              <span className="mono evyear">{p.date ? p.date.y : "—"}</span>
              <span>{p.product}</span>
              <span className="chip mono">{p.unitIds.length > 1 ? "协作" : "自研"}</span>
              {(p.speed || p.word) && (
                <div className="evnote mono small">
                  {p.word ? "字长 " + p.word + " " : ""}{p.memory ? "内存 " + p.memory + " " : ""}{p.speed ? "速度 " + p.speed : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {stats.length > 0 && (
        <div className="panel-sec">
          <div className="sec-t mono">{statsYear || ""} 年概况 STATISTICS</div>
          <table className="ministat">
            <tbody>
              {stats.map((f) => (
                <tr key={f.key}><td>{f.label}</td><td className="mono">{fmtNum(u.stats[f.key])}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="dimtext mono small">数值与量纲悉依原表。</div>
        </div>
      )}

      {(u.remark || u.source) && (
        <div className="panel-sec">
          <div className="sec-t mono">备注与出处 NOTES</div>
          {u.remark && <div className="panel-intro">{u.remark}</div>}
          {u.source && <div className="dimtext small" style={{ marginTop: 6 }}>出处:{u.source}</div>}
        </div>
      )}
    </div>
  );
}

/* ============================================================ PRODUCTS ============================================================ */
function ProductsView({ data, gotoUnit, byId }) {
  const [kind, setKind] = useState("semi");
  const [q, setQ] = useState("");
  const rows = kind === "semi" ? data.semi : data.comp;
  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter((r) =>
      [r.product, r.factoryText, r.instText, r.personnel, r.remark, r.timeRaw]
        .filter(Boolean).join(" ").toLowerCase().includes(s));
  }, [rows, q]);

  const unitChips = (r) => r.unitIds.map((id) => (
    <button key={id} className="chipbtn mono" onClick={() => gotoUnit(id, r.date ? r.date.y : null)}>
      {byId[id] ? byId[id].alt || byId[id].name : id}
    </button>
  ));

  return (
    <div className="pagepad">
      <div className="toolbar">
        <div className="segmented">
          <button className={"seg" + (kind === "semi" ? " on" : "")} onClick={() => setKind("semi")}>半导体器件 · {data.semi.length}</button>
          <button className={"seg" + (kind === "comp" ? " on" : "")} onClick={() => setKind("comp")}>计算机整机 · {data.comp.length}</button>
        </div>
        <div className="searchbox">
          <Search size={13} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="检索产品、单位、人员…" aria-label="检索产品" />
        </div>
        <span className="dimtext mono">{list.length} / {rows.length} 条</span>
      </div>
      <div className="notebar">
        本页直录 <b>{SOURCE_FILE}</b> 的 {kind === "semi" ? "「Semi-Product」" : "「Comp-Product」"} 表。
        单位名称按别名对照连回名录(如「上无十三」即上海电子计算机厂);未收入名录的协作单位以原文呈现,不作链接。
      </div>
      <div className="tablewrap">
        {kind === "semi" ? (
          <table>
            <thead>
              <tr><th className="mono">年份</th><th>产品</th><th>生产单位</th><th>名录内</th><th>人员</th><th>备注</th></tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.date ? fmtDate(r.date) : r.timeRaw || "—"}</td>
                  <td>{r.product || "—"}</td>
                  <td>{r.factoryText}</td>
                  <td>{unitChips(r)}</td>
                  <td className="small">{r.personnel}</td>
                  <td className="small">{r.remark}</td>
                </tr>
              ))}
              {!list.length && <tr><td colSpan={6} className="dimtext" style={{ textAlign: "center", padding: 24 }}>没有匹配的记录。</td></tr>}
            </tbody>
          </table>
        ) : (
          <table>
            <thead>
              <tr><th className="mono">时间</th><th>机型</th><th className="mono">字长</th><th className="mono">内存</th>
                <th className="mono">速度</th><th>研制单位</th><th>生产单位</th><th>名录内</th><th>人员</th><th>备注</th></tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.id}>
                  <td className="mono small">{r.timeRaw || "—"}</td>
                  <td>{r.product}</td>
                  <td className="mono">{r.word || "—"}</td>
                  <td className="mono">{r.memory || "—"}</td>
                  <td className="mono">{r.speed || "—"}</td>
                  <td className="small">{r.instText}</td>
                  <td className="small">{r.factoryText}</td>
                  <td>{unitChips(r)}</td>
                  <td className="small">{r.personnel}</td>
                  <td className="small">{r.remark}</td>
                </tr>
              ))}
              {!list.length && <tr><td colSpan={10} className="dimtext" style={{ textAlign: "center", padding: 24 }}>没有匹配的记录。</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ============================================================ DIRECTORY ============================================================ */
function DirectoryView({ data, gotoUnit, onImportFile, onExport }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState({ key: "start", dir: 1 });
  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    const filtered = data.units.filter((u) =>
      !s || [u.name, u.alt, u.industry, u.address, u.district, u.product, u.founder, u.remark, u.source]
        .filter(Boolean).join(" ").toLowerCase().includes(s));
    const val = (u) => {
      if (sort.key === "start") return u.start ? u.start.y * 10000 + (u.start.m || 0) * 100 + (u.start.d || 0) : Infinity;
      if (sort.key === "name") return u.name;
      if (sort.key === "industry") return u.industry;
      const v = u.stats[sort.key];
      return v == null ? -Infinity : v;
    };
    return filtered.slice().sort((a, b) => {
      const va = val(a), vb = val(b);
      if (typeof va === "string" || typeof vb === "string") return String(va).localeCompare(String(vb)) * sort.dir;
      return (va - vb) * sort.dir;
    });
  }, [data.units, q, sort]);

  const th = (key, label, mono) => (
    <th className={(mono ? "mono " : "") + "sortable" + (sort.key === key ? " on" : "")}
      onClick={() => setSort((s) => ({ key, dir: s.key === key ? -s.dir : 1 }))}>
      {label}{sort.key === key ? (sort.dir > 0 ? " ▲" : " ▼") : ""}
    </th>
  );

  return (
    <div className="pagepad">
      <div className="toolbar">
        <div className="searchbox">
          <Search size={13} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="检索单位、地址、沿革…" aria-label="检索名录" />
        </div>
        <span className="dimtext mono">{list.length} / {data.units.length} 家</span>
        <span className="spacer" />
        <label className="btn btn-ghost">
          <Upload size={13} /> 导入 Excel
          <input type="file" accept=".xlsx,.xls" style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) onImportFile(f); e.target.value = ""; }} />
        </label>
        <button className="btn btn-y" onClick={onExport}><Download size={13} /> 导出 Excel</button>
      </div>
      <div className="notebar">
        全站数据来自仓库根目录的 <b>{SOURCE_FILE}</b>(Fact and Comp-Shanghai / Semi-Product / Comp-Product 三表),构建时编入产物。
        更新流程:改表 → 用「导入 Excel」在本机预览核对 → 覆盖仓库中的同名文件并 push,Actions 自动重建。导入只影响你自己这一次浏览。
        {data.statsYear ? " 统计列为 " + data.statsYear + " 年数值,量纲悉依原表。" : ""}
      </div>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              {th("name", "单位")}
              {th("industry", "行业")}
              <th>类型</th>
              {th("start", "起讫", true)}
              <th>地址</th>
              {STAT_FIELDS.map((f) => th(f.key, f.label, true))}
              <th>备注</th>
              <th>出处</th>
            </tr>
          </thead>
          <tbody>
            {list.map((u) => (
              <tr key={u.id}>
                <td>
                  <button className="linkbtn" onClick={() => gotoUnit(u.id, u.start ? u.start.y : null)}>{u.name}</button>
                  {u.alt && <div className="dimtext mono small">{u.alt}</div>}
                </td>
                <td><span className="chip mono" style={{ borderColor: industryMeta(u.industry).color, color: industryMeta(u.industry).color }}>{u.industry || "—"}</span></td>
                <td className="small">{(TYPE_META[u.type] || {}).label}</td>
                <td className="mono small">{spanText(u)}</td>
                <td className="small">
                  {u.address || <span className="dimtext">未著录</span>}
                  {u.precision === "city" && <div className="dimtext mono small">坐标待定位</div>}
                </td>
                {STAT_FIELDS.map((f) => <td key={f.key} className="mono">{fmtNum(u.stats[f.key])}</td>)}
                <td className="small">{u.remark}</td>
                <td className="small">{u.source || <span className="dimtext">—</span>}</td>
              </tr>
            ))}
            {!list.length && <tr><td colSpan={5 + STAT_FIELDS.length + 2} className="dimtext" style={{ textAlign: "center", padding: 24 }}>没有匹配的单位。</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ============================================================ APP ============================================================ */
export default function App() {
  const boot = useMemo(() => {
    try { return { data: loadBundledWorkbook(), error: null }; }
    catch (e) { return { data: EMPTY_DATA, error: (e && e.message) || String(e) }; }
  }, []);

  const [override, setOverride] = useState(null);
  const data = override || boot.data;

  const [preview, setPreview] = useState(null);
  const [tab, setTab] = useState("map");
  const [year, setYear] = useState(() => boot.data.statsYear || Math.round((boot.data.yearMin + boot.data.yearMax) / 2));
  const [playing, setPlaying] = useState(false);
  const [sel, setSel] = useState(null);
  const [toast, setToast] = useState(null);
  const [introOpen, setIntroOpen] = useState(true);
  const [flyReq, setFlyReq] = useState(null);
  const [shown, setShown] = useState(() => new Set(boot.data.units.map((u) => u.industry).filter(Boolean)));

  const byId = useMemo(() => Object.fromEntries(data.units.map((u) => [u.id, u])), [data.units]);

  useEffect(() => { setYear((y) => clampYear(y, data.yearMin, data.yearMax)); }, [data.yearMin, data.yearMax]);

  const showToast = useCallback((msg) => setToast({ msg, n: Date.now() }), []);
  useEffect(() => {
    if (!toast) return;
    const h = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(h);
  }, [toast]);

  /* ----- playback ----- */
  useEffect(() => {
    if (!playing) return;
    const iv = setInterval(() => {
      setYear((y) => { if (y >= data.yearMax) { setPlaying(false); return y; } return y + 1; });
    }, 560);
    return () => clearInterval(iv);
  }, [playing, data.yearMax]);

  const togglePlay = useCallback((v) => {
    if (v && year >= data.yearMax) setYear(data.yearMin);
    setPlaying(v);
  }, [year, data.yearMax, data.yearMin]);

  /* ----- navigation ----- */
  const gotoUnit = useCallback((id, y) => {
    setTab("map");
    setSel(id);
    if (y != null) setYear(clampYear(y, data.yearMin, data.yearMax));
    setFlyReq({ id, n: Date.now() });
    setIntroOpen(false);
  }, [data.yearMin, data.yearMax]);

  /* ----- Excel import (local preview only) / export ----- */
  const onImportFile = (file) => {
    const rd = new FileReader();
    rd.onload = (ev) => {
      try {
        const next = parseWorkbook(new Uint8Array(ev.target.result));
        setSel(null);
        setOverride(next);
        setShown(new Set(next.units.map((u) => u.industry).filter(Boolean)));
        setPreview(file.name || "本地文件");
        showToast("已载入本地预览:厂所 " + next.counts.units + " · 半导体产品 " + next.counts.semi +
          " · 整机 " + next.counts.comp + " · 推定沿革 " + next.counts.events + "。仅本次浏览可见。");
      } catch (err) {
        showToast("导入失败:" + ((err && err.message) || "无法解析该文件"));
      }
    };
    rd.readAsArrayBuffer(file);
  };

  const onExport = () => {
    try { exportWorkbook(data, SOURCE_FILE); }
    catch (err) { showToast("导出失败:" + (err && err.message)); }
  };

  const selU = sel ? byId[sel] : null;
  const TABS = [["map", "地图"], ["lineage", "谱系"], ["products", "产品"], ["directory", "名录"]];

  if (boot.error) {
    return (
      <div className="ec-root">
        <style>{CSS_TEXT}</style>
        <div className="bootbox">
          <div style={{ fontFamily: "var(--serif)", fontSize: 20, letterSpacing: 3 }}>数据表读取失败</div>
          <div className="mono dim" style={{ marginTop: 10, fontSize: 12 }}>{SOURCE_FILE} · {boot.error}</div>
          <div className="dimtext small" style={{ marginTop: 10, maxWidth: 420 }}>
            请检查仓库根目录下的 {SOURCE_FILE} 是否仍含
            「Fact and Comp-Shanghai / Semi-Product / Comp-Product」三张表。
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ec-root">
      <style>{CSS_TEXT}</style>
      <header className="hdr">
        <div className="ttl">
          <div className="ttl-zh">中国电子工业历史地图</div>
          <div className="ttl-en mono">HISTORICAL ATLAS OF CHINA'S ELECTRONICS INDUSTRY · {data.yearMin}–{data.yearMax}</div>
        </div>
        <nav className="tabs" aria-label="页面切换">
          {TABS.map(([k, lab]) => (
            <button key={k} className={"tab" + (tab === k ? " on" : "")} onClick={() => setTab(k)}>{lab}</button>
          ))}
        </nav>
        <div className="hdr-right">
          <span className="chip mono dimchip">现有数据:上海 · {data.counts.units} 家厂所</span>
          {preview && (
            <button className="chip mono storchip" onClick={() => { setOverride(null); setPreview(null); }}
              title="当前显示的是你导入的本地文件,线上数据未改变。点击可放弃预览。">
              ● 本地预览:{preview} ✕
            </button>
          )}
        </div>
      </header>

      <main className="content">
        {tab === "map" && (
          <>
            <MapView data={data} byId={byId} year={year} sel={sel}
              setSel={(id) => { setSel(id); if (id) setIntroOpen(false); }} flyReq={flyReq} shown={shown} />
            <Legend data={data} shown={shown} setShown={setShown} />
            {!selU && introOpen && (
              <div className="panel introcard">
                <div className="panel-h">
                  <h2 className="panel-name">使用说明</h2>
                  <button className="icobtn" onClick={() => setIntroOpen(false)} aria-label="关闭"><X size={15} /></button>
                </div>
                <p className="panel-intro">
                  拖动下方<b>年份标尺</b>或按 ▶ 播放,观察厂所的兴建、分立与合并;滚轮缩放、点击节点查看详情。
                  首屏已自动套合到现有数据的范围(上海),缩小即可回到全国视野。
                </p>
                <p className="panel-intro">
                  节点颜色代表行业,形状区分工厂 / 研究所 / 合资企业。<b>经纬度不在原表之中</b>,
                  是按门牌地址人工推定的近似落点(误差数百米至数公里);带红点者原表未著录地址,暂落在市中心。
                </p>
                <p className="panel-intro">
                  连线是据原表「Founder」列与整机研制记录<b>推定</b>的沿革与协作关系,详情页均注明依据。
                </p>
                <button className="btn btn-ghost small" onClick={() => setTab("lineage")}>查看「谱系」年表 →</button>
              </div>
            )}
            {selU && <DetailPanel u={selU} data={data} byId={byId} statsYear={data.statsYear} year={year}
              onClose={() => setSel(null)} gotoUnit={gotoUnit} />}
            <Ruler data={data} year={year} setYear={setYear} playing={playing} setPlaying={togglePlay} />
          </>
        )}

        {tab === "lineage" && (
          <>
            <LineageView data={data} year={year} setYear={setYear} sel={sel} setSel={setSel} />
            {selU && <DetailPanel u={selU} data={data} byId={byId} statsYear={data.statsYear} year={year}
              onClose={() => setSel(null)} gotoUnit={gotoUnit} />}
          </>
        )}

        {tab === "products" && <ProductsView data={data} byId={byId} gotoUnit={gotoUnit} />}

        {tab === "directory" && (
          <DirectoryView data={data} gotoUnit={gotoUnit} onImportFile={onImportFile} onExport={onExport} />
        )}
      </main>

      {toast && <div className="toast" role="status">{toast.msg}</div>}
    </div>
  );
}

/* ============================================================ CSS ============================================================ */
const CSS_TEXT = `
:root{
  --bg:#0F2743; --bg2:#132E4F; --panel:#16345A; --line:rgba(216,231,246,.24);
  --paper:#EAF2FB; --paper2:#BBD3EC; --dim:#7E9BBD;
  --yellow:#F2C14E; --cyan:#7ED8E8; --violet:#C9B8FF; --green:#8FD9A8; --red:#E4573D;
  --serif:"Noto Serif SC","Songti SC","STSongti-SC-Regular","SimSun",Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Segoe UI",Roboto,sans-serif;
  --mono:"SF Mono",SFMono-Regular,ui-monospace,Consolas,"Liberation Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
.ec-root{position:relative;height:100vh;display:flex;flex-direction:column;overflow:hidden;
  background:var(--bg);color:var(--paper);font-family:var(--sans);font-size:13.5px;line-height:1.65;
  background-image:linear-gradient(rgba(216,231,246,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(216,231,246,.045) 1px,transparent 1px);
  background-size:26px 26px;}
.mono{font-family:var(--mono)}
.dim,.dimtext{color:var(--dim)}
.small{font-size:11.5px}
.spacer{flex:1}
b{color:var(--paper)}
button{font-family:inherit;color:inherit;background:none;border:none;cursor:pointer}
:focus-visible{outline:2px solid var(--yellow);outline-offset:2px}

/* header */
.hdr{display:flex;align-items:center;gap:16px;padding:0 16px;height:56px;flex:none;
  border-bottom:1px solid var(--line);background:rgba(10,24,43,.75);backdrop-filter:blur(5px);z-index:20}
.ttl-zh{font-family:var(--serif);font-size:17.5px;letter-spacing:2.5px;font-weight:600}
.ttl-en{font-size:8px;letter-spacing:.24em;color:var(--dim);margin-top:1px;white-space:nowrap}
.tabs{display:flex;gap:6px;margin-left:8px}
.tab{position:relative;padding:5px 13px;border:1px solid var(--line);border-radius:2px;font-size:13px;letter-spacing:2px;color:var(--paper2)}
.tab:hover{border-color:var(--paper2);color:var(--paper)}
.tab.on{background:var(--yellow);border-color:var(--yellow);color:#0E2440;font-weight:600}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.storchip{cursor:pointer;color:var(--yellow);border-color:var(--yellow)}
.dimchip{color:var(--dim)}

/* layout */
.content{position:relative;flex:1;display:flex;flex-direction:column;min-height:0}
.pagepad{padding:16px 18px;overflow:auto;flex:1;min-height:0}

/* map */
.maparea{position:relative;flex:1;min-height:0;cursor:grab}
.maparea:active{cursor:grabbing}
.mapsvg{display:block;width:100%;height:100%}
.prov{fill:rgba(216,231,246,.05);stroke:rgba(216,231,246,.4)}
.prov:hover{fill:rgba(216,231,246,.09)}
.city{fill:rgba(216,231,246,.045);stroke:rgba(216,231,246,.33)}
.city:hover{fill:rgba(216,231,246,.1)}
.attrib{position:absolute;right:14px;bottom:38px;z-index:10;font-size:9.5px;color:var(--dim);
  background:rgba(10,24,43,.7);padding:2px 7px;border-radius:2px;max-width:56%}
.node{cursor:pointer}
/* 描边宽度在 <g> 的缩放里会被一起放大,故由各处按 1/k 显式给出,不写在这里 */
.maplabel{fill:#EAF2FB;paint-order:stroke;stroke:#0E2440;stroke-linejoin:round;font-family:var(--sans)}
.maplabel.strong{font-weight:600}
.maplabel.dim{fill:#9FB8D4}
.maplabel.mono{font-family:var(--mono)}
.hubbadge{cursor:pointer}
.tooltip{position:absolute;pointer-events:none;background:rgba(10,24,43,.94);border:1px solid var(--line);
  padding:6px 9px;border-radius:2px;max-width:250px;z-index:15}
.tt-name{font-family:var(--serif);font-size:13px}
.tt-meta{font-size:10px;color:var(--dim);margin-top:1px}
.mapcontrols{position:absolute;top:12px;left:12px;display:flex;flex-direction:column;gap:5px;z-index:10}
.icobtn{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;
  border:1px solid var(--line);border-radius:2px;background:rgba(13,29,51,.85);color:var(--paper2)}
.icobtn:hover{border-color:var(--yellow);color:var(--yellow)}
.scalebar{position:absolute;right:14px;bottom:14px;z-index:10;display:flex;align-items:center;gap:7px;
  font-size:10.5px;color:var(--paper2);background:rgba(10,24,43,.8);padding:4px 9px;border:1px solid var(--line);border-radius:2px}
.legend{position:absolute;bottom:76px;left:12px;background:rgba(10,24,43,.88);border:1px solid var(--line);
  padding:8px 11px;border-radius:2px;z-index:13;max-width:min(70%,560px)}
.lg-title{font-size:9px;letter-spacing:.18em;color:var(--dim);margin-bottom:5px}
.lg-row{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;font-size:11px;color:var(--paper2)}
.lg-row+.lg-row{margin-top:5px;padding-top:5px;border-top:1px dashed rgba(216,231,246,.14)}
.lg-item{display:inline-flex;align-items:center;gap:5px}
.lg-btn{border:1px solid transparent;border-radius:2px;padding:1px 5px;font-size:11px}
.lg-btn:hover{border-color:var(--paper2)}
.lg-btn.off{opacity:.35;text-decoration:line-through}
.sw{display:inline-block;width:9px;height:9px;border-radius:50%;border:1px solid #0E2440}
.sw-square{border-radius:1.5px}
.sw-ring{box-shadow:0 0 0 2.5px rgba(187,211,236,.4)}
.sw-uncertain{background:var(--red);width:7px;height:7px;border:none}

/* ruler */
.ruler-row{flex:none;display:flex;align-items:center;gap:7px;padding:7px 14px 9px;border-top:1px solid var(--line);
  background:rgba(10,24,43,.8);z-index:14}
.rulersvg{flex:1;min-width:0;touch-action:none;cursor:ew-resize;display:block}
.yeardisp{font-size:25px;color:var(--yellow);letter-spacing:2px;width:76px;text-align:right}
.icobtn.play{border-color:var(--yellow);color:var(--yellow)}
.evdiamond{cursor:pointer}

/* panel */
.panel{position:absolute;top:14px;right:14px;bottom:76px;width:350px;overflow-y:auto;z-index:16;
  background:rgba(17,36,62,.96);border:1px solid var(--line);border-radius:2px;padding:15px 16px;
  box-shadow:0 8px 30px rgba(0,0,0,.35)}
.introcard{bottom:auto;max-height:calc(100% - 96px)}
.panel-h{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.panel-name{font-family:var(--serif);font-size:19px;font-weight:600;letter-spacing:1px;margin-top:6px;line-height:1.4}
.panel-city{font-size:11.5px;color:var(--paper2);margin-top:4px}
.panel-intro{margin-top:6px;font-size:13px;color:var(--paper2);text-align:justify}
.panel-sec{margin-top:14px;border-top:1px dashed var(--line);padding-top:10px}
.sec-t{font-size:9.5px;letter-spacing:.2em;color:var(--dim);margin-bottom:7px}
.chiprow{display:flex;flex-wrap:wrap;gap:5px}
.chip{display:inline-block;border:1px solid var(--line);color:var(--paper2);font-size:10px;
  padding:1.5px 7px;border-radius:2px;letter-spacing:.06em;white-space:nowrap}
.chain{list-style:none;counter-reset:step;font-size:12.5px;color:var(--paper2)}
.chain li{position:relative;padding-left:18px;margin-bottom:5px}
.chain li:before{counter-increment:step;content:counter(step);position:absolute;left:0;top:1px;
  font-family:var(--mono);font-size:9.5px;color:var(--yellow);border:1px solid var(--line);
  width:13px;height:13px;line-height:11px;text-align:center;border-radius:2px}
.evline,.prodline{margin-bottom:9px;font-size:12.5px}
.evyear{color:var(--yellow);margin-right:6px}
.evdir{color:var(--dim);margin:0 5px}
.evothers{display:inline}
.evnote{color:var(--dim);font-size:11.5px;margin-top:2px;padding-left:2px}
.linkbtn{color:var(--cyan);text-decoration:underline dotted;text-underline-offset:3px;padding:0 1px;font-size:inherit;text-align:left}
.linkbtn:hover{color:var(--yellow)}
.evothers .linkbtn{margin-right:8px}
.ministat{width:100%;border-collapse:collapse;font-size:12px}
.ministat td{padding:3px 0;border-bottom:1px solid rgba(216,231,246,.1);color:var(--paper2)}
.ministat td:last-child{text-align:right;color:var(--paper)}

/* tables */
.toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.segmented{display:flex;border:1px solid var(--line);border-radius:2px;overflow:hidden}
.seg{padding:5px 12px;font-size:12.5px;color:var(--paper2);letter-spacing:1px}
.seg+.seg{border-left:1px solid var(--line)}
.seg.on{background:var(--yellow);color:#0E2440;font-weight:600}
.searchbox{display:flex;align-items:center;gap:6px;border:1px solid var(--line);padding:5px 9px;border-radius:2px;
  background:rgba(13,29,51,.7);color:var(--dim);min-width:220px}
.searchbox input{background:none;border:none;color:var(--paper);width:100%;font-size:12.5px}
.searchbox input:focus{outline:none}
select,input,textarea{background:rgba(13,29,51,.8);border:1px solid var(--line);color:var(--paper);
  border-radius:2px;padding:5px 8px;font-size:12.5px;font-family:var(--sans)}
select:focus,input:focus,textarea:focus{outline:none;border-color:var(--yellow)}
.notebar{margin:10px 0 12px;font-size:11.5px;color:var(--dim);border-left:2px solid var(--yellow);padding-left:9px}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:2px}
table{width:100%;border-collapse:collapse;font-size:12px;min-width:920px}
th{font-family:var(--serif);font-weight:600;text-align:left;letter-spacing:1px;font-size:12px;
  padding:8px 10px;border-bottom:1px solid var(--line);background:rgba(13,29,51,.92);position:sticky;top:0;white-space:nowrap}
th.sortable{cursor:pointer}
th.sortable:hover{color:var(--yellow)}
th.sortable.on{color:var(--yellow)}
td{padding:7px 10px;border-bottom:1px solid rgba(216,231,246,.1);vertical-align:top;color:var(--paper2)}
.chipbtn{border:1px solid var(--line);color:var(--cyan);font-size:10px;padding:1px 6px;margin:1px 3px 1px 0;border-radius:2px;white-space:nowrap}
.chipbtn:hover{border-color:var(--cyan)}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:2px;
  padding:6px 13px;font-size:12.5px;letter-spacing:1px;color:var(--paper2);background:rgba(13,29,51,.6)}
.btn:hover{border-color:var(--paper2);color:var(--paper)}
.btn-y{background:var(--yellow);border-color:var(--yellow);color:#0E2440;font-weight:600}
.btn-y:hover{background:#f7d075;color:#0E2440}
.btn-ghost{background:none;cursor:pointer}
.btn.small{padding:4px 9px;font-size:11.5px}

/* lineage */
.lineage-wrap{flex:1;min-height:0;display:flex;flex-direction:column;padding:12px 16px}
.lineage-cap{font-size:10px;letter-spacing:.1em;color:var(--dim);margin-bottom:8px}
.lineage-scroll{flex:1;overflow:auto;border:1px solid var(--line);border-radius:2px;background:rgba(11,26,46,.5)}
.lineagesvg{display:block}
.famhdr{fill:var(--yellow);font-family:var(--serif);letter-spacing:2px}
.lbar{cursor:pointer}
.lbl{fill:#D5E4F4;font-family:var(--sans)}
.lbl.on{fill:#fff;font-weight:600}

.bootbox{margin:auto;text-align:center;color:var(--paper2);padding:24px}

/* toast */
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);z-index:60;
  background:rgba(10,24,43,.96);border:1px solid var(--yellow);color:var(--paper);
  padding:9px 16px;font-size:12.5px;border-radius:2px;max-width:82%;box-shadow:0 6px 24px rgba(0,0,0,.4)}

/* 当年始建 / 更名的高亮:一圈黄光加两道扩散环 */
.glowcore,.glowring{transform-box:fill-box;transform-origin:center}
.glowcore{animation:glowbreath 1.6s ease-in-out infinite;opacity:.18}
@keyframes glowbreath{0%,100%{transform:scale(.8);opacity:.10}50%{transform:scale(1.18);opacity:.30}}
.glowring{animation:glowout 1.6s ease-out infinite}
.glowring.d2{animation-delay:.8s}
@keyframes glowout{0%{transform:scale(.55);opacity:.95}100%{transform:scale(2.3);opacity:0}}
.glowcap{fill:var(--yellow)}
.chaindate{color:var(--yellow);margin-right:6px;font-size:10.5px}
.nameline{font-size:12.5px;margin-bottom:5px;color:var(--paper2)}
.nameline.on{color:var(--paper)}
.nameline.on .evyear{background:rgba(242,193,78,.16);border-radius:2px;padding:0 3px}

/* animations */
.nb{animation:born .8s ease-out;transform-box:fill-box;transform-origin:center}
@keyframes born{from{transform:scale(2.4);opacity:0}to{transform:scale(1);opacity:1}}
.pulse{animation:pulse 1.6s ease-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes pulse{0%{transform:scale(.7);opacity:.9}100%{transform:scale(1.5);opacity:0}}
.arcin{stroke-dasharray:1;stroke-dashoffset:1;animation:drawin .7s ease forwards}
@keyframes drawin{to{stroke-dashoffset:0}}

/* responsive */
@media (max-width:860px){
  .hdr{gap:9px;padding:0 10px;height:auto;min-height:54px;flex-wrap:wrap;padding-top:6px;padding-bottom:6px}
  .ttl-en{display:none}
  .ttl-zh{font-size:15px}
  .tab{padding:4px 9px;font-size:12px;letter-spacing:1px}
  .hdr-right .dimchip{display:none}
  .panel{left:10px;right:10px;top:auto;bottom:74px;width:auto;max-height:46%}
  .introcard{bottom:74px;max-height:52%}
  .legend{display:none}
  .yeardisp{font-size:19px;width:52px}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none !important;transition:none !important}
}
`;
