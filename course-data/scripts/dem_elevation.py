"""コースの地盤標高を 国土地理院 標高タイル (標準) か PLATEAU 地形モデル (DEM, TIN) で作り直す。numpy と標準ライブラリ (+Pillow) で動く。

使い方:
  # 1) PLATEAU 福岡市 CityGML zip の udx/dem から、中心線 40m 以内の TIN 頂点を抜き出す (約230MB を Range 取得)
  SSL_CERT_FILE=<CAバンドル> python3 dem_elevation.py extract course_ring_inner_centerline.csv <zip の URL かパス> dem_points_ring_inner.npy
  # 1') または 国土地理院 標高タイル (DEM5A → DEM5B → DEM5C → DEM10B) から抜き出す (こちらが標準)
  python3 dem_elevation.py extract-gsi course_ring_inner_centerline.csv dem_points_gsi_ring_inner.npy
  # 2) 地盤高を DEM に置き換え、路面高を再計算して CSV と course JSON を上書きする
  python3 dem_elevation.py apply <course-data ディレクトリ> dem_points_gsi_ring_inner.npy gsi
  python3 dem_elevation.py apply <course-data ディレクトリ> dem_points_ring_inner.npy plateau

地盤高: DEM の点 (国土地理院タイルの画素 / PLATEAU TIN の頂点) を、
        中心線の各点 (5m 間隔) でガウス重み (σ=6m, 半径20m) の平均。高架の下の地面の高さになる。
路面高: 地盤高 + 高架の推定地上高 (OSM layer から)。トンネルは両坑口の地盤高を直線で結び、坑口の前後 300m で高架の高さへすり付ける。
"""
import csv, io, json, math, os, re, sys, zipfile
import numpy as np

LAT0, LON0, R = 33.59, 130.40, 6378137.0
KX = R * math.cos(math.radians(LAT0)) * math.pi / 180
KY = R * math.pi / 180
KEEP = 40.0       # 抜き出す範囲 [m]
CELL = 50.0

# OSM layer -> 路面の地上高 [m] (推定)。この路線は OSM でほぼ全線 layer=3 なので 3 を標準高架とする。
LEVEL_OFFSET = {0: 0.0, 1: 6.0, 2: 9.0, 3: 12.0, 4: 18.0, 5: 24.0}
PORTAL_RAMP = 300.0
MAX_GRADE = 0.06


def centerline_xy(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    x = np.array([(float(r["lon"]) - LON0) * KX for r in rows])
    y = np.array([(float(r["lat"]) - LAT0) * KY for r in rows])
    return rows, x, y


def extract(cl_path, src, out):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from extract_plateau import HttpFile
    rows, cx, cy = centerline_xy(cl_path)
    cells = {(int(math.floor(a / CELL)) + i, int(math.floor(b / CELL)) + j)
             for a, b in zip(cx, cy) for i in (-1, 0, 1) for j in (-1, 0, 1)}
    keys = np.array(sorted(i * 100000 + j for i, j in cells))
    lat = [float(r["lat"]) for r in rows]; lon = [float(r["lon"]) for r in rows]
    pad = 0.002
    bb = (min(lat) - pad, min(lon) - pad, max(lat) + pad, max(lon) + pad)
    z = zipfile.ZipFile(HttpFile(src) if src.startswith("http") else open(src, "rb"))
    pat = re.compile(rb"<gml:posList>([^<]*)</gml:posList>")
    res = []
    for name in sorted(n for n in z.namelist() if "/dem/" in n and n.endswith(".gml")):
        with z.open(name) as f:
            head = f.read(5000).decode("utf-8", "replace")
        lo = re.search(r"lowerCorner>([^<]+)", head).group(1).split()
        up = re.search(r"upperCorner>([^<]+)", head).group(1).split()
        if float(lo[0]) > bb[2] or float(up[0]) < bb[0] or float(lo[1]) > bb[3] or float(up[1]) < bb[1]:
            continue
        print(name, file=sys.stderr, flush=True)
        buf = b""
        with z.open(name) as f:
            while True:
                chunk = f.read(1 << 24)
                if not chunk:
                    break
                buf += chunk
                cut = buf.rfind(b"</gml:posList>")
                if cut < 0:
                    continue
                cut += len(b"</gml:posList>")
                parts = pat.findall(buf, 0, cut); buf = buf[cut:]
                if not parts:
                    continue
                a = np.array(b" ".join(parts).split(), dtype=np.float64).reshape(-1, 3)
                x = (a[:, 1] - LON0) * KX; y = (a[:, 0] - LAT0) * KY
                k = np.floor(x / CELL).astype(np.int64) * 100000 + np.floor(y / CELL).astype(np.int64)
                m = np.isin(k, keys)
                if m.any():
                    res.append(np.unique(np.c_[x[m], y[m], a[m, 2]].round(2), axis=0))
    P = np.unique(np.vstack(res), axis=0)
    keep = np.zeros(len(P), bool)
    for s in range(0, len(cx), 200):
        keep |= np.min(np.hypot(P[:, 0, None] - cx[None, s:s + 200], P[:, 1, None] - cy[None, s:s + 200]), axis=1) < KEEP
    P = P[keep]
    np.save(out, P)
    print(f"{len(P)} DEM vertices -> {out}")


GSI_LAYERS = ["dem5a_png", "dem5b_png", "dem5c_png", "dem_png"]  # 優先順 (5mレーザ → 5m写真 → 10m)


def extract_gsi(cl_path, out, z=15):
    """国土地理院 標高タイル (PNG) から中心線 KEEP m 以内の画素を (x, y, 標高) で抜き出す。
    DEM5A (航空レーザ) が無い画素は DEM5B → DEM5C → DEM10B の順に埋める。z=14 の dem_png は z15 画素に拡大して使う。"""
    import urllib.request
    from PIL import Image
    rows, cx, cy = centerline_xy(cl_path)
    lat = np.array([float(r["lat"]) for r in rows]); lon = np.array([float(r["lon"]) for r in rows])
    N = 2 ** z * 256
    px = (lon + 180) / 360 * N
    py = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * N
    mpp = 2 * math.pi * R * math.cos(math.radians(LAT0)) / N  # 1画素の大きさ [m]
    r = int(KEEP / mpp) + 2
    tiles = sorted({(int(x // 256) + i, int(y // 256) + j) for x, y in zip(px[::4], py[::4])
                    for i in (-1, 0, 1) for j in (-1, 0, 1)})

    def fetch(layer, tz, tx, ty):
        url = f"https://cyberjapandata.gsi.go.jp/xyz/{layer}/{tz}/{tx}/{ty}.png"
        for t in range(5):
            try:
                raw = urllib.request.urlopen(url, timeout=60).read(); break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if t == 4:
                    raise
            except Exception:
                if t == 4:
                    raise
        a = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB")).astype(np.int64)
        v = a[..., 0] * 65536 + a[..., 1] * 256 + a[..., 2]
        h = np.where(v < 2 ** 23, v, v - 2 ** 24) * 0.01
        h[v == 2 ** 23] = np.nan  # データ無し
        return h

    out_pts = []
    for tx, ty in tiles:
        # このタイルに中心線の近くが入るか
        gx = np.arange(256) + tx * 256 + 0.5; gy = np.arange(256) + ty * 256 + 0.5
        near = (px > gx[0] - r) & (px < gx[-1] + r) & (py > gy[0] - r) & (py < gy[-1] + r)
        if not near.any():
            continue
        H = np.full((256, 256), np.nan); S = np.full((256, 256), -1)
        for li, layer in enumerate(GSI_LAYERS):
            if not np.isnan(H).any():
                break
            if layer == "dem_png":
                h = fetch(layer, z - 1, tx // 2, ty // 2)
                if h is not None:
                    h = h[(ty % 2) * 128:(ty % 2) * 128 + 128, (tx % 2) * 128:(tx % 2) * 128 + 128].repeat(2, 0).repeat(2, 1)
            else:
                h = fetch(layer, z, tx, ty)
            if h is None:
                continue
            m = np.isnan(H) & ~np.isnan(h)
            H[m] = h[m]; S[m] = li
        X, Y = np.meshgrid(gx, gy)
        lon_g = X / N * 360 - 180
        lat_g = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * Y / N))))
        x = (lon_g - LON0) * KX; y = (lat_g - LAT0) * KY
        ok = ~np.isnan(H)
        T = np.c_[x[ok], y[ok], H[ok], S[ok]]
        keep = np.zeros(len(T), bool)
        ncx, ncy = cx[near], cy[near]
        for s0 in range(0, len(ncx), 64):
            keep |= np.min(np.hypot(T[:, 0, None] - ncx[None, s0:s0 + 64], T[:, 1, None] - ncy[None, s0:s0 + 64]), axis=1) < KEEP
        out_pts.append(T[keep])
        print(f"tile {z}/{tx}/{ty}", file=sys.stderr, flush=True)
    P = np.vstack(out_pts)
    for li, layer in enumerate(GSI_LAYERS):
        print(f"{layer}: {(P[:, 3] == li).sum()} px", file=sys.stderr)
    np.save(out, P[:, :3])
    print(f"{len(P)} GSI DEM pixels -> {out}")


def circ_smooth(a, w):
    k = np.ones(w) / w
    return np.convolve(np.concatenate([a[-w:], a, a[:w]]), k, mode="same")[w:-w]


def corridor_level(P, cx, cy, radius=KEEP, q=75):
    """中心線から radius m 以内の DEM 点の q パーセンタイル。川・水路の上を通る区間でも周りの地面の高さを拾う"""
    idx = {}
    C = 40.0
    for i, (x, y) in enumerate(P[:, :2]):
        idx.setdefault((int(x // C), int(y // C)), []).append(i)
    out = np.full(len(cx), np.nan)
    for k in range(len(cx)):
        i0, j0 = int(cx[k] // C), int(cy[k] // C)
        cand = [i for di in (-1, 0, 1) for dj in (-1, 0, 1) for i in idx.get((i0 + di, j0 + dj), [])]
        if cand:
            Q = P[cand]; m = np.hypot(Q[:, 0] - cx[k], Q[:, 1] - cy[k]) < radius
            if m.any():
                out[k] = np.percentile(Q[m, 2], q)
    if np.isnan(out).any():
        ok = ~np.isnan(out); n = np.arange(len(out))
        out[~ok] = np.interp(n[~ok], n[ok], out[ok], period=len(out))
    return np.maximum(out, 0.0)


def sample_ground(P, cx, cy):
    idx = {}
    C = 20.0
    for i, (x, y) in enumerate(P[:, :2]):
        idx.setdefault((int(x // C), int(y // C)), []).append(i)
    g = np.full(len(cx), np.nan)
    for k in range(len(cx)):
        i0, j0 = int(cx[k] // C), int(cy[k] // C)
        cand = [i for di in (-1, 0, 1) for dj in (-1, 0, 1) for i in idx.get((i0 + di, j0 + dj), [])]
        if not cand:
            continue
        Q = P[cand]; d = np.hypot(Q[:, 0] - cx[k], Q[:, 1] - cy[k]); m = d < 20
        if m.any():
            w = np.exp(-(d[m] / 6) ** 2) + 1e-9
            g[k] = (w * Q[m, 2]).sum() / w.sum()
    if np.isnan(g).any():  # データ無し (海上など) は前後から補間
        ok = ~np.isnan(g); n = np.arange(len(g))
        g[~ok] = np.interp(n[~ok], n[ok], g[ok], period=len(g))
    return g


def runs(mask):
    """閉路上で True が続く区間 [(start, end)] (end は含む)"""
    n = len(mask); out = []
    if mask.all():
        return [(0, n - 1)]
    s0 = int(np.argmin(mask))  # False から走査を始める
    i = 0
    while i < n:
        j = (s0 + i) % n
        if mask[j]:
            a = j; L = 0
            while i < n and mask[(s0 + i) % n]:
                i += 1; L += 1
            out.append((a, (a + L - 1) % n))
        else:
            i += 1
    return out


def apply(D, pts_path, source="gsi"):
    cl_path = f"{D}/course_ring_inner_centerline.csv"
    rows, cx, cy = centerline_xy(cl_path)
    n = len(rows)
    P = np.load(pts_path)
    gnd = sample_ground(P, cx, cy)
    gnd = np.maximum(circ_smooth(gnd, 3), 0.0)  # 約15m窓。海面下は0m
    lvl = np.array([int(r["level"]) for r in rows]); tun = np.array([r["tunnel"] == "1" for r in rows])
    ds = np.hypot(np.roll(cx, -1) - cx, np.roll(cy, -1) - cy)

    # 橋脚の足元の凹凸 (川・水路・法面) は路面に響かせない:
    # 中心線 ±40m の地面の 75% 点を、約200m の移動中央値でならしたものを高架の基準面にする
    lev = corridor_level(P, cx, cy)
    w = 41
    pad = np.concatenate([lev[-w:], lev, lev[:w]])
    base = np.array([np.median(pad[i - w // 2:i + w // 2 + 1]) for i in range(w, w + n)])
    off = np.array([LEVEL_OFFSET.get(max(int(l), 0), 12.0) for l in lvl])
    # 坑口の前後は地表から高架へ徐々に上がる (PORTAL_RAMP m かけて推定地上高まで)
    step = float(np.median(ds))
    dist = np.full(n, np.inf)
    for i in np.flatnonzero(tun):
        k = np.arange(n); d = np.minimum((k - i) % n, (i - k) % n) * step
        dist = np.minimum(dist, d)
    off = np.where(tun, 0.0, off * np.clip(dist / PORTAL_RAMP, 0, 1))
    z = base + off
    # トンネル: 坑口の高さを直線で結ぶ (山の地表に沿わせない)
    for a, b in runs(tun):
        ia, ib = (a - 1) % n, (b + 1) % n
        L = (b - a) % n + 1
        t = np.arange(1, L + 1) / (L + 1)
        z[(a + np.arange(L)) % n] = z[ia] * (1 - t) + z[ib] * t
    z = circ_smooth(circ_smooth(z, 41), 41)  # 約200m窓×2
    for it in range(5000):
        grade = (np.roll(z, -1) - z) / ds
        bad = np.abs(grade) > MAX_GRADE
        if not bad.any():
            break
        m = bad | np.roll(bad, 1) | np.roll(bad, -1)
        zl = (np.roll(z, 1) + np.roll(z, -1)) / 2
        z = np.where(m, 0.5 * z + 0.5 * zl, z)
    grade = (np.roll(z, -1) - z) / ds

    # CSV 上書き
    fields = list(rows[0].keys())
    for r, zi, gi, gr in zip(rows, z, gnd, grade):
        r["z_m"] = f"{zi:.2f}"; r["ground_m"] = f"{gi:.1f}"; r["grade"] = f"{gr:.4f}"
    with open(cl_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)

    # course JSON 上書き
    cpath = f"{D}/course_ring_inner.json"
    c = json.load(open(cpath, encoding="utf-8"))
    step = int(round(c["segment_length_m"] / c["sample_step_m"]))
    for k, seg in enumerate(c["segments"]):
        seg["z"] = round(float(z[min(k * step, n - 1)]), 2)
        seg["ground"] = round(float(gnd[min(k * step, n - 1)]), 2)
    c["coordinate_system"]["z"] = "elevation [m] (ground: PLATEAU DEM, deck height above ground: estimated)"
    gsi = source == "gsi"
    c["elevation_note"] = (("地盤標高は 国土地理院 標高タイル(DEM5A 航空レーザ 5m, 欠けは DEM10B)の実測値。" if gsi else
                            "地盤標高は PLATEAU 福岡市 地形モデル(DEM, 原典: 国土地理院 基盤地図情報 数値標高モデル)の実測値。")
                           + "路面は 地盤 + OSM layer からの推定地上高(高架)。トンネルは坑口間を直線で結ぶ。")
    c["level_offset_m"] = {str(k): v for k, v in LEVEL_OFFSET.items()}
    c["stats"].update({
        "z_min": round(float(z.min()), 1), "z_max": round(float(z.max()), 1),
        "ground_min": round(float(gnd.min()), 1), "ground_max": round(float(gnd.max()), 1),
        "max_grade_pct": round(float(np.abs(grade).max() * 100), 2),
    })
    att = c["attribution"].split("; elevation:")[0]
    c["attribution"] = att + ("; elevation: 国土地理院 標高タイル" if gsi else "; elevation: 国土交通省 Project PLATEAU 福岡市 3D都市モデル(地形モデル)")
    json.dump(c, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(c["stats"], ensure_ascii=False))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "extract":
        extract(*sys.argv[2:5])
    elif cmd == "extract-gsi":
        extract_gsi(*sys.argv[2:4])
    elif cmd == "apply":
        apply(*sys.argv[2:5])
    else:
        sys.exit(__doc__)
