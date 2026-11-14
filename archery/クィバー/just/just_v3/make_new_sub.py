"""up.blend の new_sub を、6 本の矢を扇形に振り分ける直方体の切込みに作り直し、
別ファイルの up_slot.blend に保存する。up.blend は書き換えない。

使い方:
  blender -b up.blend --python make_new_sub.py

束ねた 6 本の矢を FOCUS(-X 側の外)に当て、そこから扇形に開いた切込みに沿わせて、
それぞれの穴に入れる。切込みは穴の中心線(x=0)から -X 側の面の外まで通し、
幅は穴と同じ 7mm、深さは body の上面から DEPTH。
各切込みの中心線は、穴の中心と FOCUS を結ぶ直線にする。
"""
import os

import bmesh
import bpy
from mathutils import Vector

MM = 0.001

# 束で通す 6 本の穴(arrow.blend と同じ。x=0)
ARROW_Y = [0.0, 8.4, 16.8, 25.2, 33.6, 42.0]
SLOT_W = 7.0  # 切込みの幅。穴の直径と同じ
DEPTH = 20.0  # body の上面からの深さ
FOCUS = (-60.0, 21.0)  # 切込みの中心線が集まる点 (x, y)。-X 側の外
OVERSHOOT = 2.0  # 面をきれいに抜くため、-X の面と上面からはみ出させる量

body = bpy.data.objects["body"]
coll = bpy.data.collections["new_sub"]

bb = [body.matrix_world @ Vector(c) for c in body.bound_box]
x_min = min(p.x for p in bb)
z_top = max(p.z for p in bb)
z_lo = z_top - DEPTH * MM
z_hi = z_top + OVERSHOOT * MM
x_out = x_min - OVERSHOOT * MM

for o in list(coll.objects):
    me = o.data
    bpy.data.objects.remove(o)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)

focus = Vector((FOCUS[0] * MM, FOCUS[1] * MM))
half = SLOT_W / 2 * MM

for i, y in enumerate(ARROW_Y):
    p0 = Vector((0.0, y * MM))
    d = (focus - p0).normalized()
    p1 = p0 + d * ((x_out - p0.x) / d.x)
    n = Vector((-d.y, d.x)) * half
    quad = [p0 - n, p1 - n, p1 + n, p0 + n]

    bm = bmesh.new()
    lo = [bm.verts.new((q.x, q.y, z_lo)) for q in quad]
    hi = [bm.verts.new((q.x, q.y, z_hi)) for q in quad]
    bm.faces.new(lo)
    bm.faces.new(hi)
    for k in range(4):
        j = (k + 1) % 4
        bm.faces.new((lo[k], lo[j], hi[j], hi[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    name = f"slot.{i}"
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.display_type = "WIRE"
    ob.hide_render = True

    ang = d.angle_signed(Vector((-1.0, 0.0)))
    print(f"{name}: y={y:.2f} angle={-ang * 57.29578:+.2f}deg")

out = os.path.join(os.path.dirname(bpy.data.filepath), "up_slot.blend")
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
print(f"saved {out}")
