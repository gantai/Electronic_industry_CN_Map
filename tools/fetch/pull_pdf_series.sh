#!/usr/bin/env bash
# 抓取按序号编排的 PDF series(默认:清华计算机系《AlumniExpress》校友通讯)。
#
#   https://www.cs.tsinghua.edu.cn/fujian/AlumniExpress001.pdf
#   https://www.cs.tsinghua.edu.cn/fujian/AlumniExpress002.pdf
#   ...                                                  ???
#
# 刊物共几期未知,故用「连续缺号 N 期即停」的规则收尾,既能跨过中间断号,
# 又不会无限往下试。每期都校验 %PDF 魔数,挡住返回 200 的伪 404 页面。
#
# 用法:
#   tools/fetch/pull_pdf_series.sh                 # 001 起,连缺 8 期即停
#   tools/fetch/pull_pdf_series.sh -s 40 -e 120    # 只取 040–120
#   tools/fetch/pull_pdf_series.sh -n              # 干跑,只探测不落盘
#   tools/fetch/pull_pdf_series.sh -o ~/pdf -d 5   # 换目录、每次间隔 5 秒
#
# 断点续抓:重跑即可,已存在且校验通过的文件会跳过(-f 强制重下)。

set -uo pipefail

BASE_URL="https://www.cs.tsinghua.edu.cn/fujian/AlumniExpress"
SUFFIX=".pdf"
OUT_DIR="AlumniExpress"
START=1
END=0                 # 0 = 自动,靠 MISS_LIMIT 收尾
CEILING=999           # 自动模式下的硬上限,防跑飞
MISS_LIMIT=8          # 连续缺这么多期就认为刊物到头了
PAD=3
DELAY=3
FORCE=0
DRY_RUN=0
UA="Mozilla/5.0 (compatible; pull_pdf_series/1.0; +archival use)"

usage() {
  awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
  cat <<'EOU'

选项:
  -u URL   序号前的 URL 前缀        (默认 …/fujian/AlumniExpress)
  -x EXT   序号后的后缀             (默认 .pdf)
  -o DIR   落盘目录                 (默认 ./AlumniExpress)
  -s N     起始期号                 (默认 1)
  -e N     结束期号,给了就不靠缺号收尾
  -m N     连续缺号阈值             (默认 8)
  -c N     自动模式硬上限           (默认 999)
  -p N     序号补零位数             (默认 3 → 001)
  -d SEC   每次请求间隔秒数         (默认 3)
  -f       已存在的文件也重下
  -n       干跑:只探测远端有哪些期,不保存(可先摸清总期数)
  -h       本帮助
EOU
}

while getopts "u:x:o:s:e:m:c:p:d:fnh" opt; do
  case "$opt" in
    u) BASE_URL="$OPTARG" ;;
    x) SUFFIX="$OPTARG" ;;
    o) OUT_DIR="$OPTARG" ;;
    s) START="$OPTARG" ;;
    e) END="$OPTARG" ;;
    m) MISS_LIMIT="$OPTARG" ;;
    c) CEILING="$OPTARG" ;;
    p) PAD="$OPTARG" ;;
    d) DELAY="$OPTARG" ;;
    f) FORCE=1 ;;
    n) DRY_RUN=1 ;;
    h) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

command -v curl >/dev/null || { echo "缺 curl" >&2; exit 127; }

LAST=$(( END > 0 ? END : CEILING ))
MANIFEST="$OUT_DIR/manifest.csv"
TMP=""
cleanup() { [ -n "$TMP" ] && rm -f "$TMP"; }
trap cleanup EXIT
trap 'echo; echo "已中断。续抓:$0 -s <下一期号>" >&2; exit 130' INT

if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$OUT_DIR"
  [ -f "$MANIFEST" ] || echo "no,file,bytes,sha256,url" > "$MANIFEST"
fi

is_pdf() { [ "$(head -c 4 "$1" 2>/dev/null)" = "%PDF" ]; }

sha_of() {
  if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum   >/dev/null; then shasum -a 256 "$1" | cut -d' ' -f1
  else echo "-"; fi
}

hits=0; misses=0; skipped=0; streak=0; highest=0
n="$START"

while [ "$n" -le "$LAST" ]; do
  num=$(printf "%0${PAD}d" "$n")
  url="${BASE_URL}${num}${SUFFIX}"
  dest="$OUT_DIR/$(basename "$BASE_URL")${num}${SUFFIX}"

  if [ "$DRY_RUN" -eq 0 ] && [ "$FORCE" -eq 0 ] && [ -s "$dest" ] && is_pdf "$dest"; then
    printf '%s  已有,跳过\n' "$num"
    skipped=$((skipped + 1)); streak=0; highest=$n
    n=$((n + 1)); continue
  fi

  TMP=$(mktemp "${TMPDIR:-/tmp}/pdfseries.XXXXXX")
  code=$(curl -sSL \
              --retry 3 --retry-delay 2 --retry-connrefused \
              --connect-timeout 20 --max-time 600 \
              -A "$UA" -o "$TMP" -w '%{http_code}' "$url" 2>/dev/null)
  rc=$?

  # 传输层故障(断网、DNS、被墙、超时)不算「缺号」,否则会误判刊物结束。
  if [ "$rc" -ne 0 ]; then
    echo "$num  网络错误 (curl $rc),重试仍失败;续抓:$0 -s $n" >&2
    rm -f "$TMP"; TMP=""
    exit 1
  fi

  if [ "$code" != "200" ]; then
    printf '%s  缺号 (HTTP %s)\n' "$num" "$code"
    misses=$((misses + 1)); streak=$((streak + 1))
  elif ! is_pdf "$TMP"; then
    # 200 但不是 PDF:多半是站点的软 404 / 跳转到首页。
    printf '%s  非 PDF 内容,按缺号处理 (%s 字节)\n' "$num" "$(wc -c < "$TMP" | tr -d ' ')"
    misses=$((misses + 1)); streak=$((streak + 1))
  else
    bytes=$(wc -c < "$TMP" | tr -d ' ')
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '%s  存在 (%s 字节) [干跑]\n' "$num" "$bytes"
    else
      mv "$TMP" "$dest"
      printf '%s,%s,%s,%s,%s\n' "$num" "$(basename "$dest")" "$bytes" "$(sha_of "$dest")" "$url" >> "$MANIFEST"
      printf '%s  已存 %s (%s 字节)\n' "$num" "$dest" "$bytes"
    fi
    hits=$((hits + 1)); streak=0; highest=$n
  fi

  rm -f "$TMP"; TMP=""

  if [ "$END" -le 0 ] && [ "$streak" -ge "$MISS_LIMIT" ]; then
    echo "连续 $MISS_LIMIT 期缺号,判定刊物到此为止。"
    break
  fi

  n=$((n + 1))
  [ "$n" -le "$LAST" ] && sleep "$DELAY"
done

if [ "$END" -le 0 ] && [ "$n" -gt "$CEILING" ]; then
  echo "已到硬上限 $CEILING 仍在出刊,用 -s $n -c <更大值> 继续。" >&2
fi

echo "———"
verb=$([ "$DRY_RUN" -eq 1 ] && echo "探到" || echo "下载")
echo "$verb $hits 期,跳过 $skipped 期,缺号 $misses 期,最大期号 $(printf "%0${PAD}d" "$highest")。"
[ "$DRY_RUN" -eq 0 ] && echo "清单:$MANIFEST"
