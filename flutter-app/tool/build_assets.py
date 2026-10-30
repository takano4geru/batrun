"""course-data/ から Flutter 用のコンパクトなアセット assets/course_data.json を作る。

使い方: python3 tool/build_assets.py <course-data ディレクトリ> assets/course_data.json
"""
import csv
import json
import math
import sys

src, out = sys.argv[1], sys.argv[2]
course = json.load(open(f"{src}/course_ring_inner.json"))
scenery = json.load(open(f"{src}/scenery_ring_inner.json"))
rows = list(csv.DictReader(open(f"{src}/course_ring_inner_centerline.csv")))

segs = course["segments"]
n = len(segs)
seg_len = course["segment_length_m"]
step = course["sample_step_m"]
per = int(round(seg_len / step))


def row_at(i):
    return rows[min(i * per, len(rows) - 1)]


CLASS = {
    "house": 0, "detached": 0, "residential": 0, "semidetached_house": 0,
    "apartments": 1, "dormitory": 1,
    "commercial": 2, "retail": 2, "office": 2, "hotel": 2,
    "warehouse": 3, "industrial": 3, "roof": 3, "garage": 3, "garages": 3,
    "public": 4, "school": 4, "government": 4, "hospital": 4, "university": 4,
}

buildings = []
for b in scenery["buildings"]:
    h = b["height"] or 8.0
    off = b["offset"]
    # 道路から遠い低い建物は見えないので間引く。高い建物は遠くても残す。
    if abs(off) > 170 and h < 30:
        continue
    if abs(off) < 9:
        continue
    seg = int(b["s"] // seg_len) % n
    buildings.append([
        seg, round(off, 1), round(h, 1),
        round(min(b["w"], 80), 1), round(min(b["d"], 60), 1),
        CLASS.get(b["class"], 5),
    ])
buildings.sort(key=lambda r: r[0])

named = []
for b in scenery["buildings"]:
    if b["name"] and (b["height"] or 0) >= 40:
        named.append({"s": b["s"], "name": b["name"], "height": b["height"],
                      "x": b["x"], "y": b["y"]})

data = {
    "name": course["name"],
    "length_m": course["length_m"],
    "segment_length_m": seg_len,
    "attribution": course["attribution"],
    "curve": [s["curve"] for s in segs],
    "z": [s["z"] for s in segs],
    "ground": [float(row_at(i)["ground_m"]) for i in range(n)],
    "heading": [float(row_at(i)["heading_deg"]) for i in range(n)],
    "level": [s["level"] for s in segs],
    "tunnel": [1 if s["tunnel"] else 0 for s in segs],
    "map": [[round(float(row_at(i)["x_m"])), round(float(row_at(i)["y_m"]))]
            for i in range(0, n, 5)],
    "landmarks": course["landmarks"],
    "named_buildings": named,
    "buildings": buildings,
}
json.dump(data, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print(f"segments={n} buildings={len(buildings)} named={len(named)}")
