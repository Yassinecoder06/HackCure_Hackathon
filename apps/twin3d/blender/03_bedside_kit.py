"""Step 3: take the machines Room B lacks from Room A and put a set beside each bed.

Run after steps 1-2:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/03_bedside_kit.py")

Room A ("Sketchfab_model") is a one-bed room with a bedside monitor cart, an IV pole and a
headwall unit. Room B ("Hospital") has no monitor at all, and the twin needs one per bed.
This script COPIES those parts (Room A is not modified) into a "kit" in the frame of the
bed head, then places one kit beside each Room B bed.

Three details worth knowing:
- Room A's cart is ~200 000 triangles (a cylinder with 100 000). Each copied mesh is
  decimated to a budget that grows with its size (see poly_budget); the copy gets its
  own mesh, the original is untouched.
- The live data has to be shown on a separate mesh, so we build a flat `screen_monitor`
  quad on the real front face of the monitor body (largest group of faces sharing a
  normal), inset a little so the bezel stays. The web app swaps its texture.
- Room A has its bed head on +x, Room B on -x, so the kit is turned 180 degrees about Z.
"""
import collections
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

ROOM_A = "Sketchfab_model"
HEADBOARD_A = "Cube.231__0"      # head of Room A's bed: defines the kit origin
MONITOR_BODY_A = "Cube.248__0"   # the tilted display body on the cart
MAX_POLYS = 3000
SCREEN_INSET = 0.10              # fraction of the front face left as bezel on each side
KIT = "Bedside_kit_source"
BED_ROOTS = ["bed:All_bed", "bed2:All_bed"]

# Where each machine stands in Room A (world metres; centre of each mesh's bounding box).
GROUPS = {
    "bedside_monitor": dict(x=(0.9, 1.4), y=(31.6, 32.2), zmax=1.6),
    "iv_pole": dict(x=(1.4, 1.95), y=(31.55, 32.25)),
    # skip the bed's own headboard pieces and the long wall panels
    "headwall_unit": dict(x=(1.65, 1.95), y=(32.4, 33.4), zmin=0.5, maxdim=1.5,
                          skip=("Cube.231__0", "Cylinder.336__0")),
}


def in_group(centre, size, name, g):
    if not (g["x"][0] <= centre.x <= g["x"][1] and g["y"][0] <= centre.y <= g["y"][1]):
        return False
    if centre.z >= g.get("zmax", 99) or centre.z < g.get("zmin", -99):
        return False
    if max(size) > g.get("maxdim", 99) or name in g.get("skip", ()):
        return False
    return True


def poly_budget(obj):
    """Triangles a part deserves: small parts (buttons, fittings) get few, big ones up to MAX_POLYS."""
    lo, hi = common.world_bbox([obj])          # world metres (obj.dimensions ignores parent scale)
    return min(MAX_POLYS, max(150, int(8000 * max(hi - lo))))


def decimated(obj):
    """Give `obj` its own, lighter mesh (original mesh data is left alone)."""
    n = len(obj.data.polygons)
    budget = poly_budget(obj)
    if n <= budget:
        return
    # Weld duplicated vertices first: the FBX import left many unwelded, which stops the
    # collapse from reaching its target.
    mesh = obj.data.copy()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(mesh)
    bm.free()
    obj.data = mesh
    mod = obj.modifiers.new("decimate", "DECIMATE")
    mod.ratio = budget / n
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    obj.data = bpy.data.meshes.new_from_object(evaluated)
    obj.modifiers.remove(mod)


def screen_quad(src, to_kit, parent, collection):
    """A flat quad on the largest flat face of `src` (the monitor's display)."""
    nm = src.matrix_world.to_3x3()
    area = collections.defaultdict(float)
    faces = collections.defaultdict(list)
    for p in src.data.polygons:
        n = (nm @ p.normal).normalized()
        key = tuple(round(v, 1) for v in n)
        area[key] += p.area
        faces[key].append(p)
    key = max(area, key=area.get)
    pts = [src.matrix_world @ src.data.vertices[i].co for p in faces[key] for i in p.vertices]
    n = Vector(key).normalized()
    right = Vector((0, 0, 1)).cross(n).normalized()   # as seen by someone facing the screen
    up = n.cross(right)
    s = [v.dot(right) for v in pts]
    t = [v.dot(up) for v in pts]
    d = sum(v.dot(n) for v in pts) / len(pts) + 0.002  # 2 mm in front, avoids z-fighting
    ds, dt = (max(s) - min(s)) * SCREEN_INSET, (max(t) - min(t)) * SCREEN_INSET
    s0, s1, t0, t1 = min(s) + ds, max(s) - ds, min(t) + dt, max(t) - dt
    corners = [right * a + up * b + n * d for a, b in ((s0, t0), (s1, t0), (s1, t1), (s0, t1))]
    mesh = bpy.data.meshes.new("screen_monitor")
    mesh.from_pydata([to_kit @ c for c in corners], [], [(0, 1, 2, 3)])
    mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    obj = bpy.data.objects.new("screen_monitor", mesh)
    obj["twin_role"] = "bed_monitor_screen"
    collection.objects.link(obj)
    obj.parent = parent
    return obj


def remove_previous_run():
    """Re-running is safe: delete only what an earlier run of this script created."""
    doomed = []
    for name in ["kit_bedside"] + [f"kit:{b}" for b in BED_ROOTS]:
        if name in bpy.data.objects:
            doomed += common.subtree(bpy.data.objects[name])
    meshes = {o.data for o in doomed if o.type == "MESH"}
    for o in doomed:
        bpy.data.objects.remove(o, do_unlink=True)
    if KIT in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections[KIT])
    for m in meshes:
        if m.users == 0:
            bpy.data.meshes.remove(m)


# ---------------------------------------------------------------- build the kit
remove_previous_run()
bpy.context.view_layer.update()
kit_coll = common.get_collection(KIT)
room_a = bpy.data.objects[ROOM_A]

head_lo, head_hi = common.world_bbox([bpy.data.objects[HEADBOARD_A]])
origin_a = Vector((head_hi.x, (head_lo.y + head_hi.y) / 2, 0.0))   # bed head, on the floor
to_kit = Matrix.Translation(-origin_a)

kit_root = bpy.data.objects.new("kit_bedside", None)
kit_coll.objects.link(kit_root)
group_empties = {}
for name in GROUPS:
    e = bpy.data.objects.new(name, None)
    e.parent = kit_root
    kit_coll.objects.link(e)
    group_empties[name] = e

taken = set()
for o in common.subtree(room_a):
    if o.type != "MESH" or o.matrix_world.translation.y < 20:   # skip stray far-away objects
        continue
    lo, hi = common.world_bbox([o])
    for name, g in GROUPS.items():
        if o.name not in taken and in_group((lo + hi) / 2, hi - lo, o.name, g):
            c = o.copy()                       # linked mesh; decimated below if heavy
            c.parent = None
            kit_coll.objects.link(c)
            c.parent = group_empties[name]
            c.matrix_world = to_kit @ o.matrix_world
            decimated(c)
            if c.data.users > 1:
                c.data = c.data.copy()     # own mesh: later material changes never touch Room A
            taken.add(o.name)

body = bpy.data.objects[MONITOR_BODY_A]
screen = screen_quad(body, to_kit, group_empties["bedside_monitor"], kit_coll)
bpy.context.view_layer.update()

# ------------------------------------------------- place one kit beside each Room B bed
floor_top = common.world_bbox([bpy.data.objects["floor"]])[1].z
wall_inner_x = common.world_bbox([bpy.data.objects["wall2"]])[1].x
wall_gap_a = 1.94 - origin_a.x       # Room A: bed head to wall
visible = bpy.data.collections["Collection"]
for bed_name in BED_ROOTS:
    lo, hi = common.world_bbox(common.subtree(bpy.data.objects[bed_name]))
    head = Vector((lo.x, (lo.y + hi.y) / 2, floor_top))      # bed head is on the -x side
    place = Matrix.Translation(head) @ Matrix.Rotation(math.pi, 4, "Z")
    inst = common.linked_copy(kit_root, f"kit:{bed_name}", place, collection=visible)
    # the headwall unit sits on the wall, not on the bed: close the gap difference
    for c in inst.children:
        if c.name.startswith("headwall_unit"):
            c.location.x += (lo.x - wall_inner_x) - wall_gap_a

common.get_collection(KIT, exclude=True)    # keep the source kit, hidden

# Make room for the new equipment (each nudge runs once, then the object is flagged).
NUDGES = {
    "sofa:sofa.001": Vector((0.5, 0, 0)),                    # armchair was against bed 1's monitor cart
    "Hospital_screen_with_curtain1": Vector((0, 0.5, 0)),    # curtain stood 0.2 m from bed 2's side
}
for name, offset in NUDGES.items():
    o = bpy.data.objects[name]
    if not o.get("borj_nudged"):
        o.matrix_world = Matrix.Translation(offset) @ o.matrix_world
        o["borj_nudged"] = True
bpy.context.view_layer.update()
