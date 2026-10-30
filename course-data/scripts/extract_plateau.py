"""PLATEAU 福岡市 3D都市モデル (CityGML) からコース沿線の建物を抽出する。

build_scenery.py (Overture 版) と同じ形式の風景データを作る。numpy と標準ライブラリだけで動く。

使い方:
  # 1) 沿線に必要な3次メッシュ番号を表示 (ダウンロード対象の確認用)
  python3 extract_plateau.py meshes course_ring_inner_centerline.csv
  # 2) 沿線の bldg GML だけ読んで抽出 (入力は udx/bldg ディレクトリ / CityGML zip / zip の URL)
  python3 extract_plateau.py extract course_ring_inner_centerline.csv <入力> scenery_ring_inner_plateau.json
  URL の場合は HTTP Range で沿線メッシュのファイルだけ読む (約1GBの zip 全体は落とさない)。
  プロキシ環境では SSL_CERT_FILE にCAバンドルを指定する。
  # 3) (任意) PLATEAU には建物名がほぼ無いので、OSM/Overture 版の建物名を重心が近い建物へ移す
  python3 extract_plateau.py names scenery_ring_inner_plateau.json scenery_ring_inner_osm.json

データ入手先: G空間情報センター「福岡市 3D都市モデル (Project PLATEAU)」2024年度 CityGML 版
  https://www.geospatial.jp/ckan/dataset/plateau-40130-fukuoka-shi-2024
  CityGML zip (v4): https://assets.cms.plateau.reearth.io/assets/c5/263250-3d72-486d-8b76-f8c62aaaca03/40130_fukuoka-shi_city_2024_citygml_2_op.zip
座標系: EPSG:6697 (JGD2011 緯度, 経度, 標高)
"""
import glob, io, json, math, os, sys, urllib.request, zipfile
import xml.etree.ElementTree as ET
import numpy as np

MAX_DIST = 300.0
FLOOR_H = 3.2
DEFAULT_H = 8.0
LAT0, LON0, R = 33.59, 130.40, 6378137.0
KX = R * math.cos(math.radians(LAT0)) * math.pi / 180
KY = R * math.pi / 180
GML = "http://www.opengis.net/gml"
BLDG = "http://www.opengis.net/citygml/building/2.0"
NS = {"gml": GML, "bldg": BLDG}

# PLATEAU bldg:usage コード -> OSM 風の class 名 (flutter-app/tool/build_assets.py の分類に合わせる)
USAGE_CLASS = {
    "401": "office", "402": "commercial", "403": "hotel", "404": "commercial",
    "411": "house", "412": "apartments", "413": "house", "414": "apartments", "415": "house",
    "421": "government", "422": "school", "431": "warehouse", "441": "industrial",
    "451": "warehouse", "452": "warehouse", "453": "industrial", "454": "government", "461": None,
}


def load_centerline(path):
    return np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding="utf-8")


def mesh3(lat, lon):
    """JIS X 0410 3次メッシュコード (約1km)"""
    p = int(lat * 1.5); a = lat * 1.5 - p
    u = int(lon - 100); f = lon - 100 - u
    q = int(a * 8); b = a * 8 - q
    v = int(f * 8); g = f * 8 - v
    r = int(b * 10); w = int(g * 10)
    return f"{p:02d}{u:02d}{q}{v}{r}{w}"


def corridor_meshes(cl):
    ms = set()
    for lat, lon in zip(cl["lat"], cl["lon"]):
        for dy in (-MAX_DIST, 0, MAX_DIST):
            for dx in (-MAX_DIST, 0, MAX_DIST):
                ms.add(mesh3(lat + dy / KY, lon + dx / KX))
    return sorted(ms)


# ---- 平面幾何 (shapely 無しで済ませる) ----

def ring_area_centroid(p):
    x, y = p[:, 0], p[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cr = x * y1 - x1 * y
    a = cr.sum() / 2
    if abs(a) < 1e-9:
        return 0.0, p.mean(axis=0)
    return abs(a), np.array([((x + x1) * cr).sum() / (6 * a), ((y + y1) * cr).sum() / (6 * a)])


def convex_hull(p):
    pts = sorted(set(map(tuple, p)))
    if len(pts) < 3:
        return np.array(pts)
    def half(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h
    lo, up = half(pts), half(pts[::-1])
    return np.array(lo[:-1] + up[:-1])


def min_rect_sides(p):
    """最小外接矩形 (回転可) の長辺・短辺"""
    h = convex_hull(p)
    if len(h) < 3:
        span = np.ptp(p, axis=0) if len(p) else np.zeros(2)
        return float(span.max()), float(span.min())
    e = np.roll(h, -1, axis=0) - h
    ang = np.arctan2(e[:, 1], e[:, 0])
    best = None
    for t in ang:
        c, s = math.cos(t), math.sin(t)
        u = h @ np.array([c, s]); v = h @ np.array([-s, c])
        w, d = np.ptp(u), np.ptp(v)
        if best is None or w * d < best[0]:
            best = (w * d, max(w, d), min(w, d))
    return float(best[1]), float(best[2])


def simplify(p, tol=0.5):
    """Douglas-Peucker (閉じていない頂点列)"""
    if len(p) <= 4:
        return p
    keep = np.zeros(len(p), bool); keep[0] = keep[-1] = True
    stack = [(0, len(p) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = p[i], p[j]; ab = b - a; L = np.hypot(*ab)
        seg = p[i + 1:j] - a
        d = np.abs(ab[0] * seg[:, 1] - ab[1] * seg[:, 0]) / L if L > 0 else np.hypot(seg[:, 0], seg[:, 1])
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k; keep[m] = True; stack += [(i, m), (m, j)]
    q = p[keep]
    return q if len(q) >= 4 else p


class Line:
    """閉じた中心線への射影 (コース距離 s と最短距離)"""
    def __init__(self, xs, ys):
        P = np.c_[np.r_[xs, xs[0]], np.r_[ys, ys[0]]]
        self.a = P[:-1]; self.d = P[1:] - P[:-1]
        self.L = np.hypot(self.d[:, 0], self.d[:, 1])
        self.s0 = np.r_[0, np.cumsum(self.L)[:-1]]
        self.L2 = np.maximum(self.L ** 2, 1e-9)

    def project(self, pts):
        """pts (N,2) -> (s, dist)"""
        S, D = np.empty(len(pts)), np.empty(len(pts))
        for k in range(0, len(pts), 256):
            q = pts[k:k + 256, None, :]
            t = np.clip(((q - self.a) * self.d).sum(-1) / self.L2, 0, 1)
            near = self.a + t[..., None] * self.d
            dd = np.hypot(*(q - near).transpose(2, 0, 1))
            j = dd.argmin(1); r = np.arange(len(j))
            S[k:k + 256] = self.s0[j] + t[r, j] * self.L[j]
            D[k:k + 256] = dd[r, j]
        return S, D


# ---- CityGML 読み込み ----

class HttpFile(io.RawIOBase):
    """HTTP Range で読む seekable ファイル。zipfile に渡して必要なメンバーだけ取得する。"""
    def __init__(self, url, block=1 << 22):
        self.url, self.block, self.pos, self.cache, self.fetched = url, block, 0, {}, 0
        self.size = int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60).headers["Content-Length"])
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos
    def _blk(self, i):
        if i not in self.cache:
            if len(self.cache) > 32:
                self.cache.clear()
            a = i * self.block; b = min(a + self.block, self.size) - 1
            for t in range(5):
                try:
                    req = urllib.request.Request(self.url, headers={"Range": f"bytes={a}-{b}"})
                    self.cache[i] = urllib.request.urlopen(req, timeout=180).read(); break
                except Exception:
                    if t == 4:
                        raise
            self.fetched += len(self.cache[i])
        return self.cache[i]
    def read(self, n=-1):
        n = self.size - self.pos if n is None or n < 0 else min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            i, o = divmod(self.pos, self.block)
            d = self._blk(i)[o:o + n]; out += d; self.pos += len(d); n -= len(d)
        return bytes(out)
    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)


def open_sources(src, meshes):
    """ディレクトリ / ローカルzip / zipのURL から、対象メッシュの bldg GML を順に開く"""
    if os.path.isdir(src):
        for f in sorted(glob.glob(os.path.join(src, "**", "*.gml"), recursive=True)):
            if os.path.basename(f)[:8] in meshes:
                yield f, open(f, "rb")
        return
    fh = HttpFile(src) if src.startswith("http") else open(src, "rb")
    z = zipfile.ZipFile(fh)
    names = [n for n in z.namelist() if "/bldg/" in n and n.endswith(".gml") and os.path.basename(n)[:8] in meshes]
    for k, name in enumerate(sorted(names)):
        print(f"[{k + 1}/{len(names)}] {name}", file=sys.stderr, flush=True)
        yield name, io.BytesIO(z.read(name))


def footprint(bld):
    """lod0 の外形があれば使い、無ければ lod1Solid の最も低い面を外形とする。(外形[N,2] ローカルm, 地盤高)"""
    cand = []
    for tag in ("bldg:lod0FootPrint", "bldg:lod0RoofEdge", "bldg:lod1Solid"):
        for pl in bld.iterfind(f".//{tag}//gml:posList", NS):
            cand.append(np.array(pl.text.split(), float).reshape(-1, 3))
        if cand and tag != "bldg:lod1Solid":
            break
    if not cand:
        return None, None
    # lod1Solid は側面も含むので、水平な面のうち最も低いものを底面とする
    flat = [v for v in cand if np.ptp(v[:, 2]) < 0.01] or cand
    v = min(flat, key=lambda v: v[:, 2].mean())
    xy = np.c_[(v[:, 1] - LON0) * KX, (v[:, 0] - LAT0) * KY]
    if len(xy) > 1 and np.allclose(xy[0], xy[-1]):
        xy = xy[:-1]
    return xy, float(v[:, 2].min())


def num(el, path):
    e = el.find(path, NS)
    try:
        return float(e.text) if e is not None and e.text else None
    except ValueError:
        return None


def extract(cl, src, out_path):
    xs, ys, ss, hd = cl["x_m"], cl["y_m"], cl["s_m"], np.radians(cl["heading_deg"])
    line = Line(xs, ys)
    meshes = set(corridor_meshes(cl))
    raw, files = [], []
    for fn, fobj in open_sources(src, meshes):
        files.append(fn)
        for _, el in ET.iterparse(fobj, events=("end",)):
            if el.tag != f"{{{BLDG}}}Building":
                continue
            xy, base_z = footprint(el)
            if xy is not None and len(xy) >= 3:
                usage = el.find("bldg:usage", NS)
                gname = el.find("gml:name", NS)
                raw.append((xy, base_z, num(el, "bldg:measuredHeight"), num(el, "bldg:storeysAboveGround"),
                            usage.text if usage is not None else None,
                            gname.text if gname is not None else None,
                            el.get(f"{{{GML}}}id")))
            el.clear()
    print(f"buildings in meshes: {len(raw)}", file=sys.stderr)

    # 重心の距離で粗く絞り、外形の頂点も見て中心線から MAX_DIST 以内のものを残す
    cents = np.array([ring_area_centroid(r[0])[1] for r in raw])
    radius = np.array([np.hypot(*(r[0] - c).T).max() for r, c in zip(raw, cents)])
    s_all, d_all = line.project(cents)
    out = []
    for k in np.nonzero(d_all - radius <= MAX_DIST)[0]:
        xy, base_z, h, storeys, usage, gname, gid = raw[k]
        if d_all[k] > MAX_DIST and line.project(xy)[1].min() > MAX_DIST:
            continue
        area, c = ring_area_centroid(xy)
        s = float(s_all[k])
        i = int(np.searchsorted(ss, s) % len(ss))
        off = (c[0] - xs[i]) * math.cos(hd[i]) - (c[1] - ys[i]) * math.sin(hd[i])
        if abs(off) > MAX_DIST:
            continue
        w, d = min_rect_sides(xy)
        p2 = simplify(np.vstack([xy, xy[:1]]))[:-1]
        if h and h > 0:
            height, hsrc = h, "measuredHeight"
        elif storeys:
            height, hsrc = storeys * FLOOR_H, "floors"
        else:
            height, hsrc = DEFAULT_H, "default"
        out.append({
            "s": round(s, 1), "offset": round(off, 1), "x": round(float(c[0]), 1), "y": round(float(c[1]), 1),
            "height": round(height, 1), "height_src": hsrc,
            "floors": int(storeys) if storeys else None,
            "ground_z": round(base_z, 1) if base_z is not None else None,
            "w": round(w, 1), "d": round(d, 1), "area": round(area, 1),
            "usage_code": usage, "class": USAGE_CLASS.get(usage) if usage else None,
            "roof": None, "name": gname,
            "footprint": [[round(float(a), 1), round(float(b), 1)] for a, b in p2],
            "source": "PLATEAU", "id": gid,
        })
    out.sort(key=lambda b: (b["s"], b["offset"]))
    hs = np.array([b["height"] for b in out])
    meta = {
        "course": "福岡都市高速 環状線 内回り",
        "coordinate_system": {"type": "local_tangent_plane", "origin_lonlat": [LON0, LAT0], "x": "east [m]", "y": "north [m]"},
        "fields": {
            "s": "コース始点からの距離 [m] (course_ring_inner.json と同じ)",
            "offset": "中心線からの横距離 [m] 進行方向右が正",
            "x,y": "重心 (ローカル平面 [m])",
            "height": "建物高さ [m]", "height_src": "measuredHeight=PLATEAU計測高さ / floors=階数×3.2m / default=不明のため8m",
            "ground_z": "建物の地盤高 [m] (PLATEAU LOD1 底面)",
            "w,d": "最小外接矩形の長辺/短辺 [m] (スプライト幅の目安)",
            "usage_code": "PLATEAU bldg:usage コード", "class": "usage_code を OSM 風の分類名に変換したもの",
            "footprint": "簡略化した外形 (ローカル平面 [m])",
        },
        "max_distance_m": MAX_DIST,
        "source": "PLATEAU 福岡市 2024年度 (v4) CityGML",
        "files_read": len(files),
        "stats": {
            "count": len(out),
            "height_known": int(sum(b["height_src"] == "measuredHeight" for b in out)),
            "from_floors": int(sum(b["height_src"] == "floors" for b in out)),
            "default_height": int(sum(b["height_src"] == "default" for b in out)),
            "height_p50": round(float(np.median(hs)), 1), "height_p95": round(float(np.percentile(hs, 95)), 1),
            "height_max": round(float(hs.max()), 1),
            "tallest": sorted(({"name": b["name"], "height": b["height"], "s": b["s"]} for b in out if b["name"]), key=lambda b: -b["height"])[:10],
        },
        "attribution": "出典: 国土交通省 Project PLATEAU 福岡市3D都市モデル (2024年度) を加工して作成",
    }
    json.dump({**meta, "buildings": out}, open(out_path, "w"), ensure_ascii=False, separators=(",", ":"))

    def ll(x, y):
        return [round(LON0 + x / KX, 7), round(LAT0 + y / KY, 7)]
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {k: b[k] for k in ("s", "offset", "height", "height_src", "name", "class", "usage_code", "id")},
         "geometry": {"type": "Polygon", "coordinates": [[ll(*p) for p in b["footprint"] + b["footprint"][:1]]]}} for b in out]}
    json.dump(gj, open(os.path.splitext(out_path)[0] + ".geojson", "w"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(meta["stats"], ensure_ascii=False))


def copy_names(plateau_path, osm_path, max_d=25.0):
    """OSM 版の名前付き建物を、重心が max_d m 以内で最も近い PLATEAU 建物へ移す (名前は ODbL 由来)"""
    d = json.load(open(plateau_path)); b = d["buildings"]
    xy = np.array([[x["x"], x["y"]] for x in b])
    n = 0
    for o in json.load(open(osm_path))["buildings"]:
        if not o["name"]:
            continue
        dist = np.hypot(xy[:, 0] - o["x"], xy[:, 1] - o["y"])
        k = int(dist.argmin())
        if dist[k] <= max_d and not b[k]["name"]:
            b[k]["name"] = o["name"]; b[k]["name_src"] = "OSM"; n += 1
    d["stats"]["named_from_osm"] = n
    d["stats"]["tallest"] = sorted(({"name": x["name"], "height": x["height"], "s": x["s"]} for x in b if x["name"]), key=lambda x: -x["height"])[:10]
    json.dump(d, open(plateau_path, "w"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({"named_from_osm": n, "tallest": d["stats"]["tallest"][:5]}, ensure_ascii=False))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "names":
        copy_names(sys.argv[2], sys.argv[3]); sys.exit()
    cl = load_centerline(sys.argv[2])
    if cmd == "meshes":
        print("\n".join(corridor_meshes(cl)))
    elif cmd == "extract":
        extract(cl, sys.argv[3], sys.argv[4])
