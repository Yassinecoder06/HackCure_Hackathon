"""Step 2: a second, identical bed, and the walls and ceiling the room was missing.

Run after step 1:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/02_second_bed_and_shell.py")

Why:
- Every room in seed/ward-W1.yaml has exactly two beds (B01+B02, B03+B04, ...). The
  room had one real bed and one stretcher with a covered figure (archived in step 1).
  A linked copy of the real bed (same mesh data: no extra memory or file size) goes
  where the stretcher was, between the two curtain screens.
- The room only had a floor, a back wall (with the door) and a left wall. The east wall,
  south wall and ceiling are new boxes. They are separate objects tagged `twin_cutaway`
  so the web view can hide the ones facing the camera (doll-house view) instead of the
  walls blocking the beds.
"""
import importlib
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

importlib.reload(common)   # a long-lived Blender session may hold an older copy

BED = "bed:All_bed"
BED2 = "bed2:All_bed"
BED2_OFFSET_Y = 3.04    # metres from the first bed to where the old stretcher stood
WALL_T = 0.10           # thickness of the new walls, metres
SHELL = "Room_shell"


def box(name, lo, hi, collection):
    """An axis-aligned box from corner `lo` to corner `hi` (world metres)."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (lo + hi) / 2
    obj.scale = hi - lo
    obj["twin_cutaway"] = True
    collection.objects.link(obj)
    return obj


bpy.context.view_layer.update()
if BED2 in bpy.data.objects:
    raise RuntimeError("Step 2 already ran on this scene")

# 1. Second bed.
src = bpy.data.objects[BED]
common.linked_copy(src, BED2, Matrix.Translation(Vector((0, BED2_OFFSET_Y, 0))) @ src.matrix_world)

# The trolley that stood beside the old (shorter) stretcher would now overlap the foot
# of the bed, so it moves 0.7 m toward the foot end (+x).
trolley = bpy.data.objects["Trolley"]
trolley.matrix_world = Matrix.Translation(Vector((0.7, 0, 0))) @ trolley.matrix_world

# 2. Missing shell. Measure the room from the parts that exist.
floor_lo, floor_hi = common.world_bbox([bpy.data.objects["floor"]])
left_lo, left_hi = common.world_bbox([bpy.data.objects["wall2"]])
back_lo, back_hi = common.world_bbox([bpy.data.objects["wall1"]])
x0, x1 = left_lo.x, floor_hi.x
y0, y1 = floor_lo.y, back_hi.y
height = left_hi.z

coll = common.get_collection(SHELL)
box("shell_wall_east", Vector((x1, y0 - WALL_T, 0)), Vector((x1 + WALL_T, y1, height)), coll)
box("shell_wall_south", Vector((x0, y0 - WALL_T, 0)), Vector((x1 + WALL_T, y0, height)), coll)
box("shell_ceiling", Vector((x0, y0 - WALL_T, height)), Vector((x1 + WALL_T, y1, height + WALL_T)), coll)
bpy.context.view_layer.update()
