"""6角ビットの工具入れを .blend に組み立てる。

使い方(画面なしで実行):
    blender -b <入力.blend> --python make_tool_holder.py -- <出力.blend> <出力.stl> [列 行]

例:
    blender -b holes.orig.blend --python make_tool_holder.py -- holes.blend tool_holder.stl 10 5
    blender -b holes.orig.blend --python make_tool_holder.py -- holes_sample.blend tool_holder_sample.stl 3 1

単位は mm(シーンの 1 単位 = 1mm)。
"""
import math
import sys

import bmesh
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT_BLEND, OUT_STL = argv[0], argv[1]
BIT_COLS, BIT_ROWS = (int(v) for v in (argv[2:4] or (10, 5)))

# --- 寸法 ---
FLOOR = 5.0            # 穴の下に残す底の厚さ
BIT_DEPTH = 18.0       # ビット穴の深さ
BIT_HEX_FLAT = 6.5     # ビット穴の対辺(1/4インチ 6.35mm + 余裕)
BIT_PITCH_X = 15.0
BIT_PITCH_Y = 12.0
MARGIN_X = 7.5         # ビット穴の中心から左右の端まで
MARGIN_Y = 8.0         # ビット穴の中心から前後の端まで

block_h = FLOOR + BIT_DEPTH
width = (BIT_COLS - 1) * BIT_PITCH_X + 2 * MARGIN_X
depth = (BIT_ROWS - 1) * BIT_PITCH_Y + 2 * MARGIN_Y


def box_mesh(name, x0, y0, z0, x1, y1, z1):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 if v.co.x < 0 else x1
        v.co.y = y0 if v.co.y < 0 else y1
        v.co.z = z0 if v.co.z < 0 else z1
    bm.to_mesh(me)
    bm.free()
    return me


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


def add_array(obj, name, offset, count):
    m = obj.modifiers.new(name, "ARRAY")
    m.use_relative_offset = False
    m.use_constant_offset = True
    m.constant_offset_displace = offset
    m.count = count


# --- シーンを片付ける(カメラとライトは残す) ---
scene = bpy.context.scene
for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o)
for c in list(bpy.data.collections):
    if c.name != "Collection":
        bpy.data.collections.remove(c)

main_col = bpy.data.collections.new("工具入れ")
parts_col = bpy.data.collections.new("形状パーツ")
scene.collection.children.link(main_col)
main_col.children.link(parts_col)

# --- 本体(ビット台) ---
body = bpy.data.objects.new("工具入れ", box_mesh("ビット台", 0, 0, 0, width, depth, block_h))
main_col.objects.link(body)

# --- ビット穴(1個をモデリングし、Array で並べる。対辺が X 方向) ---
r = BIT_HEX_FLAT / math.sqrt(3)  # 外接円の半径
hexagon = [(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i)))
           for i in range(6)]
hole = bpy.data.objects.new("ビット穴", prism_mesh("ビット穴", [
    (FLOOR, hexagon),
    (block_h + 2, hexagon),
]))
hole.location = (MARGIN_X, MARGIN_Y, 0)
parts_col.objects.link(hole)
add_array(hole, "横に並べる", (BIT_PITCH_X, 0, 0), BIT_COLS)
add_array(hole, "縦に並べる", (0, BIT_PITCH_Y, 0), BIT_ROWS)
hole.display_type = "WIRE"
hole.hide_render = True

m = body.modifiers.new("ビット穴を抜く", "BOOLEAN")
m.operation = "DIFFERENCE"
m.solver = "EXACT"
m.object = hole

# --- 説明をファイルに残す(Blender の Text Editor で読める) ---
note = bpy.data.texts.get("説明") or bpy.data.texts.new("説明")
note.from_string(f"""工具入れ(単位 mm)

最終形は「工具入れ」オブジェクト。Boolean モディファイア「ビット穴を抜く」で
形状パーツ/ビット穴(ワイヤー表示・レンダリング対象外)を差し引いている。

  個数・間隔: ビット穴の Array モディファイア(横に並べる・縦に並べる)
  穴の大きさ: ビット穴のメッシュ(対辺 {BIT_HEX_FLAT}, 深さ {BIT_DEPTH})
  個数を増やしたら「工具入れ」の大きさも合わせて広げる。

今の設定: {BIT_COLS}x{BIT_ROWS} 穴(間隔 {BIT_PITCH_X}x{BIT_PITCH_Y})
全体 {width} x {depth} x {block_h} mm

ソケットは socket_adapter.blend のアダプタを穴に挿して掛ける。
make_tool_holder.py で作り直せる。
""")

for o in bpy.context.view_layer.objects:
    o.select_set(o == body)
bpy.context.view_layer.objects.active = body

bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
bpy.ops.wm.stl_export(filepath=OUT_STL, export_selected_objects=True, apply_modifiers=True)

ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
print("RESULT", OUT_BLEND, "dims", tuple(round(d, 2) for d in ev.dimensions),
      "verts", len(ev.data.vertices), "faces", len(ev.data.polygons))
