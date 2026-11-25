"""ErgoDash (rev1.2) の印刷用ボトムプレートと、木のパームレストをつなぐアダプターを作る。

構成 (左右それぞれ):
  plate    キーボードの下のプレート。外形は元のボトムプレートと同じで、
           枠・スペーサー穴のボス・それをつなぐリブだけを残して肉抜きする。
           手前の辺の外側に、アダプターを留める「帯」(高さ BAND_H) が付く。
  adapter  帯の上に重なる舌と、木のレストを載せる台。上面は平ら。
           木のレストは台の上に載せ、下から M3 で留める。
  rest     木のレスト。ただの長方形 (rest_*.dxf は下穴位置の型紙)。

ボルト:
  プレート ⇔ アダプター  M3x8 皿ねじ (上から) + M3 ナット (帯の下面の六角穴)
  アダプター ⇔ 木        M3 (下から) + 木に埋めた鬼目ナット
                         または上から通しボルトにして、台の下面の六角穴にナット
  プレート ⇔ スペーサー  元のキットの M2x5 (下面のざぐりに頭を沈める)

座標: mm, 上から見た図, 原点は元のプレートの左下, y が奥 (Pro Micro 側), z が上。
床に置いたときの下面が z = 0。

使い方:
  pip install shapely manifold3d trimesh ezdxf matplotlib
  python make_print.py
"""

import json
import math
from pathlib import Path

import ezdxf
import manifold3d as m3
import matplotlib
import numpy as np
import trimesh
from shapely import affinity, delaunay_triangles
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points, unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---- パラメータ -------------------------------------------------------------
PLATE_T = 4.0  # プレートの厚み
FRAME_W = 6.0  # 外周の枠の幅
RIB_W = 6.0  # リブの幅
BOSS_D = 10.0  # スペーサー穴まわりのボスの径
PAD_D = 14.0  # ゴム足を貼る所の径 (肉抜きしない)
MIN_OPENING_AREA = 40.0  # これより小さい肉抜きは埋める
OPENING_R = 2.0  # 肉抜きの角の丸み

M2_HOLE_D = 2.3  # M2 の通し穴
M2_CBORE_D = 4.4  # M2 なべ頭のざぐり径 (下面から)
M2_CBORE_DEPTH = 2.0  # ざぐりの深さ。残りの厚み = PLATE_T - これ

BAND_GAP = 1.0  # 帯の手前の面を、親指クラスタのいちばん手前からどれだけ出すか
BAND_H = 5.0  # 帯の高さ (この上にアダプターの舌が載る)

ADAPTER_T = 9.0  # アダプターの台の厚み = 木のレストの下面の高さ
REST_DEPTH = 85.0  # 木のレストの奥行き (帯の手前の面から手前へ)
ADAPTER_FRAME_W = 12.0  # アダプターの台の枠の幅
FIT = 0.3  # はめあいのすき間

M3_HOLE_D = 3.4
M3_CSK_D = 6.6  # 皿ねじの頭の座ぐり (90 度)
M3_NUT_AF = 5.5 + 0.4  # M3 ナットの二面幅 + すき間
M3_NUT_DEPTH = 3.0
WOOD_BOLT_INSET = 15.0  # 木を留める穴を台の縁からどれだけ内側に置くか
# -----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
m3.set_circular_segments(48)


# ---- 2D -> 3D ---------------------------------------------------------------
def cs(geom):
    if geom.is_empty:
        return m3.CrossSection()
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    rings = []
    for p in polys:
        p = orient(p, 1.0)
        rings.append(np.array(p.exterior.coords[:-1]))
        rings += [np.array(r.coords[:-1]) for r in p.interiors]
    return m3.CrossSection(rings, m3.FillRule.Positive)


def prism(geom, z0, z1):
    return m3.Manifold.extrude(cs(geom), z1 - z0).translate((0, 0, z0))


def cyl(x, y, d, z0, z1, d_top=None):
    r_top = (d_top if d_top is not None else d) / 2
    return m3.Manifold.cylinder(z1 - z0, d / 2, r_top).translate((x, y, z0))


def hex_prism(x, y, af, z0, z1):
    r = af / math.sqrt(3)
    pts = [(x + r * math.cos(math.radians(60 * i)), y + r * math.sin(math.radians(60 * i))) for i in range(6)]
    return prism(Polygon(pts), z0, z1)


def union(items):
    items = [i for i in items if i is not None]
    return m3.Manifold.batch_boolean(items, m3.OpType.Add) if items else m3.Manifold()


# ---- 形 ---------------------------------------------------------------------
def load_original():
    d = json.loads((HERE / "ergodash_rev1.2_bottom.json").read_text(encoding="utf-8"))
    return Polygon(d["outline"]).buffer(0), [(x, y) for x, y, _ in d["holes"]]


def corner_points(area, targets):
    return [tuple(nearest_points(area, Point(t))[0].coords[0]) for t in targets]


def skeleton(orig, keep_points):
    """枠・ボス・リブだけ残した 2D 形."""
    inner = orig.buffer(-FRAME_W, join_style="mitre")
    keep = [Point(p).buffer(BOSS_D / 2) for p in keep_points]
    # ボス同士をつなぐリブ (ドロネー分割の辺)
    tris = delaunay_triangles(unary_union([Point(p) for p in keep_points]))
    edges = set()
    for t in tris.geoms:
        c = list(t.exterior.coords)[:3]
        for i in range(3):
            a, b = sorted([c[i], c[(i + 1) % 3]])
            edges.add((a, b))
    for a, b in edges:
        line = LineString([a, b])
        if line.within(orig.buffer(-1)):
            keep.append(line.buffer(RIB_W / 2, cap_style="flat"))
    # 各ボスから一番近い枠へのリブ
    for p in keep_points:
        q = nearest_points(orig.exterior, Point(p))[0]
        keep.append(LineString([p, q.coords[0]]).buffer(RIB_W / 2, cap_style="flat"))
    openings = inner.difference(unary_union(keep))
    openings = openings.buffer(-OPENING_R).buffer(OPENING_R)
    geoms = openings.geoms if isinstance(openings, MultiPolygon) else [openings]
    openings = unary_union([g for g in geoms if g.area >= MIN_OPENING_AREA])
    return orig.difference(openings), openings


def build_left():
    orig, spacer_holes = load_original()
    minx, miny, maxx, maxy = orig.bounds
    front_y = min(y for x, y in orig.exterior.coords if x < 50)  # 手前のまっすぐな辺
    y_b = miny - BAND_GAP  # 帯の手前の面 = 木のレストの奥の辺

    # 帯: 手前の辺の外側。キーボードの基板の外なので、高くしても当たらない
    band = box(minx, y_b, maxx, front_y + 1).difference(orig)
    band = max(band.geoms, key=lambda g: g.area) if isinstance(band, MultiPolygon) else band

    # 帯のボルト: 帯の中に余裕をもって入る所に 3 本
    room = band.buffer(-(M3_NUT_AF / 2 + 2.0))
    joint_bolts = []
    for tx in (minx + 15, (minx + maxx) / 2 - 10, maxx - 8):
        p = nearest_points(room, Point(tx, (y_b + front_y) / 2))[0]
        joint_bolts.append(p.coords[0])

    # ゴム足のパッド (プレートの四隅)
    pad_area = orig.buffer(-(PAD_D / 2 + 1))
    pads = corner_points(pad_area, [(minx, miny), (maxx, miny), (minx, maxy), (maxx, maxy)])

    skel2d, openings = skeleton(orig, spacer_holes + pads)

    # ---- plate ----
    plate = prism(skel2d, 0, PLATE_T) + prism(band.buffer(0.01), 0, BAND_H)
    cut = []
    for x, y in spacer_holes:
        cut.append(cyl(x, y, M2_HOLE_D, -1, BAND_H + 1))
        cut.append(cyl(x, y, M2_CBORE_D, -1, M2_CBORE_DEPTH))
    for x, y in joint_bolts:
        cut.append(cyl(x, y, M3_HOLE_D, -1, BAND_H + 1))
        cut.append(hex_prism(x, y, M3_NUT_AF, -1, M3_NUT_DEPTH))
    plate = plate - union(cut)

    # ---- adapter ----
    body2d = box(minx, y_b - REST_DEPTH, maxx, y_b - FIT)
    tongue2d = unary_union([band, box(minx, y_b - 2, maxx, y_b)]).difference(orig.buffer(FIT))
    tongue2d = tongue2d.buffer(-0.5).buffer(0.5)
    by0, by1 = y_b - REST_DEPTH, y_b - FIT
    wood_bolts = [
        (minx + WOOD_BOLT_INSET, by0 + WOOD_BOLT_INSET),
        (maxx - WOOD_BOLT_INSET, by0 + WOOD_BOLT_INSET),
        (minx + WOOD_BOLT_INSET, by1 - WOOD_BOLT_INSET),
        (maxx - WOOD_BOLT_INSET, by1 - WOOD_BOLT_INSET),
    ]
    a_pads = [
        (minx + PAD_D / 2 + 1, by0 + PAD_D / 2 + 1),
        (maxx - PAD_D / 2 - 1, by0 + PAD_D / 2 + 1),
    ]
    # 台の肉抜き: 枠 + 木を留める穴のボス + 中央の縦横リブ
    cx, cy = (minx + maxx) / 2, (by0 + by1) / 2
    a_keep = [Point(p).buffer(BOSS_D / 2 + 2) for p in wood_bolts + a_pads]
    a_keep.append(box(cx - RIB_W / 2, by0, cx + RIB_W / 2, by1))
    a_keep.append(box(minx, cy - RIB_W / 2, maxx, cy + RIB_W / 2))
    a_keep += [LineString([p, (cx, cy)]).buffer(RIB_W / 2) for p in wood_bolts]
    a_open = body2d.buffer(-ADAPTER_FRAME_W, join_style="mitre").difference(unary_union(a_keep))
    a_open = a_open.buffer(-OPENING_R).buffer(OPENING_R)
    body_skel = body2d.difference(a_open)

    adapter = prism(body_skel, 0, ADAPTER_T) + prism(tongue2d, BAND_H + FIT, ADAPTER_T)
    cut = []
    for x, y in joint_bolts:
        cut.append(cyl(x, y, M3_HOLE_D, 0, ADAPTER_T + 1))
        csk_depth = (M3_CSK_D - M3_HOLE_D) / 2
        cut.append(cyl(x, y, M3_HOLE_D, ADAPTER_T - csk_depth, ADAPTER_T + 0.01, d_top=M3_CSK_D))
    for x, y in wood_bolts:
        cut.append(cyl(x, y, M3_HOLE_D, -1, ADAPTER_T + 1))
        cut.append(hex_prism(x, y, M3_NUT_AF, -1, M3_NUT_DEPTH))
    adapter = adapter - union(cut)

    rest2d = box(minx, y_b - REST_DEPTH, maxx, y_b - FIT)

    return dict(
        orig=orig,
        skel2d=skel2d,
        band=band,
        plate=plate,
        adapter=adapter,
        rest2d=rest2d,
        body_skel=body_skel,
        tongue2d=tongue2d,
        spacer_holes=spacer_holes,
        joint_bolts=joint_bolts,
        wood_bolts=wood_bolts,
        pads=pads,
        a_pads=a_pads,
        cx=(minx + maxx) / 2,
    )


# ---- 出力 -------------------------------------------------------------------
def to_trimesh(man):
    mesh = man.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts))


def mirror_x(man, cx):
    return man.translate((-cx, 0, 0)).mirror((1, 0, 0)).translate((cx, 0, 0))


def export(man, path, flip=False):
    if flip:  # 上面を下にして印刷する
        man = man.mirror((0, 0, 1))
    b = man.bounding_box()
    man = man.translate((-b[0], -b[1], -b[2]))
    tm = to_trimesh(man)
    assert tm.is_watertight, path
    tm.export(path)
    return tm


def write_rest_dxf(path, rest2d, wood_bolts):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("OUTLINE", color=3)
    doc.layers.add("DRILL", color=1)
    msp = doc.modelspace()
    msp.add_lwpolyline(list(rest2d.exterior.coords), close=True, dxfattribs={"layer": "OUTLINE"})
    for x, y in wood_bolts:
        msp.add_circle((x, y), 1.0, dxfattribs={"layer": "DRILL"})
        msp.add_line((x - 4, y), (x + 4, y), dxfattribs={"layer": "DRILL"})
        msp.add_line((x, y - 4), (x, y + 4), dxfattribs={"layer": "DRILL"})
    doc.saveas(path)


def preview(path, g):
    fig, ax = plt.subplots(figsize=(8, 11))

    def fill(geom, **kw):
        for p in geom.geoms if isinstance(geom, MultiPolygon) else [geom]:
            xs, ys = p.exterior.xy
            ax.fill(xs, ys, **kw)
            for r in p.interiors:
                xs, ys = r.xy
                ax.fill(xs, ys, fc="white", ec=kw.get("ec", "k"), lw=0.6)

    fill(g["rest2d"], fc="#ecd9bb", ec="#b08a55", lw=0.8, ls="--")
    fill(g["body_skel"], fc="#9fb7c9", ec="#2b4a63", lw=0.8)
    fill(g["tongue2d"], fc="#7d9bb3", ec="#2b4a63", lw=0.8)
    fill(g["skel2d"], fc="#c9c9c9", ec="#333", lw=0.8)
    fill(g["band"], fc="#a8a8a8", ec="#333", lw=0.8)
    xs, ys = g["orig"].exterior.xy
    ax.plot(xs, ys, color="#555", lw=0.5, ls=":")
    for x, y in g["spacer_holes"]:
        ax.add_patch(plt.Circle((x, y), M2_CBORE_D / 2, fc="white", ec="k", lw=0.6))
    for x, y in g["joint_bolts"]:
        ax.add_patch(plt.Circle((x, y), M3_CSK_D / 2, fc="white", ec="r", lw=0.9))
    for x, y in g["wood_bolts"]:
        ax.add_patch(plt.Circle((x, y), M3_NUT_AF / 2, fc="white", ec="m", lw=0.9))
    for x, y in g["pads"] + g["a_pads"]:
        ax.add_patch(plt.Circle((x, y), PAD_D / 2 - 2, fc="none", ec="g", lw=0.8, ls=":"))
    ax.set_aspect("equal")
    ax.grid(True, lw=0.3)
    ax.set_title("Left (top view). grey: plate / blue: adapter / tan dashed: wooden rest")
    fig.text(
        0.5,
        0.03,
        "red: plate-adapter M3 (countersunk from top, nut under band)  magenta: adapter-wood M3  "
        "green dotted: rubber feet",
        ha="center",
        fontsize=8,
    )
    fig.savefig(path, dpi=150, bbox_inches="tight")


def main():
    OUT.mkdir(exist_ok=True)
    g = build_left()
    cx = g["cx"]
    parts = {
        "plate_L": (g["plate"], False),
        "plate_R": (mirror_x(g["plate"], cx), False),
        "adapter_L": (g["adapter"], True),
        "adapter_R": (mirror_x(g["adapter"], cx), True),
    }
    for name, (man, flip) in parts.items():
        tm = export(man, OUT / f"{name}.stl", flip=flip)
        print(f"{name}: {' x '.join(f'{v:.1f}' for v in tm.extents)} mm, {tm.volume / 1000:.1f} cm3")

    write_rest_dxf(OUT / "rest_print_L.dxf", g["rest2d"], g["wood_bolts"])
    mirrored = [(2 * cx - x, y) for x, y in g["wood_bolts"]]
    write_rest_dxf(OUT / "rest_print_R.dxf", affinity.scale(g["rest2d"], xfact=-1, origin=(cx, 0)), mirrored)
    preview(OUT / "print_preview.png", g)

    rx0, ry0, rx1, ry1 = g["rest2d"].bounds
    print(f"wooden rest: {rx1 - rx0:.1f} x {ry1 - ry0:.1f} mm, bottom at z = {ADAPTER_T} mm")


if __name__ == "__main__":
    main()
