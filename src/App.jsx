import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import * as d3 from "d3";
import { Play, Pause, ChevronLeft, ChevronRight, X, Plus, Minus, Upload, Download, Search, Crosshair } from "lucide-react";
import GEO_RAW from "./china.geo.json";
import { SEED } from "./seed.js";
import { YEAR_MIN, YEAR_MAX, TYPE_META, EVENT_META, HUB_LABELS } from "./consts.js";
import { clone, clampYear } from "./utils.js";
import { EMPTY_DATA, parseWorkbookBuffer, exportWorkbook } from "./xlsxio.js";

/* ============================================================
   中国电子工业历史地图 · Historical Atlas of China's Electronics Industry
   Single-maintainer build:
   · 数据源 = 仓库内 public/data.xlsx(站点启动时载入,GitHub Pages 自动部署)
   · 只读展示站点:无贡献/审核功能,更新数据 = 覆盖 data.xlsx 并 push
   · 「导入 Excel」仅在本人浏览器中预览,不影响线上数据
   ============================================================ */

const CHINA = GEO_RAW;

const EXPAND_K = 2.2;

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
const GEO = rewind(CHINA);

/* ---------- helpers ---------- */
const isAlive = (e, year) => e.founded <= year && (e.ended == null || e.ended > year);

function fmtCite(c) {
  if (!c) return "";
  const bits = [];
  if (c.author && c.author !== "—") bits.push(c.author);
  bits.push("《" + c.title + "》");
  if (c.source) bits.push(c.source);
  if (c.locator) bits.push(c.locator);
  if (c.year && c.year !== "—") bits.push(c.year);
  return bits.join(",");
}


/* ============================================================ MAP ============================================================ */
function MapView({ data, byId, year, sel, setSel, flyReq, onOpenIntro }) {
  const wrapRef = useRef(null);
  const svgRef = useRef(null);
  const zoomRef = useRef(null);
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
    const z = d3.zoom().scaleExtent([1, 16]).on("zoom", (ev) => setT(ev.transform));
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

  const basePos = useMemo(() => {
    const m = {};
    if (!projection) return m;
    data.entities.forEach((e) => {
      const p = projection([e.lng, e.lat]);
      if (p && isFinite(p[0])) m[e.id] = p;
    });
    return m;
  }, [projection, data.entities]);

  const hubs = useMemo(() => {
    const g = {};
    data.entities.forEach((e) => { if (e.hub) (g[e.hub] = g[e.hub] || []).push(e.id); });
    const out = {};
    Object.entries(g).forEach(([hk, ids]) => {
      const pts = ids.map((id) => basePos[id]).filter(Boolean);
      if (!pts.length) return;
      out[hk] = { ids, cx: d3.mean(pts, (p) => p[0]), cy: d3.mean(pts, (p) => p[1]), R: 16 + ids.length * 2.1 };
    });
    return out;
  }, [data.entities, basePos]);

  const k = t.k;
  const expanded = k >= EXPAND_K;

  const posOf = useCallback((id) => {
    const e = byId[id];
    if (!e) return null;
    const h = e.hub && hubs[e.hub];
    if (h && h.ids.length > 1) {
      if (!expanded) return [h.cx, h.cy];
      const i = h.ids.indexOf(id), n = h.ids.length;
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      return [h.cx + (Math.cos(a) * h.R) / k, h.cy + (Math.sin(a) * h.R) / k];
    }
    return basePos[id] || null;
  }, [byId, hubs, basePos, k, expanded]);

  const evNear = useMemo(() => data.events.filter((v) => Math.abs(v.year - year) <= 2), [data.events, year]);
  const ghostSet = useMemo(() => {
    const s = new Set();
    evNear.forEach((v) => [...(v.from || []), ...(v.to || [])].forEach((id) => s.add(id)));
    if (sel) s.add(sel);
    return s;
  }, [evNear, sel]);

  const arcs = useMemo(() => {
    const out = [];
    evNear.forEach((v) => {
      const meta = EVENT_META[v.type] || EVENT_META["协作"];
      const pairs = [];
      if (v.to && v.to.length) v.from.forEach((f) => v.to.forEach((tt) => pairs.push([f, tt])));
      else for (let i = 1; i < v.from.length; i++) pairs.push([v.from[0], v.from[i]]);
      pairs.forEach(([a, b]) => {
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
  }, [evNear, posOf, year]);

  const zoomBy = (f) => {
    if (svgRef.current && zoomRef.current)
      d3.select(svgRef.current).transition().duration(230).call(zoomRef.current.scaleBy, f);
  };
  const resetZoom = () => {
    if (svgRef.current && zoomRef.current)
      d3.select(svgRef.current).transition().duration(320).call(zoomRef.current.transform, d3.zoomIdentity);
  };
  const flyTo = useCallback((x, y, kk) => {
    if (!svgRef.current || !zoomRef.current || !size.w) return;
    const tr = d3.zoomIdentity.translate(size.w / 2 - kk * x, size.h / 2 - kk * y).scale(kk);
    d3.select(svgRef.current).transition().duration(620).call(zoomRef.current.transform, tr);
  }, [size]);

  useEffect(() => {
    if (!flyReq || !projection) return;
    const e = byId[flyReq.id];
    if (!e) return;
    const p = basePos[e.id];
    if (p) flyTo(p[0], p[1], e.hub ? 4.6 : 5.6);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyReq, projection]);

  const onNodeHover = (ev, id) => {
    const r = wrapRef.current.getBoundingClientRect();
    setHover({ id, x: ev.clientX - r.left, y: ev.clientY - r.top });
  };

  const nodeList = useMemo(() => {
    return data.entities
      .filter((e) => basePos[e.id])
      .filter((e) => (expanded ? true : !(e.hub && hubs[e.hub] && hubs[e.hub].ids.length > 1)))
      .map((e) => ({ e, alive: isAlive(e, year), ghost: !isAlive(e, year) && ghostSet.has(e.id) }))
      .filter((n) => n.alive || n.ghost);
  }, [data.entities, basePos, expanded, hubs, year, ghostSet]);

  const hovE = hover && byId[hover.id];

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
          {provPaths.map((p) => (
            <path key={p.key} d={p.d} className="prov" strokeWidth={0.8 / k}>
              <title>{p.name}</title>
            </path>
          ))}

          {/* hub rings (expanded) */}
          {expanded && Object.entries(hubs).map(([hk, h]) => h.ids.length > 1 && (
            <g key={"ring" + hk} pointerEvents="none">
              <circle cx={h.cx} cy={h.cy} r={(h.R + 11) / k} fill="none" stroke="rgba(216,231,246,.34)"
                strokeWidth={1 / k} strokeDasharray={(3 / k) + " " + (4 / k)} />
              <text x={h.cx} y={h.cy - (h.R + 17) / k} textAnchor="middle" fontSize={10 / k}
                className="maplabel dim">{HUB_LABELS[hk] || hk}</text>
            </g>
          ))}

          {/* event arcs */}
          {arcs.map((a) => (
            <g key={a.key} opacity={a.fade} pointerEvents="none">
              <path d={a.d} fill="none" stroke={a.meta.color} strokeWidth={1.7 / k}
                strokeDasharray={a.meta.dash ? a.meta.dash.map((d) => d / k).join(" ") : undefined}
                markerEnd={"url(#arr-" + a.meta.slug + ")"}
                pathLength={a.meta.dash ? undefined : 1}
                className={a.meta.dash ? "" : "arcin"} />
              {a.v.uncertain && <circle cx={a.mid[0]} cy={a.mid[1]} r={2.4 / k} fill="#E4573D" />}
              {k >= 2.1 && (
                <text x={a.mid[0]} y={a.mid[1] - 5 / k} textAnchor="middle" fontSize={9.5 / k}
                  fill={a.meta.color} className="maplabel mono">
                  {a.v.year} {a.v.type}{a.v.uncertain ? " · 待考" : ""}
                </text>
              )}
            </g>
          ))}

          {/* collapsed hub badges */}
          {!expanded && Object.entries(hubs).map(([hk, h]) => {
            if (h.ids.length < 2) return null;
            const members = h.ids.map((id) => byId[id]).filter(Boolean);
            const nAlive = members.filter((m) => isAlive(m, year)).length;
            const hasEvent = evNear.some((v) => [...(v.from || []), ...(v.to || [])].some((id) => h.ids.includes(id)));
            const holdsSel = sel && h.ids.includes(sel);
            if (!nAlive && !hasEvent && !holdsSel) return null;
            return (
              <g key={"hub" + hk} transform={"translate(" + h.cx + "," + h.cy + ")"}
                className="hubbadge" onClick={(ev) => { ev.stopPropagation(); flyTo(h.cx, h.cy, 4.2); }}>
                {hasEvent && <circle r={15 / k} fill="none" stroke="#F2C14E" strokeWidth={1 / k} className="pulse" />}
                <circle r={10 / k} fill="#16345A" stroke={hasEvent ? "#F2C14E" : "#D8E7F6"} strokeWidth={(hasEvent ? 1.8 : 1.2) / k} />
                <text textAnchor="middle" dy={3.4 / k} fontSize={9.5 / k} fill="#EAF2FB" className="mono">{nAlive}</text>
                <text x={13 / k} dy={3.4 / k} fontSize={10 / k} className="maplabel">{HUB_LABELS[hk] || hk}</text>
                <title>{(HUB_LABELS[hk] || hk) + " · 当前存续 " + nAlive + " 个单位,点击放大"}</title>
              </g>
            );
          })}

          {/* nodes */}
          {nodeList.map(({ e, ghost }) => {
            const p = posOf(e.id);
            if (!p) return null;
            const meta = TYPE_META[e.type] || TYPE_META.factory;
            const isSel = sel === e.id;
            const born = e.founded === year && !ghost;
            const showLabel = isSel || (expanded && k >= 2.5) || (hover && hover.id === e.id);
            return (
              <g key={e.id} transform={"translate(" + p[0] + "," + p[1] + ")"}
                className={"node" + (born ? " nb" : "")}
                onClick={(ev) => { ev.stopPropagation(); setSel(e.id); }}
                onMouseMove={(ev) => onNodeHover(ev, e.id)}
                onMouseLeave={() => setHover(null)}>
                {isSel && <circle r={10.5 / k} fill="none" stroke="#F2C14E" strokeWidth={1.6 / k} />}
                {e.type === "institute" ? (
                  <rect x={-5.2 / k} y={-5.2 / k} width={10.4 / k} height={10.4 / k} rx={1.4 / k}
                    fill={ghost ? "none" : meta.color} stroke={ghost ? meta.color : "#0E2440"}
                    strokeWidth={1.2 / k} strokeDasharray={ghost ? (3 / k) + " " + (2.4 / k) : undefined}
                    opacity={ghost ? 0.55 : 1} />
                ) : (
                  <>
                    {e.type === "group" && <circle r={8.6 / k} fill="none" stroke={meta.color} strokeWidth={1 / k} opacity={ghost ? 0.55 : 0.9} />}
                    <circle r={6 / k} fill={ghost ? "none" : meta.color} stroke={ghost ? meta.color : "#0E2440"}
                      strokeWidth={1.2 / k} strokeDasharray={ghost ? (3 / k) + " " + (2.4 / k) : undefined}
                      opacity={ghost ? 0.55 : 1} />
                    {!ghost && <circle r={2 / k} fill="#0E2440" />}
                  </>
                )}
                {e.uncertain && <circle cx={5.4 / k} cy={-5.4 / k} r={1.8 / k} fill="#E4573D" />}
                {showLabel && (
                  <text x={9 / k} dy={3.6 / k} fontSize={10.5 / k} className="maplabel strong">
                    {e.code && e.code !== "—" ? e.code : e.name.slice(0, 6)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* tooltip */}
      {hovE && hover && (
        <div className="tooltip" style={{ left: hover.x + 14, top: hover.y + 10 }}>
          <div className="tt-name">{hovE.name}</div>
          <div className="tt-meta mono">{(TYPE_META[hovE.type] || {}).label} · {hovE.founded}–{hovE.ended == null ? "…" : hovE.ended}{hovE.uncertain ? " · 待考" : ""}</div>
        </div>
      )}

      {/* zoom controls */}
      <div className="mapcontrols">
        <button className="icobtn" onClick={() => zoomBy(1.6)} aria-label="放大"><Plus size={15} /></button>
        <button className="icobtn" onClick={() => zoomBy(1 / 1.6)} aria-label="缩小"><Minus size={15} /></button>
        <button className="icobtn" onClick={resetZoom} aria-label="复位视图"><Crosshair size={15} /></button>
      </div>

      {/* legend */}
      <div className="legend">
        <div className="lg-title mono">图例 LEGEND</div>
        <div className="lg-row">
          {Object.entries(TYPE_META).map(([kk, m]) => (
            <span key={kk} className="lg-item"><i className={"sw sw-" + kk} style={{ backgroundColor: m.color }} />{m.label}</span>
          ))}
        </div>
        <div className="lg-row">
          {Object.entries(EVENT_META).map(([kk, m]) => (
            <span key={kk} className="lg-item">
              <svg width="26" height="8"><line x1="1" y1="4" x2="25" y2="4" stroke={m.color} strokeWidth="1.8"
                strokeDasharray={m.dash ? m.dash.join(" ") : undefined} /></svg>{kk}
            </span>
          ))}
          <span className="lg-item"><i className="sw sw-uncertain" />待考</span>
        </div>
      </div>
    </div>
  );
}

/* ============================================================ TIMELINE RULER ============================================================ */
function Ruler({ data, year, setYear, playing, setPlaying }) {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((en) => setW(en[0].contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const x = useMemo(() => d3.scaleLinear().domain([YEAR_MIN, YEAR_MAX]).range([14, Math.max(80, w - 14)]), [w]);
  const evYears = useMemo(() => {
    const m = {};
    data.events.forEach((v) => { (m[v.year] = m[v.year] || []).push(v); });
    return m;
  }, [data.events]);

  const setFromClient = (cx) => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setYear(clampYear(Math.round(x.invert(cx - r.left))));
  };
  const dragging = useRef(false);
  const onPD = (e) => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); setFromClient(e.clientX); };
  const onPM = (e) => { if (dragging.current) setFromClient(e.clientX); };
  const onPU = () => { dragging.current = false; };

  const years = [];
  for (let y = YEAR_MIN; y <= YEAR_MAX; y++) years.push(y);

  return (
    <div className="ruler-row" tabIndex={0} aria-label={"年份标尺,当前 " + year + " 年,左右方向键调整"}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") { setYear(clampYear(year - (e.shiftKey ? 5 : 1))); e.preventDefault(); }
        else if (e.key === "ArrowRight") { setYear(clampYear(year + (e.shiftKey ? 5 : 1))); e.preventDefault(); }
        else if (e.key === " ") { setPlaying(!playing); e.preventDefault(); }
      }}>
      <button className="icobtn play" onClick={() => setPlaying(!playing)} aria-label={playing ? "暂停" : "播放"}>
        {playing ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <button className="icobtn" onClick={() => setYear(clampYear(year - 1))} aria-label="上一年"><ChevronLeft size={15} /></button>
      <button className="icobtn" onClick={() => setYear(clampYear(year + 1))} aria-label="下一年"><ChevronRight size={15} /></button>
      <svg ref={ref} className="rulersvg" height="48"
        onPointerDown={onPD} onPointerMove={onPM} onPointerUp={onPU} onPointerCancel={onPU}>
        {w > 0 && (
          <g>
            <line x1={x(YEAR_MIN)} y1={32} x2={x(YEAR_MAX)} y2={32} stroke="rgba(216,231,246,.5)" strokeWidth="1" />
            {years.map((y) => (
              <line key={y} x1={x(y)} y1={32} x2={x(y)} y2={32 - (y % 10 === 0 ? 9 : y % 5 === 0 ? 6.5 : 3.5)}
                stroke={"rgba(216,231,246," + (y % 5 === 0 ? ".65" : ".3") + ")"} strokeWidth="1" />
            ))}
            {years.filter((y) => y % 10 === 0).map((y) => (
              <text key={"t" + y} x={x(y)} y={45} textAnchor="middle" fontSize="9.5" className="mono" fill="#7E9BBD">{y}</text>
            ))}
            {Object.entries(evYears).map(([y, vs]) => (
              <g key={"d" + y} className="evdiamond" onClick={(e) => { e.stopPropagation(); setYear(+y); }}>
                {vs.slice(0, 3).map((v, i) => (
                  <path key={i} transform={"translate(" + x(+y) + "," + (13 - i * 6.5) + ") rotate(45)"}
                    d="M-3.2,-3.2h6.4v6.4h-6.4z" fill={(EVENT_META[v.type] || {}).color || "#D8E7F6"}
                    stroke="#0E2440" strokeWidth=".7" />
                ))}
                <title>{vs.map((v) => v.year + " " + v.type + (v.uncertain ? "(待考)" : "")).join(" / ")}</title>
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
function LineageView({ data, byId, year, setYear, sel, setSel }) {
  const layout = useMemo(() => {
    const parent = {};
    data.entities.forEach((e) => { parent[e.id] = e.id; });
    const find = (a) => (parent[a] === a ? a : (parent[a] = find(parent[a])));
    const uni = (a, b) => { if (parent[a] == null || parent[b] == null) return; a = find(a); b = find(b); if (a !== b) parent[b] = a; };
    data.events.forEach((v) => {
      const all = [...(v.from || []), ...(v.to || [])].filter((id) => parent[id] != null);
      for (let i = 1; i < all.length; i++) uni(all[0], all[i]);
    });
    const fam = {};
    data.entities.forEach((e) => { const r = find(e.id); (fam[r] = fam[r] || []).push(e); });
    let famList = Object.values(fam).map((list) => {
      list.sort((a, b) => (a.founded - b.founded) || a.id.localeCompare(b.id));
      return { members: list, start: Math.min(...list.map((m) => m.founded)), label: list[0].name };
    });
    const multi = famList.filter((f) => f.members.length > 1).sort((a, b) => (b.members.length - a.members.length) || (a.start - b.start));
    const singles = famList.filter((f) => f.members.length === 1).flatMap((f) => f.members).sort((a, b) => a.founded - b.founded);
    const families = [...multi];
    if (singles.length) families.push({ members: singles, label: "其他·未关联条目", isOther: true });

    const PXY = 15, LEFT = 18, TOP = 34, ROW = 34;
    const x = (yy) => LEFT + (yy - YEAR_MIN) * PXY;
    let cy = TOP;
    const rowsY = {}, headers = [];
    families.forEach((f) => {
      headers.push({ label: f.isOther ? f.label : f.label + " 系", y: cy + 6 });
      cy += 22;
      f.members.forEach((m) => { rowsY[m.id] = cy + 10; cy += ROW; });
      cy += 16;
    });
    return { x, rowsY, headers, W: LEFT + (YEAR_MAX - YEAR_MIN + 1) * PXY + 150, H: cy + 8 };
  }, [data]);

  const { x, rowsY, headers, W, H } = layout;

  return (
    <div className="lineage-wrap">
      <div className="lineage-cap mono">横条 = 存续区间 · 竖线 = 沿革事件 · 虚线 = 待考 · 点击横条查看详情,点击空白处改变年份</div>
      <div className="lineage-scroll">
        <svg width={W} height={H} className="lineagesvg"
          onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const yy = Math.round(YEAR_MIN + (e.clientX - r.left - 18) / 15);
            setYear(clampYear(yy));
          }}>
          {Array.from({ length: Math.floor(YEAR_MAX / 5) - Math.ceil(YEAR_MIN / 5) + 1 }, (_, i) => Math.ceil(YEAR_MIN / 5) * 5 + i * 5).map((yy) => (
            <g key={yy}>
              <line x1={x(yy)} y1={24} x2={x(yy)} y2={H - 4} stroke="rgba(216,231,246,.09)" strokeWidth="1" />
              {yy % 10 === 0 && <text x={x(yy)} y={16} textAnchor="middle" fontSize="10" className="mono" fill="#7E9BBD">{yy}</text>}
            </g>
          ))}
          {headers.map((hd, i) => (
            <text key={i} x={6} y={hd.y} fontSize="11" className="famhdr">{hd.label}</text>
          ))}
          {data.entities.map((e) => {
            const ry = rowsY[e.id];
            if (ry == null) return null;
            const meta = TYPE_META[e.type] || TYPE_META.factory;
            const x1 = x(e.founded);
            const ongoing = e.ended == null;
            const x2 = ongoing ? x(YEAR_MAX) + 8 : x(e.ended);
            const bw = x2 - x1;
            const isSel = sel === e.id;
            return (
              <g key={e.id} className="lbar" onClick={(ev) => { ev.stopPropagation(); setSel(e.id); }}>
                <rect x={x1} y={ry - 7} width={Math.max(bw, 4)} height={14} rx={3}
                  fill={meta.color + "30"} stroke={isSel ? "#F2C14E" : meta.color}
                  strokeWidth={isSel ? 2.2 : 1.2}
                  strokeDasharray={e.uncertain ? "4 3" : undefined} />
                {ongoing && <path d={"M" + (x2 + 2) + "," + (ry - 5) + " L" + (x2 + 7) + "," + ry + " L" + (x2 + 2) + "," + (ry + 5)}
                  fill="none" stroke={meta.color} strokeWidth="1.4" />}
                <text x={bw >= 130 ? x1 + 7 : x2 + 12} y={ry + 4} fontSize="11"
                  className={"lbl" + (isSel ? " on" : "")}>
                  {(e.code && e.code !== "—" ? e.code + " " : "") + e.name}
                </text>
                <title>{e.name + " " + e.founded + "–" + (e.ended == null ? "…" : e.ended)}</title>
              </g>
            );
          })}
          {data.events.map((v) => {
            const meta = EVENT_META[v.type] || EVENT_META["协作"];
            const ids = [...(v.from || []), ...(v.to || [])].filter((id) => rowsY[id] != null);
            if (ids.length < 2) return null;
            const ys = ids.map((id) => rowsY[id]);
            const y1 = Math.min(...ys), y2 = Math.max(...ys);
            const xe = x(v.year);
            const dash = v.uncertain ? "4 4" : meta.dash ? meta.dash.join(" ") : undefined;
            return (
              <g key={v.id} pointerEvents="none">
                <line x1={xe} y1={y1} x2={xe} y2={y2} stroke={meta.color} strokeWidth="1.7" strokeDasharray={dash} />
                {ids.map((id) => <circle key={id} cx={xe} cy={rowsY[id]} r="3" fill={meta.color} stroke="#0E2440" strokeWidth=".8" />)}
                <text x={xe + 6} y={y1 - 6} fontSize="10" className="mono" fill={meta.color}>
                  {v.year} {v.type}{v.uncertain ? <tspan fill="#E4573D"> 待考</tspan> : null}
                </text>
              </g>
            );
          })}
          <g pointerEvents="none">
            <line x1={x(year)} y1={22} x2={x(year)} y2={H - 4} stroke="#F2C14E" strokeWidth="1.6" opacity=".9" />
            <text x={x(year) + 5} y={30} fontSize="11" className="mono" fill="#F2C14E">{year}</text>
          </g>
        </svg>
      </div>
    </div>
  );
}

/* ============================================================ DETAIL PANEL ============================================================ */
function DetailPanel({ e, data, byId, onClose, gotoEntity, gotoCitation }) {
  if (!e) return null;
  const meta = TYPE_META[e.type] || TYPE_META.factory;
  const evs = data.events
    .filter((v) => (v.from || []).includes(e.id) || (v.to || []).includes(e.id))
    .sort((a, b) => a.year - b.year);
  const cites = (e.cites || []).map((cid) => ({ cid, c: data.citations.find((c) => c.id === cid) }));
  return (
    <div className="panel" role="dialog" aria-label={e.name}>
      {e.uncertain && <div className="stamp">待考</div>}
      <div className="panel-h">
        <div>
          <div className="chiprow">
            <span className="chip mono" style={{ borderColor: meta.color, color: meta.color }}>{meta.label}</span>
            {e.code && e.code !== "—" && <span className="chip mono">{e.code}</span>}
            <span className="chip mono">{e.founded}–{e.ended == null ? "…" : e.ended}</span>
          </div>
          <h2 className="panel-name">{e.name}</h2>
          {e.en && <div className="panel-en">{e.en}</div>}
          <div className="panel-city mono">{e.city}{e.province && e.province !== e.city ? " · " + e.province : ""}</div>
        </div>
        <button className="icobtn" onClick={onClose} aria-label="关闭"><X size={15} /></button>
      </div>
      <p className="panel-intro">{e.intro || "(暂无简介)"}</p>

      <div className="panel-sec">
        <div className="sec-t mono">沿革 LINEAGE</div>
        {evs.length === 0 && <div className="dimtext">暂无沿革记录。</div>}
        {evs.map((v) => {
          const others = [...(v.from || []), ...(v.to || [])].filter((id) => id !== e.id);
          const outgoing = (v.from || []).includes(e.id) && (v.to || []).length > 0;
          const incoming = (v.to || []).includes(e.id);
          const vm = EVENT_META[v.type] || EVENT_META["协作"];
          return (
            <div key={v.id} className="evline">
              <span className="mono evyear">{v.year}</span>
              <span className="chip mono" style={{ borderColor: vm.color, color: vm.color }}>{v.type}</span>
              {v.uncertain && <span className="chip mono red">待考</span>}
              <span className="evdir">{incoming ? "由" : outgoing ? "→" : "与"}</span>
              <span className="evothers">
                {others.map((oid) => (
                  <button key={oid} className="linkbtn" onClick={() => gotoEntity(oid, v.year)}>
                    {byId[oid] ? byId[oid].name : oid}
                  </button>
                ))}
              </span>
              {v.note && <div className="evnote">{v.note}</div>}
            </div>
          );
        })}
      </div>

      <div className="panel-sec">
        <div className="sec-t mono">引文 SOURCES</div>
        {cites.length === 0 && <div className="dimtext">暂无引文 —— 欢迎在「贡献」页补充。</div>}
        {cites.map(({ cid, c }, i) => (
          <div key={cid} className="citline">
            <button className="linkbtn mono" onClick={() => gotoCitation(cid)}>[{cid}]</button>
            <span>{c ? fmtCite(c) : "(引文表中未收录)"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============================================================ CITATIONS ============================================================ */
function CitationsView({ data, usedBy, citeFocus, gotoEntity, onImportFile, onExport }) {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("全部");
  const rowRefs = useRef({});
  const kinds = useMemo(() => ["全部", ...Array.from(new Set(data.citations.map((c) => c.kind).filter(Boolean)))], [data.citations]);
  const list = useMemo(() => data.citations.filter((c) => {
    if (kind !== "全部" && c.kind !== kind) return false;
    if (!q.trim()) return true;
    const hay = [c.id, c.author, c.title, c.source, c.locator, c.year, c.note, c.contributor].join(" ").toLowerCase();
    return hay.includes(q.trim().toLowerCase());
  }), [data.citations, q, kind]);

  useEffect(() => {
    if (citeFocus && rowRefs.current[citeFocus.id]) {
      rowRefs.current[citeFocus.id].scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [citeFocus]);

  return (
    <div className="pagepad">
      <div className="toolbar">
        <div className="searchbox">
          <Search size={13} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="检索作者、题名、档号…" aria-label="检索引文" />
        </div>
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="按类别筛选">
          {kinds.map((kk) => <option key={kk}>{kk}</option>)}
        </select>
        <span className="dimtext mono">{list.length} / {data.citations.length} 条</span>
        <span className="spacer" />
        <label className="btn btn-ghost">
          <Upload size={13} /> 导入 Excel
          <input type="file" accept=".xlsx,.xls" style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) onImportFile(f); e.target.value = ""; }} />
        </label>
        <button className="btn btn-y" onClick={onExport}><Download size={13} /> 导出 Excel</button>
      </div>
      <div className="notebar">
        全站数据来自仓库中的 <b>public/data.xlsx</b>(节点 / 沿革事件 / 引文三表),站点启动时读取。
        更新流程:「导出 Excel」取回当前数据 → 在 Excel 中编辑 → 用「导入 Excel」在本机预览核对 → 覆盖仓库中的 public/data.xlsx 并 push。
        导入只影响你自己这一次浏览,不会改变线上内容。
      </div>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th className="mono">编号</th><th>类别</th><th>作者 / 机构</th><th>题名</th><th>出处</th>
              <th>卷期·档号·页码</th><th className="mono">年份</th><th>被引用</th><th>贡献者</th>
            </tr>
          </thead>
          <tbody>
            {list.map((c) => (
              <tr key={c.id} ref={(el) => { rowRefs.current[c.id] = el; }}
                className={citeFocus && citeFocus.id === c.id ? "hl" : ""}>
                <td className="mono">{c.id}</td>
                <td><span className="chip mono">{c.kind || "—"}</span></td>
                <td>{c.author}</td>
                <td>{c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="a">{c.title}</a> : c.title}</td>
                <td>{c.source}</td>
                <td className="mono small">{c.locator}</td>
                <td className="mono">{c.year}</td>
                <td>
                  {(usedBy[c.id] || []).map((u, i) => (
                    <button key={i} className="chipbtn mono" onClick={() => u.go()}>{u.label}</button>
                  ))}
                </td>
                <td className="small">{c.contributor}<div className="dimtext mono small">{c.added}</div></td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={9} className="dimtext" style={{ textAlign: "center", padding: 24 }}>没有匹配的引文。清空检索词,或点右上「导入 Excel」载入你的引文表。</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ============================================================ APP ============================================================ */
export default function App() {
  const [data, setData] = useState(() => clone(SEED));
  const [boot, setBoot] = useState("loading");
  const [preview, setPreview] = useState(null);
  const [tab, setTab] = useState("map");
  const [year, setYear] = useState(1958);
  const [playing, setPlaying] = useState(false);
  const [sel, setSel] = useState(null);
  const [citeFocus, setCiteFocus] = useState(null);
  const [toast, setToast] = useState(null);
  const [introOpen, setIntroOpen] = useState(true);
  const [flyReq, setFlyReq] = useState(null);

  const byId = useMemo(() => Object.fromEntries(data.entities.map((e) => [e.id, e])), [data.entities]);

  /* ----- boot: load published data.xlsx ----- */
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(import.meta.env.BASE_URL + "data.xlsx", { cache: "no-store" });
        if (res.ok) {
          const published = parseWorkbookBuffer(await res.arrayBuffer(), EMPTY_DATA).next;
          if (published.entities.length) { setData(published); setBoot("done"); return; }
        }
      } catch (e) { /* fall through to bundled seed */ }
      setToast({ msg: "未能载入 data.xlsx,当前显示内置示例数据", n: Date.now() });
      setBoot("done");
    })();
  }, []);

  const showToast = useCallback((msg) => setToast({ msg, n: Date.now() }), []);
  useEffect(() => {
    if (!toast) return;
    const h = setTimeout(() => setToast(null), 3200);
    return () => clearTimeout(h);
  }, [toast]);

  /* ----- playback ----- */
  useEffect(() => {
    if (!playing) return;
    const iv = setInterval(() => {
      setYear((y) => { if (y >= YEAR_MAX) { setPlaying(false); return y; } return y + 1; });
    }, 640);
    return () => clearInterval(iv);
  }, [playing]);

  /* ----- navigation helpers ----- */
  const gotoEntity = useCallback((id, y) => {
    setTab("map");
    setSel(id);
    if (y != null) setYear(clampYear(y));
    setFlyReq({ id, n: Date.now() });
    setIntroOpen(false);
  }, []);
  const gotoCitation = useCallback((cid) => { setTab("citations"); setCiteFocus({ id: cid, n: Date.now() }); }, []);

  const usedBy = useMemo(() => {
    const m = {};
    data.entities.forEach((e) => (e.cites || []).forEach((c) => {
      (m[c] = m[c] || []).push({ label: e.code && e.code !== "—" ? e.code : e.name.slice(0, 5), go: () => gotoEntity(e.id) });
    }));
    data.events.forEach((v) => (v.cites || []).forEach((c) => {
      (m[c] = m[c] || []).push({ label: v.year + v.type, go: () => { if (v.from && v.from[0]) gotoEntity(v.from[0], v.year); } });
    }));
    return m;
  }, [data, gotoEntity]);

  /* ----- Excel import (local preview only) / export ----- */
  const onImportFile = (file) => {
    const rd = new FileReader();
    rd.onload = (ev) => {
      try {
        const { next, counts } = parseWorkbookBuffer(ev.target.result, data);
        if (!counts.any) { showToast("导入失败:未找到「节点 / 沿革事件 / 引文」任一工作表"); return; }
        setSel(null);
        setData(next);
        setPreview(file.name || "本地文件");
        showToast("已载入本地预览:节点 " + counts.ne + " · 事件 " + counts.nv + " · 引文 " + counts.nc +
          (counts.skipped ? " · 跳过 " + counts.skipped + " 行(缺 id/名称/年份)" : "") + "。仅本次浏览可见。");
      } catch (err) {
        showToast("导入失败:无法解析该文件(" + (err && err.message) + ")");
      }
    };
    rd.readAsArrayBuffer(file);
  };

  const onExport = () => {
    try { exportWorkbook(data, "data.xlsx"); }
    catch (err) { showToast("导出失败:" + (err && err.message)); }
  };

  const selE = sel ? byId[sel] : null;

  const TABS = [["map", "地图"], ["lineage", "谱系"], ["citations", "引文"]];

  if (boot === "loading") {
    return (
      <div className="ec-root">
        <style>{CSS_TEXT}</style>
        <div className="bootbox">
          <div style={{ fontFamily: "var(--serif)", fontSize: 20, letterSpacing: 3 }}>中国电子工业历史地图</div>
          <div className="mono dim" style={{ marginTop: 8, fontSize: 11, letterSpacing: 2 }}>正在载入 data.xlsx …</div>
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
          <div className="ttl-en mono">HISTORICAL ATLAS OF CHINA'S ELECTRONICS INDUSTRY · {YEAR_MIN}–{YEAR_MAX}</div>
        </div>
        <nav className="tabs" aria-label="页面切换">
          {TABS.map(([k, lab]) => (
            <button key={k} className={"tab" + (tab === k ? " on" : "")} onClick={() => setTab(k)}>{lab}</button>
          ))}
        </nav>
        <div className="hdr-right">
          {preview && (
            <button className="chip mono storchip" onClick={() => window.location.reload()}
              title="当前显示的是你导入的本地文件,线上数据未改变。点击可放弃预览、重新载入线上 data.xlsx。">
              ● 本地预览:{preview} ✕
            </button>
          )}
        </div>
      </header>

      <main className="content">
        {tab === "map" && (
          <>
            <MapView data={data} byId={byId} year={year} sel={sel} setSel={(id) => { setSel(id); if (id) setIntroOpen(false); }} flyReq={flyReq} />
            {!selE && introOpen && (
              <div className="panel introcard">
                <div className="panel-h">
                  <h2 className="panel-name">使用说明</h2>
                  <button className="icobtn" onClick={() => setIntroOpen(false)} aria-label="关闭"><X size={15} /></button>
                </div>
                <p className="panel-intro">拖动下方<b>年份标尺</b>或按 ▶ 播放,观察工厂的兴建、分立与合并;滚轮缩放、点击节点查看厂史气泡;酒仙桥等同址厂区在放大后会自动散开。</p>
                <p className="panel-intro">「谱系」页以年表形式呈现全部沿革关系,「引文」页可检索全部史料出处并回溯到对应条目。</p>
                <button className="btn btn-ghost small" onClick={() => { setTab("lineage"); }}>查看「谱系」年表 →</button>
              </div>
            )}
            {selE && <DetailPanel e={selE} data={data} byId={byId} onClose={() => setSel(null)}
              gotoEntity={gotoEntity} gotoCitation={gotoCitation} />}
            <Ruler data={data} year={year} setYear={setYear} playing={playing} setPlaying={setPlaying} />
          </>
        )}

        {tab === "lineage" && (
          <>
            <LineageView data={data} byId={byId} year={year} setYear={setYear} sel={sel} setSel={setSel} />
            {selE && <DetailPanel e={selE} data={data} byId={byId} onClose={() => setSel(null)}
              gotoEntity={gotoEntity} gotoCitation={gotoCitation} />}
          </>
        )}

        {tab === "citations" && (
          <CitationsView data={data} usedBy={usedBy} citeFocus={citeFocus}
            gotoEntity={gotoEntity} onImportFile={onImportFile} onExport={onExport} />
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
  --yellow:#F2C14E; --cyan:#7ED8E8; --violet:#C9B8FF; --red:#E4573D;
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
.a{color:var(--cyan)}
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

/* layout */
.content{position:relative;flex:1;display:flex;flex-direction:column;min-height:0}
.pagepad{padding:16px 18px;overflow:auto;flex:1;min-height:0}

/* map */
.maparea{position:relative;flex:1;min-height:0;cursor:grab}
.maparea:active{cursor:grabbing}
.mapsvg{display:block;width:100%;height:100%}
.prov{fill:rgba(216,231,246,.05);stroke:rgba(216,231,246,.4)}
.prov:hover{fill:rgba(216,231,246,.09)}
.node{cursor:pointer}
.maplabel{fill:#EAF2FB;paint-order:stroke;stroke:#0E2440;stroke-width:2.6px;stroke-linejoin:round;font-family:var(--sans)}
.maplabel.strong{font-weight:600}
.maplabel.dim{fill:#9FB8D4}
.maplabel.mono{font-family:var(--mono)}
.hubbadge{cursor:pointer}
.tooltip{position:absolute;pointer-events:none;background:rgba(10,24,43,.94);border:1px solid var(--line);
  padding:6px 9px;border-radius:2px;max-width:230px;z-index:15}
.tt-name{font-family:var(--serif);font-size:13px}
.tt-meta{font-size:10px;color:var(--dim);margin-top:1px}
.mapcontrols{position:absolute;top:12px;left:12px;display:flex;flex-direction:column;gap:5px;z-index:10}
.icobtn{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;
  border:1px solid var(--line);border-radius:2px;background:rgba(13,29,51,.85);color:var(--paper2)}
.icobtn:hover{border-color:var(--yellow);color:var(--yellow)}
.legend{position:absolute;bottom:12px;left:12px;background:rgba(10,24,43,.88);border:1px solid var(--line);
  padding:8px 11px;border-radius:2px;z-index:10;max-width:78%}
.lg-title{font-size:9px;letter-spacing:.18em;color:var(--dim);margin-bottom:5px}
.lg-row{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;font-size:11px;color:var(--paper2)}
.lg-row+.lg-row{margin-top:4px}
.lg-item{display:inline-flex;align-items:center;gap:5px}
.sw{display:inline-block;width:9px;height:9px;border-radius:50%;border:1px solid #0E2440}
.sw-institute{border-radius:1.5px}
.sw-group{box-shadow:0 0 0 2.5px rgba(201,184,255,.45)}
.sw-uncertain{background:var(--red);width:7px;height:7px;border:none}

/* ruler */
.ruler-row{flex:none;display:flex;align-items:center;gap:7px;padding:7px 14px 9px;border-top:1px solid var(--line);
  background:rgba(10,24,43,.8);z-index:12}
.rulersvg{flex:1;min-width:0;touch-action:none;cursor:ew-resize;display:block}
.yeardisp{font-size:25px;color:var(--yellow);letter-spacing:2px;width:76px;text-align:right}
.icobtn.play{border-color:var(--yellow);color:var(--yellow)}
.evdiamond{cursor:pointer}

/* panel */
.panel{position:absolute;top:14px;right:14px;bottom:76px;width:330px;overflow-y:auto;z-index:14;
  background:rgba(17,36,62,.96);border:1px solid var(--line);border-radius:2px;padding:15px 16px;
  box-shadow:0 8px 30px rgba(0,0,0,.35)}
.introcard{bottom:auto;max-height:calc(100% - 96px)}
.panel-h{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.panel-name{font-family:var(--serif);font-size:19px;font-weight:600;letter-spacing:1px;margin-top:6px;line-height:1.4}
.panel-en{font-size:10.5px;color:var(--dim);letter-spacing:.06em;margin-top:1px}
.panel-city{font-size:11px;color:var(--paper2);margin-top:4px}
.panel-intro{margin-top:10px;font-size:13px;color:var(--paper2);text-align:justify}
.panel-sec{margin-top:14px;border-top:1px dashed var(--line);padding-top:10px}
.sec-t{font-size:9.5px;letter-spacing:.2em;color:var(--dim);margin-bottom:7px}
.chiprow{display:flex;flex-wrap:wrap;gap:5px}
.chip{display:inline-block;border:1px solid var(--line);color:var(--paper2);font-size:10px;
  padding:1.5px 7px;border-radius:2px;letter-spacing:.06em;white-space:nowrap}
.chip.red{border-color:var(--red);color:var(--red)}
.pendchip{border-color:var(--yellow);color:var(--yellow)}
.okchip{border-color:var(--cyan);color:var(--cyan)}
.redchip{border-color:var(--red);color:var(--red)}
.evline{margin-bottom:9px;font-size:12.5px}
.evyear{color:var(--yellow);margin-right:6px}
.evdir{color:var(--dim);margin:0 5px}
.evothers{display:inline}
.evnote{color:var(--dim);font-size:11.5px;margin-top:2px;padding-left:2px}
.citline{display:flex;gap:7px;font-size:12px;color:var(--paper2);margin-bottom:7px;align-items:baseline}
.linkbtn{color:var(--cyan);text-decoration:underline dotted;text-underline-offset:3px;padding:0 1px;font-size:inherit}
.linkbtn:hover{color:var(--yellow)}
.evothers .linkbtn{margin-right:8px}
.stamp{position:absolute;top:13px;right:44px;border:2px solid var(--red);color:var(--red);
  font-family:var(--serif);font-size:13px;letter-spacing:4px;padding:2px 8px 2px 11px;transform:rotate(-8deg);opacity:.9}

/* citations table */
.toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
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
  padding:8px 10px;border-bottom:1px solid var(--line);background:rgba(13,29,51,.92);position:sticky;top:0}
td{padding:7px 10px;border-bottom:1px solid rgba(216,231,246,.1);vertical-align:top;color:var(--paper2)}
tr.hl td{background:rgba(242,193,78,.14);color:var(--paper)}
.chipbtn{border:1px solid var(--line);color:var(--cyan);font-size:10px;padding:1px 6px;margin:1px 3px 1px 0;border-radius:2px}
.chipbtn:hover{border-color:var(--cyan)}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:2px;
  padding:6px 13px;font-size:12.5px;letter-spacing:1px;color:var(--paper2);background:rgba(13,29,51,.6)}
.btn:hover{border-color:var(--paper2);color:var(--paper)}
.btn-y{background:var(--yellow);border-color:var(--yellow);color:#0E2440;font-weight:600}
.btn-y:hover{background:#f7d075;color:#0E2440}
.btn-ghost{background:none}
.btn-red{border-color:var(--red);color:var(--red);background:none}
.btn-red:hover{background:rgba(228,87,61,.12);color:var(--red)}
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

.bootbox{margin:auto;text-align:center;color:var(--paper2)}
a.btn{text-decoration:none}

/* toast */
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);z-index:60;
  background:rgba(10,24,43,.96);border:1px solid var(--yellow);color:var(--paper);
  padding:9px 16px;font-size:12.5px;border-radius:2px;max-width:82%;box-shadow:0 6px 24px rgba(0,0,0,.4)}

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
  .panel{left:10px;right:10px;top:auto;bottom:74px;width:auto;max-height:46%}
  .introcard{bottom:74px;max-height:52%}
  .yeardisp{font-size:19px;width:52px}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none !important;transition:none !important}
}
`;
