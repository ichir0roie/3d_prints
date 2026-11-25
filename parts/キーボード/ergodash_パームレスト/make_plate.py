"""ErgoDash (rev1.2) のボトムプレートを手前に延ばし、木のパームレストを載せるプレートを作る。

元の外形と穴は omkbd/ErgoDash の Case/rev1.2/ergodash-rev1-2.svg (MIT, (c) 2018 omkbd)
から取り出したもの (ergodash_rev1.2_bottom.json)。

出力 (out/):
  plate_L.dxf, plate_R.dxf  切り出し用。外形と穴だけ (レイヤー CUT)
  rest_L.dxf,  rest_R.dxf   木のレストの外形 (原寸)。木を切るときの型紙用
  preview.png               寸法の確認用

座標: mm, 上から見た図, 原点は元のプレートの左下, y が奥 (Pro Micro 側) 向き。
手前 (y < 0) にレストが付く。

使い方:
  pip install shapely ezdxf matplotlib
  python make_plate.py
"""

import json
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

# ---- パラメータ -------------------------------------------------------------
REST_DEPTH = 85.0  # レストの奥行き (手前方向, 元のプレートの手前の辺から)
GAP = 3.0  # キーボードとレストのすき間
REST_CORNER_R = 6.0  # レストとプレート手前側の角の丸み
REST_EDGE_R = 4.0  # レストの奥側 (キーボード側) の角の丸み
MOUNT_HOLE_D = 3.4  # レストを留める穴 (M3 の通し穴)
MOUNT_INSET = 20.0  # 留め穴をレストの縁からどれだけ内側に置くか
FEET_D = 10.0  # 追加するゴム足の径 (参考表示のみ)
FEET_INSET = 9.0  # 追加するゴム足の中心をプレートの縁からどれだけ内側に置くか
SPACER_HOLE_D = None  # 元のスペーサー穴の径。None なら元データのまま (約 1.95)
# -----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def load_original():
    d = json.loads((HERE / "ergodash_rev1.2_bottom.json").read_text(encoding="utf-8"))
    outline = Polygon(d["outline"]).buffer(0)
    holes = [(x, y, (SPACER_HOLE_D / 2) if SPACER_HOLE_D else r) for x, y, r in d["holes"]]
    return outline, holes


def rounded(poly, r):
    return poly.buffer(r, join_style="round").buffer(-2 * r, join_style="round").buffer(r, join_style="round")


def build():
    orig, spacer_holes = load_original()
    minx, miny, maxx, maxy = orig.bounds
    # 元のプレートの手前の辺 (親指クラスタより左のまっすぐな辺) の高さ
    front_y = min(y for x, y in orig.exterior.coords if x < 50)

    ext = rounded(box(minx, miny - REST_DEPTH, maxx, front_y + REST_CORNER_R * 2), REST_CORNER_R)
    ext = ext.intersection(box(minx - 1, miny - REST_DEPTH - 1, maxx + 1, front_y))
    # 元のプレートの左手前の角の丸み (R2) が段差として残るので埋める
    corner_fill = box(minx, front_y - 1, minx + 4, front_y + 4).intersection(orig.envelope)
    plate = unary_union([orig, ext, corner_fill])

    rest = ext.difference(orig.buffer(GAP, join_style="round"))
    if isinstance(rest, MultiPolygon):
        rest = max(rest.geoms, key=lambda g: g.area)
    rest = rounded(rest, REST_EDGE_R)

    inner = rest.buffer(-MOUNT_INSET)
    rx0, ry0, rx1, ry1 = rest.bounds
    mounts = []
    for cx, cy in [(rx0, ry0), (rx1, ry0), (rx0, ry1), (rx1, ry1)]:
        p = nearest_points(inner, Point(cx, cy))[0]
        if all(p.distance(Point(q)) > 15 for q in mounts):
            mounts.append((p.x, p.y))

    feet_area = plate.buffer(-FEET_INSET)
    feet = [nearest_points(feet_area, Point(cx, cy))[0] for cx, cy in [(minx, ry0), (maxx, ry0)]]
    feet = [(p.x, p.y) for p in feet]

    return dict(
        orig=orig,
        plate=plate,
        rest=rest,
        spacer_holes=spacer_holes,
        mounts=mounts,
        feet=feet,
        front_y=front_y,
    )


def mirror(g, cx):
    """左右反転 (もう片方の手用)."""
    if isinstance(g, list):
        out = []
        for item in g:
            x, *rest = item
            out.append((2 * cx - x, *rest))
        return out
    return affinity.scale(g, xfact=-1, yfact=1, origin=(cx, 0))


def write_plate_dxf(path, plate, spacer_holes, mounts):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("CUT", color=1)
    msp = doc.modelspace()
    msp.add_lwpolyline(list(plate.exterior.coords), close=True, dxfattribs={"layer": "CUT"})
    for ring in plate.interiors:
        msp.add_lwpolyline(list(ring.coords), close=True, dxfattribs={"layer": "CUT"})
    for x, y, r in spacer_holes:
        msp.add_circle((x, y), r, dxfattribs={"layer": "CUT"})
    for x, y in mounts:
        msp.add_circle((x, y), MOUNT_HOLE_D / 2, dxfattribs={"layer": "CUT"})
    doc.saveas(path)


def write_rest_dxf(path, rest, mounts):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("OUTLINE", color=3)
    doc.layers.add("DRILL", color=1)
    msp = doc.modelspace()
    msp.add_lwpolyline(list(rest.exterior.coords), close=True, dxfattribs={"layer": "OUTLINE"})
    for x, y in mounts:
        msp.add_circle((x, y), 1.0, dxfattribs={"layer": "DRILL"})
        msp.add_line((x - 4, y), (x + 4, y), dxfattribs={"layer": "DRILL"})
        msp.add_line((x, y - 4), (x, y + 4), dxfattribs={"layer": "DRILL"})
    doc.saveas(path)


def preview(path, sides):
    fig, axes = plt.subplots(1, 2, figsize=(12, 9))
    for ax, (name, g) in zip(axes, sides):
        def fill(poly, **kw):
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, **kw)

        fill(g["plate"], fc="#dde3ea", ec="#333", lw=1.2)
        fill(g["orig"], fc="#b9c4d0", ec="#555", lw=0.6, ls="--")
        fill(g["rest"], fc="#d9b98c", ec="#7a5528", lw=1.0, alpha=0.85)
        for x, y, r in g["spacer_holes"]:
            ax.add_patch(plt.Circle((x, y), r, fc="white", ec="k", lw=0.6))
        for x, y in g["mounts"]:
            ax.add_patch(plt.Circle((x, y), MOUNT_HOLE_D / 2, fc="white", ec="r", lw=0.8))
        for x, y in g["feet"]:
            ax.add_patch(plt.Circle((x, y), FEET_D / 2, fc="none", ec="g", lw=0.8, ls=":"))
        px0, py0, px1, py1 = g["plate"].bounds
        rx0, ry0, rx1, ry1 = g["rest"].bounds
        ax.set_title(f"{name}: plate {px1 - px0:.1f} x {py1 - py0:.1f} mm / rest {rx1 - rx0:.1f} x {ry1 - ry0:.1f} mm")
        ax.set_aspect("equal")
        ax.grid(True, lw=0.3)
    fig.text(
        0.5,
        0.02,
        "grey dashed: original ErgoDash bottom plate / tan: wooden rest / red: rest mounting holes (M3) / "
        "green dotted: extra rubber feet (reference only)",
        ha="center",
        fontsize=8,
    )
    fig.savefig(path, dpi=150, bbox_inches="tight")


def main():
    OUT.mkdir(exist_ok=True)
    left = build()
    cx = (left["orig"].bounds[0] + left["orig"].bounds[2]) / 2
    right = {k: (mirror(v, cx) if k not in ("front_y",) else v) for k, v in left.items()}

    # 元データの向きでは親指クラスタが右下にあるので、上から見て左手側
    for name, g in (("L", left), ("R", right)):
        write_plate_dxf(OUT / f"plate_{name}.dxf", g["plate"], g["spacer_holes"], g["mounts"])
        write_rest_dxf(OUT / f"rest_{name}.dxf", g["rest"], g["mounts"])
    preview(OUT / "preview.png", (("Left", left), ("Right", right)))

    px0, py0, px1, py1 = left["plate"].bounds
    rx0, ry0, rx1, ry1 = left["rest"].bounds
    print(f"plate: {px1 - px0:.1f} x {py1 - py0:.1f} mm (x2)")
    print(f"rest : {rx1 - rx0:.1f} x {ry1 - ry0:.1f} mm (x2)")
    print("mount holes:", [(round(x, 1), round(y, 1)) for x, y in left["mounts"]])


if __name__ == "__main__":
    main()
