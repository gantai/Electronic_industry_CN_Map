import { YEAR_MIN, YEAR_MAX } from "./consts.js";

export const today = () => new Date().toISOString().slice(0, 10);
export const uid = (p) => p + Date.now().toString(36) + Math.floor(Math.random() * 90 + 10);
export const clone = (o) => JSON.parse(JSON.stringify(o));
export const clampYear = (y) => Math.max(YEAR_MIN, Math.min(YEAR_MAX, y));
export const truthy = (v) => v === true || v === "是" || v === "1" || v === 1 || String(v).toLowerCase() === "true";
export const splitIds = (s) => String(s || "").split(/[;,;,、\s]+/).map((x) => x.trim()).filter(Boolean);
