"""福岡都市高速 環状線(内回り) の周回コースを Overture Maps (OSM由来) の道路セグメントから生成する。

入力: fukuoka_roads.parquet (Overture transportation/segment を福岡市周辺で切り出したもの)
出力: course_ring_inner.json, course_ring_inner_centerline.csv, landmarks
"""
import io, json, math, sys, subprocess
import numpy as np
import pyarrow.parquet as pq
from shapely import wkb
from PIL import Image

ROADS, OUT = sys.argv[1], sys.argv[2]
ROUTE = "福岡都市高速環状線内回り"
STEP = 5.0           # 中心線のサンプル間隔 [m]
SEG_LEN = 10.0       # 疑似3D用セグメント長 [m]
LAT0, LON0 = 33.59, 130.40  # ローカル平面の原点
R = 6378137.0

def to_xy(lon, lat):
    x = math.radians(lon - LON0) * R * math.cos(math.radians(LAT0))
    y = math.radians(lat - LAT0) * R
    return x, y

def to_ll(x, y):
    return (LON0 + math.degrees(x / (R * math.cos(math.radians(LAT0)))), LAT0 + math.degrees(y / R))

rows = pq.read_table(ROADS).to_pylist()
segs = [r for r in rows if any(ROUTE == (rt["name"] or "") for rt in (r["routes"] or []))]

# --- コネクタをたどって閉路に並べる -------------------------------------------
def endpoints(r):
    cs = sorted(r["connectors"], key=lambda c: c["at"])
    return cs[0]["connector_id"], cs[-1]["connector_id"]
by_start = {endpoints(r)[0]: r for r in segs}
order, cur = [], segs[0]
while True:
    order.append(cur)
    nxt = by_start.get(endpoints(cur)[1])
    if nxt is None or nxt is order[0]:
        closed = nxt is order[0]
        break
    cur = nxt
assert closed and len(order) == len(segs), (len(order), len(segs), closed)

# --- 各点に属性(高架レベル, トンネル, 道路名, 出典ID)を付けて連結 ----------------
def rule_at(rules, frac, key="value"):
    v = None
    for ru in rules or []:
        b = ru.get("between")
        if b is None or b[0] <= frac <= b[1]:
            v = ru[key] if key else ru
    return v

pts = []  # (x, y, level, tunnel, name, osm_way)
for r in order:
    g = wkb.loads(r["geometry"])
    xy = [to_xy(*c) for c in g.coords]
    d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.array(xy).T)))])
    L = d[-1]
    way = next((s["record_id"] for s in r["sources"] if s["property"] == ""), None)
    name = (r["names"] or {}).get("primary")
    for i, (p, di) in enumerate(zip(xy, d)):
        if pts and i == 0:
            continue
        f = di / L
        lvl = rule_at(r["level_rules"], f) or 0
        tunnel = any("is_tunnel" in fl["values"] and (fl["between"] is None or fl["between"][0] <= f <= fl["between"][1])
                     for fl in (r["road_flags"] or []))
        pts.append((p[0], p[1], lvl, tunnel, name, way))
if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.5:
    pts.pop()

P = np.array([[p[0], p[1]] for p in pts])
seglen = np.hypot(*np.diff(np.vstack([P, P[:1]]), axis=0).T)
cum = np.concatenate([[0], np.cumsum(seglen)])
total = cum[-1]

# --- 等間隔リサンプリング(閉路) -------------------------------------------------
n = int(round(total / STEP))
s = np.linspace(0, total, n, endpoint=False)
Pc = np.vstack([P, P[:1]])
x = np.interp(s, cum, Pc[:, 0]); y = np.interp(s, cum, Pc[:, 1])
src_idx = np.searchsorted(cum, s, side="right") - 1
src_idx = np.clip(src_idx, 0, len(pts) - 1)

def circ_smooth(a, w):
    k = np.ones(w) / w
    return np.convolve(np.concatenate([a[-w:], a, a[:w]]), k, mode="same")[w:-w]

# 角の折れを均す(約25m窓)
xs, ys = circ_smooth(x, 5), circ_smooth(y, 5)

# --- 方位と曲率 --------------------------------------------------------------
dx = np.roll(xs, -1) - np.roll(xs, 1); dy = np.roll(ys, -1) - np.roll(ys, 1)
heading = np.arctan2(dx, dy)  # 北=0, 東=+π/2 (時計回り)
dh = np.angle(np.exp(1j * (np.roll(heading, -1) - heading)))
ds = np.hypot(np.roll(xs, -1) - xs, np.roll(ys, -1) - ys)
curv = circ_smooth(dh / ds, 9)  # [rad/m] 正=右カーブ
turn_total = math.degrees(dh.sum())

# --- 地盤標高 (AWS Terrain Tiles, terrarium z14) ------------------------------
Z = 14
def tile_of(lon, lat):
    n2 = 2 ** Z
    tx = (lon + 180) / 360 * n2
    ty = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n2
    return tx, ty
tiles = {}
def ground(lon, lat):
    tx, ty = tile_of(lon, lat)
    k = (int(tx), int(ty))
    if k not in tiles:
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{k[0]}/{k[1]}.png"
        for attempt in range(5):
            raw = subprocess.run(["curl", "-sS", "-m", "60", url], capture_output=True).stdout
            if raw[:4] == b"\x89PNG":
                break
        else:
            raise RuntimeError(f"tile fetch failed: {url}")
        im = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB")).astype(float)
        tiles[k] = im[..., 0] * 256 + im[..., 1] + im[..., 2] / 256 - 32768
    px = min(255, int((tx - k[0]) * 256)); py = min(255, int((ty - k[1]) * 256))
    return float(tiles[k][py, px])

lonlat = [to_ll(a, b) for a, b in zip(xs, ys)]
gnd = np.array([ground(lo, la) for lo, la in lonlat])
# 地表モデルの細かいノイズ(建物・高架構造物の映り込み)を中央値フィルタ(約400m)で除去
w = 81
pad = np.concatenate([gnd[-w:], gnd, gnd[:w]])
gnd = np.array([np.median(pad[i:i + w]) for i in range(w // 2, w // 2 + len(gnd) + w)])[w - w // 2:w - w // 2 + len(gnd)]
gnd = np.maximum(circ_smooth(gnd, 41), 0)  # 海上は0m

# 高架・トンネルの推定オフセット (OSM layer -> 路面の地上高)
LEVEL_OFFSET = {-2: -15.0, -1: -8.0, 0: 0.0, 1: 7.0, 2: 12.0, 3: 17.0, 4: 22.0, 5: 27.0}
lvl = np.array([pts[i][2] for i in src_idx]); tun = np.array([pts[i][3] for i in src_idx])
off = np.array([LEVEL_OFFSET.get(int(l), 17.0) for l in lvl])
off[tun] = np.minimum(off[tun], -8.0)
z = gnd + off
z = circ_smooth(circ_smooth(z, 41), 41)  # 約200m窓×2で縦断を滑らかに
MAX_GRADE = 0.06  # 都市高速の設計上限程度に勾配を抑える
for _ in range(5000):
    grade = (np.roll(z, -1) - z) / ds
    bad = np.abs(grade) > MAX_GRADE
    if not bad.any():
        break
    m = bad | np.roll(bad, 1) | np.roll(bad, -1)
    zl = (np.roll(z, 1) + np.roll(z, -1)) / 2
    z = np.where(m, 0.5 * z + 0.5 * zl, z)
grade = (np.roll(z, -1) - z) / ds

# --- ランドマーク(ランプ/JCT名) ----------------------------------------------
from shapely.geometry import LineString, Point
line = LineString(np.c_[xs, ys].tolist() + [[xs[0], ys[0]]])
marks = []
for r in rows:
    nm = (r["names"] or {}).get("primary") or ""
    if r["class"] not in ("motorway", "motorway_link") or not any(k in nm for k in ("ランプ", "IC", "ＩＣ", "JCT", "入口", "出口")):
        continue
    if any(ROUTE == (rt["name"] or "") for rt in (r["routes"] or [])):
        continue
    g = wkb.loads(r["geometry"])
    best = None
    for c in (g.coords[0], g.coords[-1]):
        p = Point(to_xy(*c))
        dist = line.distance(p)
        if dist < 20 and (best is None or dist < best[1]):
            best = (line.project(p), dist)
    if best:
        kind = "entrance" if "入" in nm else ("exit" if "出" in nm else "ramp")
        marks.append({"s": round(best[0], 1), "name": nm, "kind": kind})
import re
def base(nm):
    return re.sub(r"(ランプ)?(上り|下り)?(入り?口|出口)$", "", nm).replace("ランプ", "")
marks.sort(key=lambda m: m["s"])
dedup = []
for m in marks:
    b = base(m["name"])
    hit = next((d for d in dedup if d["name"] == b and abs(m["s"] - d["s_last"]) < 1500), None)
    if hit:
        hit["kinds"].add(m["kind"]); hit["s_last"] = m["s"]
    else:
        dedup.append({"s": m["s"], "s_last": m["s"], "name": b, "kinds": {m["kind"]}})
dedup = [{"s": d["s"], "name": d["name"] + ("IC" if "IC" in d["name"] or "ＩＣ" in d["name"] else "ランプ").replace("ICIC", "IC"),
          "has": sorted(d["kinds"] - {"ramp"}) or ["entrance", "exit"]} for d in dedup]

# --- 出力 --------------------------------------------------------------------
segments = []
k = int(round(SEG_LEN / STEP))
for i in range(0, n, k):
    j = slice(i, i + k)
    segments.append({
        "s": round(float(s[i]), 1),
        "curve": round(float(dh[j].sum()), 5),          # このセグメントで向きが変わる量 [rad] 正=右
        "z": round(float(z[i]), 2),                     # 路面標高 [m]
        "level": int(lvl[i]),
        "tunnel": bool(tun[i]),
    })

course = {
    "name": "福岡都市高速 環状線 内回り",
    "direction": "clockwise" if turn_total > 0 else "counterclockwise",
    "length_m": round(float(total), 1),
    "coordinate_system": {"type": "local_tangent_plane", "origin_lonlat": [LON0, LAT0], "x": "east [m]", "y": "north [m]", "z": "elevation [m] (estimated)"},
    "sample_step_m": STEP,
    "segment_length_m": SEG_LEN,
    "elevation_note": "地盤標高(AWS Terrain Tiles z14)+OSM layerからの推定高架高さ。実測値ではない。",
    "level_offset_m": LEVEL_OFFSET,
    "stats": {
        "total_turn_deg": round(turn_total, 1),
        "z_min": round(float(z.min()), 1), "z_max": round(float(z.max()), 1),
        "max_grade_pct": round(float(np.abs(grade).max() * 100), 2),
        "tightest_radius_m": round(float(1 / np.abs(curv).max()), 1),
        "tunnel_length_m": round(float(tun.sum() * STEP), 1),
    },
    "landmarks": dedup,
    "segments": segments,
    "source_osm_ways": [next((sr["record_id"] for sr in r["sources"] if sr["property"] == ""), None) for r in order],
    "attribution": "© OpenStreetMap contributors (ODbL 1.0) via Overture Maps Foundation; elevation: AWS Terrain Tiles (Mapzen)",
}
json.dump(course, open(f"{OUT}/course_ring_inner.json", "w"), ensure_ascii=False, indent=1)

with open(f"{OUT}/course_ring_inner_centerline.csv", "w") as f:
    f.write("s_m,x_m,y_m,z_m,lon,lat,heading_deg,curvature_per_m,grade,ground_m,level,tunnel,road_name\n")
    for i in range(n):
        lo, la = lonlat[i]
        f.write(f"{s[i]:.1f},{xs[i]:.2f},{ys[i]:.2f},{z[i]:.2f},{lo:.7f},{la:.7f},{math.degrees(heading[i]) % 360:.2f},"
                f"{curv[i]:.6f},{grade[i]:.4f},{gnd[i]:.1f},{int(lvl[i])},{int(tun[i])},{pts[src_idx[i]][4] or ''}\n")

print(json.dumps(course["stats"], ensure_ascii=False), course["length_m"], course["direction"], len(dedup), "landmarks")
