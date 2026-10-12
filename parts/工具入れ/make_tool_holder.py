"""6角ビット + 3/8インチソケットの工具入れを .blend に組み立てる。

使い方(画面なしで実行):
    blender -b <入力.blend> --python make_tool_holder.py -- <出力.blend> <出力.stl> [ビット列 ビット行 ソケット列 ソケット行]

例:
    blender -b holes.blend --python make_tool_holder.py -- holes.blend tool_holder.stl 10 5 5 4
    blender -b holes.blend --python make_tool_holder.py -- holes_sample.blend tool_holder_sample.stl 3 1 3 1

単位は mm(シーンの 1 単位 = 1mm)。
"""
import sys

import bmesh
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT_BLEND, OUT_STL = argv[0], argv[1]
BIT_COLS, BIT_ROWS, SOCK_COLS, SOCK_ROWS = (int(v) for v in (argv[2:6] or (10, 5, 5, 4)))

# --- 寸法 ---
FLOOR = 5.0            # 穴の下に残す底の厚さ
BIT_DEPTH = 18.0       # ビット穴の深さ
BIT_HEX_FLAT = 6.5     # ビット穴の対辺(1/4インチ 6.35mm + 余裕)
BIT_PITCH_X = 15.0
BIT_PITCH_Y = 12.0
BIT_MARGIN_Y = 8.0     # ビット穴の中心から前後の端まで

PLATE = 5.0            # ソケット部の板の厚さ
SOCK_PITCH = 30.0
PIN = 9.2              # 差込角ピンの一辺(3/8インチ 9.5mm の穴に挿す)
PIN_HEIGHT = 10.0      # 板の上に出る高さ
PIN_CHAMFER = 1.0      # ピン先端の面取り

OVERLAP = 1.0          # 結合する部品どうしを食い込ませる量

block_h = FLOOR + BIT_DEPTH
width = max(BIT_COLS * BIT_PITCH_X, SOCK_COLS * SOCK_PITCH)
block_d = (BIT_ROWS - 1) * BIT_PITCH_Y + 2 * BIT_MARGIN_Y
plate_d = SOCK_ROWS * SOCK_PITCH


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


def add_boolean(obj, name, operand, op):
    m = obj.modifiers.new(name, "BOOLEAN")
    m.operation = op
    m.solver = "EXACT"
    m.object = operand


def as_helper(obj):
    obj.display_type = "WIRE"
    obj.hide_render = True


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

# --- 本体(ビット台)。他の部品は下のモディファイアでここに足し引きする ---
body = bpy.data.objects.new("工具入れ", box_mesh("ビット台", 0, 0, 0, width, block_d, block_h))
main_col.objects.link(body)

# --- ソケット板 ---
plate = bpy.data.objects.new(
    "ソケット板", box_mesh("ソケット板", 0, block_d - OVERLAP, 0, width, block_d + plate_d, PLATE))
parts_col.objects.link(plate)
as_helper(plate)

# --- ソケットピン(1本をモデリングし、Array で並べる) ---
h, c = PIN / 2, PIN / 2 - PIN_CHAMFER
sq = lambda s: [(-s, -s), (s, -s), (s, s), (-s, s)]
top = PLATE + PIN_HEIGHT
pin = bpy.data.objects.new("ソケットピン", prism_mesh("ソケットピン", [
    (PLATE - OVERLAP, sq(h)),
    (top - PIN_CHAMFER, sq(h)),
    (top, sq(c)),
]))
pin.location = ((width - (SOCK_COLS - 1) * SOCK_PITCH) / 2, block_d + SOCK_PITCH / 2, 0)
parts_col.objects.link(pin)
add_array(pin, "横に並べる", (SOCK_PITCH, 0, 0), SOCK_COLS)
add_array(pin, "縦に並べる", (0, SOCK_PITCH, 0), SOCK_ROWS)
as_helper(pin)

# --- ビット穴(1個をモデリングし、Array で並べる。対辺が X 方向) ---
import math
r = BIT_HEX_FLAT / math.sqrt(3)  # 外接円の半径
hexagon = [(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i)))
           for i in range(6)]
hole = bpy.data.objects.new("ビット穴", prism_mesh("ビット穴", [
    (FLOOR, hexagon),
    (block_h + 2, hexagon),
]))
hole.location = ((width - (BIT_COLS - 1) * BIT_PITCH_X) / 2, BIT_MARGIN_Y, 0)
parts_col.objects.link(hole)
add_array(hole, "横に並べる", (BIT_PITCH_X, 0, 0), BIT_COLS)
add_array(hole, "縦に並べる", (0, BIT_PITCH_Y, 0), BIT_ROWS)
as_helper(hole)

add_boolean(body, "ソケット板を足す", plate, "UNION")
add_boolean(body, "ソケットピンを足す", pin, "UNION")
add_boolean(body, "ビット穴を抜く", hole, "DIFFERENCE")

# --- 説明をファイルに残す(Blender の Text Editor で読める) ---
note = bpy.data.texts.get("説明") or bpy.data.texts.new("説明")
note.from_string(f"""工具入れ(単位 mm)

最終形は「工具入れ」オブジェクト。モディファイアで次を順に適用している。
  1. ソケット板を足す   (Boolean 結合, 形状パーツ/ソケット板)
  2. ソケットピンを足す (Boolean 結合, 形状パーツ/ソケットピン)
  3. ビット穴を抜く     (Boolean 差分, 形状パーツ/ビット穴)

形状パーツはワイヤー表示・レンダリング対象外。形を変えるときはパーツ側を編集する。
  個数・間隔: ビット穴 / ソケットピン の Array モディファイア(横に並べる・縦に並べる)
  ビット穴の大きさ: ビット穴のメッシュ(対辺 {BIT_HEX_FLAT}, 深さ {BIT_DEPTH})
  ピンの太さ: ソケットピンのメッシュ(一辺 {PIN}, 高さ {PIN_HEIGHT})
  個数を増やしたら「工具入れ」(ビット台)と「ソケット板」の大きさも合わせて広げる。

今の設定: ビット {BIT_COLS}x{BIT_ROWS}(間隔 {BIT_PITCH_X}x{BIT_PITCH_Y}), ソケット {SOCK_COLS}x{SOCK_ROWS}(間隔 {SOCK_PITCH})
全体 {width} x {block_d + plate_d} mm, 高さ {block_h}(ビット部)/ {PLATE}+{PIN_HEIGHT}(ソケット部)

make_tool_holder.py で作り直せる。
""")

for o in bpy.context.view_layer.objects:
    o.select_set(o == body)
bpy.context.view_layer.objects.active = body

bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(OUT_BLEND) if OUT_BLEND.startswith("//") else OUT_BLEND)
bpy.ops.wm.stl_export(filepath=OUT_STL, export_selected_objects=True, apply_modifiers=True)

ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
print("RESULT", OUT_BLEND, "dims", tuple(round(d, 2) for d in ev.dimensions),
      "verts", len(ev.data.vertices), "faces", len(ev.data.polygons))
