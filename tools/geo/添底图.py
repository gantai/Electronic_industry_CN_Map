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

DROP_SUFFIX = re.compile(r"(区|县|市辖区|市)$")


def _texts(props):
    """这个 feature 的属性里,所有像名字的字符串。"""
    out = []
    for v in (props or {}).values():
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _pick_name(props, city_words):
    """挑一个当区名:优先带「区/县」的中文,其次最短的那个非市名字符串。"""
    cands = _texts(props)
    zh = [t for t in cands if re.search(r"[一-鿿]", t)]
    named = [t for t in zh if DROP_SUFFIX.search(t)]
    pool = named or zh or cands
    pool = [t for t in pool if t not in city_words] or pool
    return min(pool, key=len) if pool else ""


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


def find_city(doc, city):
    """挑出属于这个市的 feature。认值不认字段名。"""
    words = CITY_ALIASES.get(city, [city])
    hit = []
    for ft in doc.get("features", []):
        blob = " ".join(_texts(ft.get("properties")))
        if any(w in blob for w in words):
            hit.append(ft)
    return hit, words


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
    feats, words = find_city(doc, args.city)
    print("%s 里共 %d 个 feature,认出属于「%s」的 %d 个。"
          % (os.path.basename(args.src), len(doc.get("features", [])),
             args.city, len(feats)))
    if not feats:
        print("\n一个也没认出来。看一眼属性长什么样,再告诉我该按哪个字段找:")
        for ft in doc.get("features", [])[:3]:
            print("   %s" % json.dumps(ft.get("properties"), ensure_ascii=False)[:160])
        return 1

    named = [(_pick_name(ft.get("properties"), words), ft) for ft in feats]
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
