#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行政区划 GeoJSON → src/city.geo.json 的市辖区多边形。

    python tools/geo/添底图.py 底图源/某某.geojson 北京              # 先看认出哪些区
    python tools/geo/添底图.py 底图源/某某.geojson 北京 --write      # 并进底图
    python tools/geo/添底图.py 底图源/全国.geojson 北京 --save-subset # 只切出这一市另存

地图上放大到城市尺度时,区界是唯一的方位参照 —— 没有它,一市之内所有的点
都浮在空白上。上海的 16 个区早已在册,别的城市照这条路添。

**属性名各家不同**(shapeName / NAME_3 / name / 中文名……),所以不认字段名,
认值:哪个属性的值里带着要找的市名或区名,就拿哪个当名字。
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CITY_JSON = os.path.join(REPO, "src", "city.geo.json")

# 市名的几种写法 —— 下载来的数据可能是中文,也可能是拼音
CITY_ALIASES = {
    "北京": ["北京", "Beijing", "Peking"],
    "上海": ["上海", "Shanghai"],
    "天津": ["天津", "Tianjin"],
    "重庆": ["重庆", "Chongqing"],
    "南京": ["南京", "Nanjing"],
    "广州": ["广州", "Guangzhou"],
}

# geoBoundaries 的 CHN ADM3 只有一个英文 shapeName(「Chaoyang District」),
# 既不写省市,也没有上级编号 —— 属性里根本找不到「北京」二字。所以退一步
# 按地理认:图形落在这个方框里的,就算这个市的。方框宽松些无妨,后头还有
# 名字对照把关。(西南角经度, 纬度, 东北角经度, 纬度)
CITY_BOX = {
    "北京": (115.35, 39.40, 117.55, 41.10),
    "上海": (120.80, 30.65, 122.30, 31.95),
    "天津": (116.65, 38.50, 118.10, 40.30),
    "重庆": (105.20, 28.10, 110.25, 32.25),
}

# 英文名 → 中文名。`city.geo.json` 存中文,站点的 DISTRICT_EN 再翻回英文。
EN_TO_ZH = {
    "北京": {
        "Dongcheng": "东城", "Xicheng": "西城", "Chongwen": "崇文", "Xuanwu": "宣武",
        "Chaoyang": "朝阳", "Haidian": "海淀", "Fengtai": "丰台", "Shijingshan": "石景山",
        "Mentougou": "门头沟", "Fangshan": "房山", "Tongzhou": "通州", "Shunyi": "顺义",
        "Changping": "昌平", "Daxing": "大兴", "Huairou": "怀柔", "Pinggu": "平谷",
        "Miyun": "密云", "Yanqing": "延庆",
    },
    "上海": {
        "Huangpu": "黄浦", "Jing'an": "静安", "Jingan": "静安", "Hongkou": "虹口",
        "Yangpu": "杨浦", "Putuo": "普陀", "Changning": "长宁", "Xuhui": "徐汇",
        "Pudong": "浦东", "Minhang": "闵行", "Jiading": "嘉定", "Baoshan": "宝山",
        "Songjiang": "松江", "Qingpu": "青浦", "Jinshan": "金山", "Fengxian": "奉贤",
        "Chongming": "崇明",
    },
}

# 「Chaoyang District」「Funing County」—— 通名去掉,只留专名
EN_GENERIC = re.compile(r"\s+(District|County|City|Qu|Xian|Shi|Autonomous\s+\w+)$", re.I)


def _centroid(geom):
    """图形的大致中心 —— 只为判断落在哪个市,取第一圈的均值就够。"""
    pts = []

    def walk(x):
        if isinstance(x, list):
            if x and isinstance(x[0], (int, float)) and len(x) >= 2:
                pts.append((float(x[0]), float(x[1])))
            else:
                for v in x:
                    walk(v)
    walk(geom.get("coordinates"))
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _in_box(geom, box):
    c = _centroid(geom)
    if not c:
        return False
    x0, y0, x1, y1 = box
    return x0 <= c[0] <= x1 and y0 <= c[1] <= y1

DROP_SUFFIX = re.compile(r"(区|县|市辖区|市)$")


def _texts(props):
    """这个 feature 的属性里,所有像名字的字符串。"""
    out = []
    for v in (props or {}).values():
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _en_key(props, table):
    """这个 feature 的英文名在不在对照表里 —— 在,就返回对应的中文。"""
    for t in sorted(_texts(props), key=len):
        bare = EN_GENERIC.sub("", t).strip()
        if bare in table:
            return table[bare]
    return ""


# 「62558664B8491700699883」这样的一串是 shapeID,不是名字
ID_LIKE = re.compile(r"^[0-9A-F]{8,}$", re.I)


def _pick_name(props, city_words, city=""):
    """挑一个当区名:有中文用中文;只有英文的,按对照表翻成中文。"""
    cands = _texts(props)
    zh = [t for t in cands if re.search(r"[一-鿿]", t)]
    if zh:
        named = [t for t in zh if DROP_SUFFIX.search(t)]
        pool = [t for t in (named or zh) if t not in city_words] or (named or zh)
        return min(pool, key=len)
    # 只有英文:「Chaoyang District」→ Chaoyang → 朝阳
    table = EN_TO_ZH.get(city, {})
    for t in sorted(cands, key=len):
        bare = EN_GENERIC.sub("", t).strip()
        if bare in table:
            return table[bare]
    for t in sorted(cands, key=len):
        bare = EN_GENERIC.sub("", t).strip()
        if (bare and not bare.isdigit() and not ID_LIKE.match(bare)
                and bare not in ("CHN", "ADM3", "ADM2", "ADM1")):
            return bare          # 表里没有的,原样留着英文,免得默默丢掉
    return ""


def _round_coords(geom, nd=4):
    """坐标取到小数点后四位 —— 约 11 米,城市尺度的底图够用,文件小一半。"""
    def walk(x):
        if isinstance(x, list):
            if x and isinstance(x[0], (int, float)):
                return [round(float(v), nd) for v in x]
            return [walk(v) for v in x]
        return x
    return {"type": geom["type"], "coordinates": walk(geom["coordinates"])}


def load_city(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_city(doc, city, box=None):
    """挑出属于这个市的 feature。

    两条路,先按名字,认不出再按地理:
    - **名字** —— 属性里哪一格带着市名(有些数据源写着省市,那最省事)
    - **地理** —— 图形中心落在这个市的方框里(geoBoundaries 只给一个英文
      区名,属性里压根没有「北京」二字,只能这么认)
    """
    words = CITY_ALIASES.get(city, [city])
    feats = doc.get("features", [])
    hit = [ft for ft in feats
           if any(w in " ".join(_texts(ft.get("properties"))) for w in words)]
    if hit:
        return hit, words, "名字"
    box = box or CITY_BOX.get(city)
    if not box:
        return [], words, "名字"
    # 方框只能圈出个大概:北京四面都是河北,框里必然混进宝坻、三河、涿州、
    # 怀来这些邻县。所以框子之外还要过一道名册 —— 对照表里有名有姓的才算。
    table = EN_TO_ZH.get(city, {})
    inbox = [ft for ft in feats if _in_box(ft.get("geometry") or {}, box)]
    if not table:
        return inbox, words, "地理"
    keep, drop = [], []
    for ft in inbox:
        (keep if _en_key(ft.get("properties"), table) else drop).append(ft)
    return keep, words, ("地理", drop)


def main(argv=None):
    ap = argparse.ArgumentParser(description="行政区划 GeoJSON → 底图的区界")
    ap.add_argument("src", help="下载来的 .geojson")
    ap.add_argument("city", help="哪个市,如 北京")
    ap.add_argument("--write", action="store_true", help="并进 src/city.geo.json")
    ap.add_argument("--save-subset", action="store_true",
                    help="只把这一市另存一份小的(大文件别提交进仓库)")
    ap.add_argument("--nd", type=int, default=4, help="坐标留几位小数(默认 4)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.src):
        sys.exit("找不到文件:%s" % args.src)
    doc = load_city(args.src)
    feats, words, how = find_city(doc, args.city)
    dropped = []
    if isinstance(how, tuple):
        how, dropped = how
    print("%s 里共 %d 个 feature,按%s认出属于「%s」的 %d 个。"
          % (os.path.basename(args.src), len(doc.get("features", [])),
             how, args.city, len(feats)))
    if how == "地理":
        print("   (属性里没有市名,只好按图形落点认;再拿英文对照表过一道,"
              "把邻县剔出去)")
    if dropped:
        names = sorted(filter(None,
                              (_pick_name(f.get("properties"), words) for f in dropped)))
        print("   落在方框里、但不在「%s」名册上的 %d 个,没收:%s"
              % (args.city, len(dropped), "、".join(names[:14])))
        print("   (北京四面是河北,方框必然圈进邻县。真有该收而漏掉的,告诉我补进对照表)")
    if not feats:
        print("\n一个也没认出来。看一眼属性长什么样,再告诉我该按哪个字段找:")
        for ft in doc.get("features", [])[:3]:
            print("   %s" % json.dumps(ft.get("properties"), ensure_ascii=False)[:160])
        return 1

    named = [(_pick_name(ft.get("properties"), words, args.city), ft) for ft in feats]
    for nm, _ft in sorted(named, key=lambda x: x[0]):
        print("   %s" % (nm or "(认不出名字)"))

    if args.save_subset:
        out = os.path.join(os.path.dirname(os.path.abspath(args.src)),
                           "%s-区界.geojson" % args.city)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": feats},
                      f, ensure_ascii=False)
        print("\n只这一市的另存到 %s(%.1f MB)"
              % (out, os.path.getsize(out) / 1048576.0))
        print("原来那个大文件删掉再提交 —— git 会把它永远留在历史里。")

    if not args.write:
        print("\n看着对了,加 --write 并进 src/city.geo.json。")
        return 0

    city_doc = load_city(CITY_JSON)
    have = {(f["properties"].get("city"), f["properties"].get("name"))
            for f in city_doc["features"]}
    added, skipped = 0, 0
    for nm, ft in sorted(named, key=lambda x: x[0]):
        if not nm:
            skipped += 1
            continue
        short = DROP_SUFFIX.sub("", nm) or nm
        if (args.city, short) in have:
            skipped += 1
            continue
        city_doc["features"].append({
            "type": "Feature",
            "properties": {"name": short, "city": args.city},
            "geometry": _round_coords(ft["geometry"], args.nd),
        })
        have.add((args.city, short))
        added += 1
    with open(CITY_JSON, "w", encoding="utf-8") as f:
        json.dump(city_doc, f, ensure_ascii=False)
    print("\n并进 %s:新增 %d 个区,跳过 %d 个(已有或认不出名字)。"
          % (os.path.relpath(CITY_JSON, REPO), added, skipped))
    print("现共 %d 个区。出处那一行记得对上 —— 界线是从哪儿来的,得说得出。"
          % len(city_doc["features"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------- 落点核对

def _rings(geom):
    """一个 Polygon / MultiPolygon 的所有外环。孔洞不管 —— 区界没有孔。"""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"][0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []


def point_in_ring(lng, lat, ring):
    """射线法:从这一点往东引一条线,穿过边界的次数是奇数就在里头。"""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            xx = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lng < xx:
                inside = not inside
    return inside


def district_at(lng, lat, geo, city="北京"):
    """这个点落在哪个区里 —— 落不进任何一个就是 None(出了本市)。"""
    for f in geo.get("features", []):
        name = _pick_name(f.get("properties", {}), set(), city)
        if not name:
            continue
        if any(point_in_ring(lng, lat, r) for r in _rings(f.get("geometry", {}))):
            return name
    return None
