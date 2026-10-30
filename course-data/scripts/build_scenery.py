"""コース沿線の建物を抽出し、疑似3Dレースの風景データにする。

入力: fukuoka_bld.parquet (Overture buildings を福岡市周辺で切り出したもの), course_ring_inner_centerline.csv
出力: scenery_ring_inner.json (s/offset順の建物リスト), scenery_ring_inner.geojson (確認用)
"""
import json, math, sys
import numpy as np
import pyarrow.parquet as pq
from shapely import wkb, prepare
from shapely.geometry import LineString
from shapely.ops import transform

BLD, CL, OUT = sys.argv[1:4]
MAX_DIST = 300.0       # 中心線からの最大距離 [m]
FLOOR_H = 3.2          # 階数→高さ換算 [m/階]
DEFAULT_H = 8.0        # 高さ不明時の既定値 [m]
LAT0, LON0, R = 33.59, 130.40, 6378137.0
KX = R * math.cos(math.radians(LAT0)) * math.pi / 180
KY = R * math.pi / 180

cl = np.genfromtxt(CL, delimiter=",", names=True, dtype=None, encoding="utf-8")
xs, ys, ss, hd = cl["x_m"], cl["y_m"], cl["s_m"], np.radians(cl["heading_deg"])
total = float(json.load(open(f"{OUT}/course_ring_inner.json"))["length_m"])
line = LineString(np.c_[xs, ys].tolist() + [[xs[0], ys[0]]])
corridor = line.buffer(MAX_DIST)
prepare(corridor)

def local(g):
    return transform(lambda lon, lat, z=None: ((lon - LON0) * KX, (lat - LAT0) * KY), g)

t = pq.read_table(BLD).to_pylist()
out, feats = [], []
for r in t:
    if r.get("is_underground"):
        continue
    g = local(wkb.loads(r["geometry"]))
    if not g.is_valid:
        g = g.buffer(0)
    if not corridor.intersects(g):
        continue
    c = g.centroid
    s = line.project(c)
    i = int(np.searchsorted(ss, s) % len(ss))
    # 進行方向の右手を正とする横オフセット
    rx, ry = math.cos(hd[i]), -math.sin(hd[i])
    d_signed = (c.x - xs[i]) * rx + (c.y - ys[i]) * ry
    if abs(d_signed) > MAX_DIST:
        continue
    if r["height"] is not None:
        h, hsrc = float(r["height"]), "height"
    elif r["num_floors"]:
        h, hsrc = r["num_floors"] * FLOOR_H, "floors"
    else:
        h, hsrc = DEFAULT_H, "default"
    poly = g.simplify(0.5)
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda p: p.area)
    mrr = poly.minimum_rotated_rectangle
    cx = list(mrr.exterior.coords)[:3]
    e1 = math.dist(cx[0], cx[1]); e2 = math.dist(cx[1], cx[2])
    ds = [r2["dataset"] for r2 in r["sources"]]
    out.append({
        "s": round(s, 1), "offset": round(d_signed, 1),
        "x": round(c.x, 1), "y": round(c.y, 1),
        "height": round(h, 1), "height_src": hsrc,
        "floors": r["num_floors"],
        "w": round(max(e1, e2), 1), "d": round(min(e1, e2), 1),
        "area": round(g.area, 1),
        "class": r["class"], "roof": r["roof_shape"],
        "name": (r["names"] or {}).get("primary"),
        "footprint": [[round(a, 1), round(b, 1)] for a, b in poly.exterior.coords[:-1]],
        "source": ds[0] if ds else None,
        "id": r["id"],
    })

out.sort(key=lambda b: (b["s"], b["offset"]))
hs = np.array([b["height"] for b in out])
meta = {
    "course": "福岡都市高速 環状線 内回り",
    "course_length_m": total,
    "coordinate_system": {"type": "local_tangent_plane", "origin_lonlat": [LON0, LAT0], "x": "east [m]", "y": "north [m]"},
    "fields": {
        "s": "コース始点からの距離 [m] (course_ring_inner.json と同じ)",
        "offset": "中心線からの横距離 [m] 進行方向右が正",
        "x,y": "重心 (ローカル平面 [m])",
        "height": "建物高さ [m]", "height_src": "height=実データ / floors=階数×3.2m / default=不明のため8m",
        "w,d": "最小外接矩形の長辺/短辺 [m] (スプライト幅の目安)",
        "footprint": "簡略化した外形 (ローカル平面 [m])",
    },
    "max_distance_m": MAX_DIST,
    "stats": {
        "count": len(out),
        "height_known": int(sum(b["height_src"] == "height" for b in out)),
        "from_floors": int(sum(b["height_src"] == "floors" for b in out)),
        "default_height": int(sum(b["height_src"] == "default" for b in out)),
        "height_p50": round(float(np.median(hs)), 1), "height_p95": round(float(np.percentile(hs, 95)), 1),
        "height_max": round(float(hs.max()), 1),
        "tallest": sorted(({"name": b["name"], "height": b["height"], "s": b["s"]} for b in out if b["name"]), key=lambda b: -b["height"])[:10],
    },
    "attribution": "© OpenStreetMap contributors (ODbL 1.0) via Overture Maps Foundation; 一部 doi:10.5281/zenodo.8174931 (Overture buildings source)",
}
json.dump({**meta, "buildings": out}, open(f"{OUT}/scenery_ring_inner.json", "w"), ensure_ascii=False, separators=(",", ":"))

# 確認用 GeoJSON (経緯度, 外形, 高さ)
def ll(x, y):
    return [round(LON0 + x / KX, 7), round(LAT0 + y / KY, 7)]
gj = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {k: b[k] for k in ("s", "offset", "height", "height_src", "name", "class", "id")},
     "geometry": {"type": "Polygon", "coordinates": [[ll(*p) for p in b["footprint"] + b["footprint"][:1]]]}} for b in out]}
json.dump(gj, open(f"{OUT}/scenery_ring_inner.geojson", "w"), ensure_ascii=False, separators=(",", ":"))
print(json.dumps(meta["stats"], ensure_ascii=False))
