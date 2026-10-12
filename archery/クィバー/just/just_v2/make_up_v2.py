"""up.blend から、矢の入り口を漏斗状にした up_v2.blend / up_v2.stl を作る。

使い方:
  blender -b up.blend --python make_up_v2.py

収納した矢は mid / bottom と同じ位置で垂直に通るので、穴の位置と直径 7mm は変えない。
各穴の上 ENTRY_DEPTH だけを、上面に向かって広げる。隣どうしの入り口は上面の少し下で
刃先状の稜線で交わり、上面に平らなところが残らない。揃えた矢先がどこに当たっても、
斜面を滑ってどれかの穴に入る。
"""
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

MM = 0.001

# 今の矢の穴(arrow.blend と同じ)
ARROW_Y = [-30.8, -22.4, -14.0, 0.0, 8.4, 16.8, 25.2, 33.6, 42.0]
HOLE_R = 3.5

# 入り口
ENTRY_R = 4.6  # 上面での入り口の半幅(X 方向)。板の厚みは 16mm なので壁は 3.4mm
ENTRY_DEPTH = 15.0  # 上面から、穴が直径 7mm に戻るまでの深さ
OVERLAP = 0.4  # 隣の入り口と重ねる量。稜線が上面より少し下に来る

SEGMENTS = 48

here = os.path.dirname(bpy.data.filepath)
plate = bpy.data.objects["Cube"]
cutters = bpy.data.collections["Collection 1"]

# 板の上下面の高さ(ワールド座標)
zs = [(plate.matrix_world @ Vector(c)).z for c in plate.bound_box]
z_bot, z_top = min(zs), max(zs)


def ring(bm, y, r, z):
    bmesh.ops.create_circle(
        bm,
        segments=SEGMENTS,
        radius=r * MM,
        matrix=Matrix.Translation((0, y * MM, z)),
    )


for i, y in enumerate(ARROW_Y):
    # 入り口の Y 方向の範囲: 隣の穴との中間まで(両端の穴は外側に ENTRY_R)
    lo = (ARROW_Y[i - 1] + y) / 2 - OVERLAP if i > 0 else y - ENTRY_R
    hi = (y + ARROW_Y[i + 1]) / 2 + OVERLAP if i < len(ARROW_Y) - 1 else y + ENTRY_R
    # 円柱(全高)と、上の円錐を別々のカッターにする。1 つの凸包にすると全高がテーパーになる
    cyl = [(y, HOLE_R, z_bot - 1 * MM), (y, HOLE_R, z_top + 1 * MM)]
    # 上面をきれいに抜くため、上に少しはみ出させる
    cone = [(y, HOLE_R, z_top - ENTRY_DEPTH * MM)] + [
        (yc, ENTRY_R, z) for z in (z_top, z_top + 1 * MM) for yc in (lo + ENTRY_R, hi - ENTRY_R)
    ]
    for name, rings in ((f"hole.{i}", cyl), (f"funnel.{i}", cone)):
        bm = bmesh.new()
        for args in rings:
            ring(bm, *args)
        ret = bmesh.ops.convex_hull(bm, input=bm.verts)
        bmesh.ops.delete(bm, geom=ret["geom_interior"] + ret["geom_unused"], context="VERTS")
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001 * MM)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        cutters.objects.link(ob)
        ob.hide_set(True)
        ob.hide_render = True
    print(f"funnel {i}: y={y:.2f} entry {lo:.2f}..{hi:.2f}")

# まっすぐの矢の穴は Boolean の対象から外し、参照用に残す
arrow = bpy.data.objects["arrow.001"]
ref = bpy.data.collections.new("ref")
bpy.context.scene.collection.children.link(ref)
ref.objects.link(arrow)
cutters.objects.unlink(arrow)
# 矢の円柱にはフレーム棒の穴も入っているので、棒の 2 本だけ切り出して Boolean に残す
rods = arrow.copy()
rods.data = arrow.data.copy()
rods.name = rods.data.name = "rods"
bm = bmesh.new()
bm.from_mesh(rods.data)
# 矢は z=0.35 まで、棒は z=0.23 まで。z=0.231 より上に届く島は矢なので消す
bm.verts.ensure_lookup_table()
seen = set()
to_delete = []
for v in bm.verts:
    if v.index in seen:
        continue
    stack, comp = [v], []
    seen.add(v.index)
    while stack:
        x = stack.pop()
        comp.append(x)
        for e in x.link_edges:
            o = e.other_vert(x)
            if o.index not in seen:
                seen.add(o.index)
                stack.append(o)
    if max(p.co.z for p in comp) > 0.231:
        to_delete += comp
bmesh.ops.delete(bm, geom=to_delete, context="VERTS")
bm.to_mesh(rods.data)
bm.free()
cutters.objects.link(rods)
rods.hide_set(True)
rods.hide_render = True

out_blend = os.path.join(here, "up_v2.blend")
bpy.ops.wm.save_as_mainfile(filepath=out_blend, copy=True)

for o in bpy.context.view_layer.objects:
    o.select_set(o is plate)
bpy.context.view_layer.objects.active = plate
bpy.ops.wm.stl_export(
    filepath=os.path.join(here, "up_v2.stl"),
    export_selected_objects=True,
    apply_modifiers=True,
)
