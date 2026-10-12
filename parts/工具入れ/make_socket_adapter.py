"""工具入れの6角穴に挿して、3/8インチソケットを掛けるアダプタを .blend に作る。

下が6角(穴に挿す)、上が4角(ソケットの差込角に挿す)。

使い方(画面なしで実行):
    blender -b holes.orig.blend --python make_socket_adapter.py -- socket_adapter.blend socket_adapter.stl

単位は mm(シーンの 1 単位 = 1mm)。モデルは使うときの向き(6角が下)。
"""
import math
import sys

import bmesh
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT_BLEND, OUT_STL = argv[0], argv[1]

# --- 寸法 ---
HEX_FLAT = 6.3         # 6角の対辺(工具入れの穴 6.5 に挿す)
HEX_LEN = 17.5         # 6角の長さ(穴の深さ 18 より少し短く、4角の下面が台に乗る)
HEX_CHAMFER = 0.5      # 6角の先端の面取り
SQ = 9.2               # 4角の一辺(3/8インチ 9.5mm の差込角に挿す)
SQ_LEN = 10.0          # 4角の長さ
SQ_CHAMFER = 1.0       # 4角の先端の面取り


def polygon(r, n, start_deg):
    return [(r * math.cos(math.radians(start_deg + 360 / n * i)),
             r * math.sin(math.radians(start_deg + 360 / n * i))) for i in range(n)]


def prism_mesh(name, rings):
    """rings: [(z, [(x, y), ...]), ...] を下から順につないだ閉じた柱。"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    loops = [[bm.verts.new((x, y, z)) for x, y in pts] for z, pts in rings]
    bm.faces.new(list(reversed(loops[0])))
    bm.faces.new(loops[-1])
    for lo, hi in zip(loops, loops[1:]):
        n = len(lo)
        for i in range(n):
            bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return me


# --- シーンを片付ける(カメラとライトは残す) ---
scene = bpy.context.scene
for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o)
for c in list(bpy.data.collections):
    if c.name != "Collection":
        bpy.data.collections.remove(c)

col = bpy.data.collections.new("ソケットアダプタ")
scene.collection.children.link(col)

hex_r = HEX_FLAT / math.sqrt(3)
sq_r = SQ / math.sqrt(2)
top = HEX_LEN + SQ_LEN

# 6角(対辺が X 方向、工具入れの穴と同じ向き)
hex_part = bpy.data.objects.new("6角", prism_mesh("6角", [
    (0, polygon(hex_r - HEX_CHAMFER / math.cos(math.radians(30)), 6, 30)),
    (HEX_CHAMFER, polygon(hex_r, 6, 30)),
    (HEX_LEN + 1, polygon(hex_r, 6, 30)),  # 4角に 1mm 食い込ませる
]))
col.objects.link(hex_part)

# 4角(辺が X/Y 方向)
sq_chamfer_r = (SQ / 2 - SQ_CHAMFER) * math.sqrt(2)
sq_part = bpy.data.objects.new("4角", prism_mesh("4角", [
    (HEX_LEN, polygon(sq_r, 4, 45)),
    (top - SQ_CHAMFER, polygon(sq_r, 4, 45)),
    (top, polygon(sq_chamfer_r, 4, 45)),
]))
col.objects.link(sq_part)
sq_part.display_type = "WIRE"
sq_part.hide_render = True

m = hex_part.modifiers.new("4角を足す", "BOOLEAN")
m.operation = "UNION"
m.solver = "EXACT"
m.object = sq_part
hex_part.name = "ソケットアダプタ"

note = bpy.data.texts.get("説明") or bpy.data.texts.new("説明")
note.from_string(f"""ソケットアダプタ(単位 mm)

最終形は「ソケットアダプタ」オブジェクト(6角のメッシュ)。
Boolean モディファイア「4角を足す」で「4角」(ワイヤー表示)を結合している。

  6角: 対辺 {HEX_FLAT}, 長さ {HEX_LEN}, 先端の面取り {HEX_CHAMFER}
  4角: 一辺 {SQ}, 長さ {SQ_LEN}, 先端の面取り {SQ_CHAMFER}
全長 {top} mm

モデルは使うときの向き(6角が下)。印刷するときは、スライサーで
上下を反転して 4角の先端を下にする(段差のオーバーハングが無くなる)。
make_socket_adapter.py で作り直せる。
""")

for o in bpy.context.view_layer.objects:
    o.select_set(o == hex_part)
bpy.context.view_layer.objects.active = hex_part

bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
bpy.ops.wm.stl_export(filepath=OUT_STL, export_selected_objects=True, apply_modifiers=True)

ev = hex_part.evaluated_get(bpy.context.evaluated_depsgraph_get())
print("RESULT", OUT_BLEND, "dims", tuple(round(d, 2) for d in ev.dimensions),
      "verts", len(ev.data.vertices), "faces", len(ev.data.polygons))
