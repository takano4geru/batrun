import json, sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import PolyCollection
fm.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"); plt.rcParams["font.family"] = "IPAGothic"
D = sys.argv[1]
cl = np.genfromtxt(f"{D}/course_ring_inner_centerline.csv", delimiter=",", names=True, dtype=None, encoding="utf-8")
c = json.load(open(f"{D}/course_ring_inner.json")); sc = json.load(open(f"{D}/scenery_ring_inner.json"))["buildings"]
fig = plt.figure(figsize=(14, 13)); ax = fig.add_axes([0.05, 0.3, 0.9, 0.67]); ax2 = fig.add_axes([0.05, 0.05, 0.9, 0.2])
polys = [b["footprint"] for b in sc]; hs = [min(b["height"], 60) for b in sc]
pc = PolyCollection(polys, array=np.array(hs), cmap="Greys", linewidths=0); ax.add_collection(pc)
sct = ax.scatter(cl["x_m"], cl["y_m"], c=cl["z_m"], cmap="plasma", s=2, zorder=3)
xs = dict(zip(cl["s_m"], zip(cl["x_m"], cl["y_m"])))
for m in c["landmarks"]:
    i = int(np.searchsorted(cl["s_m"], m["s"])) % len(cl)
    ax.annotate(m["name"], (cl["x_m"][i], cl["y_m"][i]), fontsize=8, color="navy", zorder=4)
ax.plot(cl["x_m"][0], cl["y_m"][0], "g^", ms=12, zorder=5); ax.set_aspect("equal"); ax.set_title(f"{c['name']}  全長 {c['length_m']/1000:.2f} km (▲スタート, 色=路面標高m, 灰=沿線建物 {len(sc)}棟)")
fig.colorbar(sct, ax=ax, shrink=0.5, label="路面標高 [m]")
ax2.fill_between(cl["s_m"] / 1000, 0, cl["ground_m"], color="#cdb", label="地盤")
ax2.plot(cl["s_m"] / 1000, cl["z_m"], color="purple", label="路面(推定)")
t = cl["tunnel"] == 1; ax2.scatter(cl["s_m"][t] / 1000, cl["z_m"][t], s=2, color="k", label="トンネル")
ax2.set_xlabel("距離 [km]"); ax2.set_ylabel("標高 [m]"); ax2.legend(loc="upper right"); ax2.set_xlim(0, c["length_m"] / 1000)
fig.savefig(f"{D}/preview_ring_inner.png", dpi=110)
