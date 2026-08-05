import B64 from "../CN_Electronic_Industry.xlsx?b64";
import { parseWorkbook } from "./xlsxio.js";

/** 数据源文件名 —— 界面与 README 中提到的那一个 */
export const SOURCE_FILE = "CN_Electronic_Industry.xlsx";

function bytesFromBase64(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** 解析随包编译进来的工作簿。构建期就已内联,不发网络请求。 */
export function loadBundledWorkbook() {
  return parseWorkbook(bytesFromBase64(B64));
}
