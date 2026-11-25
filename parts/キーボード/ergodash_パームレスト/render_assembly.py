"""組み立てた状態の確認図 (out/assembly.png) を描く。make_print.py の後に実行する。"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import make_print as mp

WOOD_T = 15.0  # 図に描く木の厚み (仮)

g = mp.build_left()
x0, y0, x1, y1 = g["rest2d"].bounds
wood = trimesh.creation.box(extents=(x1 - x0, y1 - y0, WOOD_T))
wood.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, mp.ADAPTER_T + WOOD_T / 2))
items = [
    (mp.to_trimesh(g["plate"]), "#9a9a9a"),
    (mp.to_trimesh(g["adapter"]), "#4f7fa6"),
    (wood, "#c9a46a"),
]
fig = plt.figure(figsize=(14, 7))
for i, (elev, azim) in enumerate([(35, -60), (-30, -60)]):
    ax = fig.add_subplot(1, 2, i + 1, projection="3d")
    for tm, color in items:
        if color == "#c9a46a" and elev < 0:
            continue
        pc = Poly3DCollection(tm.vertices[tm.faces], facecolor=color, edgecolor="none", alpha=1.0)
        pc.set_facecolor(color)
        ax.add_collection3d(pc)
    ax.set_xlim(-10, 145)
    ax.set_ylim(-95, 125)
    ax.set_zlim(-20, 40)
    ax.set_box_aspect((155, 220, 60))
    ax.view_init(elev=elev, azim=azim)
    ax.set_title("top" if elev > 0 else "bottom (wood hidden)")
    ax.set_axis_off()
fig.savefig(mp.OUT / "assembly.png", dpi=130, bbox_inches="tight")
