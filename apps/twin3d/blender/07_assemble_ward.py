"""Step 7: assemble the whole ward from seed/ward-W1.yaml: rooms, corridor, station, props, patients.

Run after steps 1-6:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/07_assemble_ward.py")

What it builds, in the collection "Ward" (the only thing step 8 exports besides the staff):

1. A ROOM TEMPLATE in room B's own coordinates. Everything static in the room (about 400 objects:
   beds, curtains, cabinets, kits, lamps, walls...) is merged into one mesh per material, so a room
   costs ~20 draw calls instead of ~400, and the heavy parts are slimmed first. Kept as separate
   nodes because the web app drives them: `screen_bedN` (monitor), `calllight_bedN`, the door call
   light, the three cut-away shell pieces, and a lying `patient_bedN`.
2. Six rooms: linked copies of the template (the mesh data is shared, so the file does not grow),
   placed with the seed's x measured at the DOOR and turned so the door faces the corridor.
   North rooms (seed y > 0) are turned 180 degrees. Beds get the seed ids (R1 -> B01, B02 ...).
3. The corridor (2.4 m wide) with a bay on its south side for the station, walls only where a
   room is not, handrails, ceiling light panels, and cut-away tags on every ceiling and shell wall
   (`twin_cutaway` = outward normal, so the web view hides what faces the camera).
4. The station, TV, a crash cart and a wheelchair from step 5, placed.
5. `patient_<bed>`: the nurse mesh posed (idle) and laid on its back on each mattress in a gown,
   slimmed. The web app shows it only while a bed has an admission.
6. A layout record (`scene["twin_layout"]`, written to JSON by step 8): every anchor the app needs
   (doors, bedsides, seats, waypoints, TV), already in three.js axes (x, up, -y_blender).

Re-running is safe. Needs the seed file in the repo and the objects made by steps 1-6.
"""
import importlib
import json
import math
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

importlib.reload(common)   # a long-lived Blender session may hold an older copy

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SEED = os.path.join(REPO, "seed", "ward-W1.yaml")
WARD, TEMPLATE = "Ward", "Room_template"
HALF = 1.2                  # half the corridor width (m)
HALL = (-3.5, 3.5, -4.5, -1.2)      # x0, x1, y0, y1 of the bay south of the corridor that holds the station
ENDS = (-15.6, 15.6)        # corridor ends (x)
WALL_T = 0.10
RAIL_Z, RAIL_T = 0.90, 0.05
STATION_AT = Vector((0.0, -2.9, 0.0))
SIT_HIPS = 0.63             # hip height in the sit clips (measured in step 6)
LAMP_SCALE = 0.75
PATIENT_PARTS = {"nurse_body": 2000, "nurse_eyes": 200, "nurse_eyelashes": 100, "nurse_top": 700,
                 "nurse_bottom": 700, "nurse_hair": 900, "nurse_hat": 400}
GOWN = (0.55, 0.72, 0.85)
YAML_ROOM = re.compile(r"\{\s*id:\s*(R\d+),\s*x:\s*(-?[\d.]+),\s*y:\s*(-?[\d.]+),\s*beds:\s*\[([^\]]*)\]")
YAML_STAFF = re.compile(r"id:\s*(\w+),\s*name:\s*\"([^\"]*)\",\s*role:\s*(\w+)")


def read_seed():
    text = open(SEED, encoding="utf-8").read()
    rooms = [dict(id=m[1], x=float(m[2]), y=float(m[3]), beds=[b.strip() for b in m[4].split(",")])
             for m in YAML_ROOM.finditer(text)]
    staff = [dict(id=m[1], name=m[2], role=m[3]) for m in YAML_STAFF.finditer(text)]
    return rooms, staff


def three(v):
    """Blender (x, y, z up) -> three.js / glTF (x, y up, z)."""
    return [round(v.x, 3), round(v.z, 3), round(-v.y, 3)]


def mat(name):
    return bpy.data.materials[name]


# ------------------------------------------------------------------- merging pieces
class Pieces:
    """Meshes already in their final coordinates, grouped by material, merged on request."""

    def __init__(self):
        self.groups = {}

    def add_mesh(self, mesh, material):
        self.groups.setdefault(material.name, []).append(mesh)

    def add_object(self, o, matrix=None, budget=None):
        """A copy of `o`'s mesh in world space (or `matrix @ o.matrix_world`), optionally slimmed."""
        src = o
        if budget is not None and len(o.data.polygons) > budget:
            src = o.copy()                       # slim a duplicate: the original keeps its mesh
            bpy.context.scene.collection.objects.link(src)
            common.decimated(src, budget)
        me = src.data.copy()
        me.transform(matrix if matrix is not None else o.matrix_world)
        if src is not o:
            bpy.data.objects.remove(src, do_unlink=True)
        material = o.active_material or mat("paint_white")
        self.add_mesh(me, material)

    def merge(self, prefix, coll, parent=None):
        out = []
        for name, meshes in self.groups.items():
            bm = bmesh.new()
            for me in meshes:
                single_uv(me)
                bm.from_mesh(me)
                bpy.data.meshes.remove(me)
            mesh = bpy.data.meshes.new(f"{prefix}_{name}")
            bm.to_mesh(mesh)
            bm.free()
            mesh.materials.append(mat(name))
            obj = bpy.data.objects.new(f"{prefix}_{name}", mesh)
            obj["twin_assembly"] = True
            coll.objects.link(obj)
            if parent is not None:
                obj.parent = parent
            out.append(obj)
        return out


def single_uv(me):
    """One UV layer named UV0 (the merge needs every piece to have the same layers)."""
    src = me.uv_layers.active
    if src is None:
        me.uv_layers.new(name="UV0")
        return
    arr = np.empty(len(src.data) * 2, dtype=np.float32)
    src.data.foreach_get("uv", arr)
    for layer in list(me.uv_layers):
        me.uv_layers.remove(layer)
    new = me.uv_layers.new(name="UV0")
    new.data.foreach_set("uv", arr)


def box_object(name, lo, hi, material, tile=None):
    """A temporary axis-aligned box object (world metres) with world-metre UVs when `tile` is set."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (lo + hi) / 2
    obj.scale = hi - lo
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    mesh.materials.append(material)
    if tile:
        common.world_box_uv(obj, tile)
    return obj


# ------------------------------------------------------------------ the patient
def tinted_copy(name, source, colour):
    """A copy of a recolourable nurse material with its own tint."""
    m = bpy.data.materials.get(name) or mat(source).copy()
    m.name = name
    node = m.node_tree.nodes[m["tint_node"]]
    [s for s in node.inputs if s.type == "RGBA"][1].default_value = (*colour, 1)
    return m


def build_patient(bed_root, mattress_top, coll):
    """The nurse mesh, idle pose, laid on its back on the mattress, in a gown. A static mesh."""
    arm = bpy.data.objects["nurse_rig"]
    arm.animation_data.action = bpy.data.actions["idle"]
    bpy.context.scene.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    # local axes -> world: head toward -x (bed head), face up (+z), body's right toward +y
    lie = Matrix(((0, 0, -1, 0), (1, 0, 0, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
    meshes = {}
    for name, budget in PATIENT_PARTS.items():
        o = bpy.data.objects[name]
        me = bpy.data.meshes.new_from_object(o.evaluated_get(deps), depsgraph=deps)
        me.transform(lie @ o.matrix_world)
        meshes[name] = (me, budget, o.active_material)
    lo = Vector(min(v.co[i] for me, _, _ in meshes.values() for v in me.vertices) for i in range(3))
    hi = Vector(max(v.co[i] for me, _, _ in meshes.values() for v in me.vertices) for i in range(3))
    b_lo, b_hi = common.world_bbox(common.subtree(bed_root))
    shift = Vector((b_lo.x + 0.18 - lo.x, (b_lo.y + b_hi.y) / 2 - (lo.y + hi.y) / 2, mattress_top - lo.z))
    root = bpy.data.objects.new("patient_tpl", None)
    coll.objects.link(root)
    gown = tinted_copy("patient_gown", "nurse_top", GOWN)
    cap = tinted_copy("patient_cap", "nurse_hat", (0.85, 0.88, 0.90))
    for name, (me, budget, material) in meshes.items():
        me.transform(Matrix.Translation(shift))
        obj = bpy.data.objects.new(name.replace("nurse_", "patient_"), me)
        coll.objects.link(obj)
        common.decimated(obj, budget)
        obj.data.materials.clear()
        obj.data.materials.append(
            gown if name in ("nurse_top", "nurse_bottom") else cap if name == "nurse_hat" else material)
        obj.parent = root
        obj["twin_assembly"] = True
    return root


# --------------------------------------------------------------------------- run
def remove_previous_run():
    for o in list(bpy.data.objects):
        if o.get("twin_assembly") or o.name.startswith(("tpl_", "patient_tpl")):
            bpy.data.objects.remove(o, do_unlink=True)


remove_previous_run()
bpy.context.view_layer.update()
start = common.snapshot()
rooms, staff_seed = read_seed()
assert len(rooms) == 6, "expected 6 rooms in the seed"
ward = common.get_collection(WARD)
tcoll = common.get_collection(TEMPLATE)
view = set(bpy.context.view_layer.objects)

# 1. ROOM TEMPLATE ------------------------------------------------------------------------------
tpl = bpy.data.objects.new("tpl_room", None)
tpl["twin_assembly"] = True
tcoll.objects.link(tpl)
room_roots = [bpy.data.objects[n] for n in ("Hospital", "kit:bed:All_bed", "kit:bed2:All_bed")]
pieces = Pieces()
screens = {}
for r in room_roots:
    for o in common.subtree(r):
        if o.type != "MESH" or o not in view:
            continue
        if o.name.startswith("screen_monitor"):
            screens[r.name, o.name] = o
            continue
        pieces.add_object(o, budget=common.poly_budget(o, per_metre=900, lo=12, hi=350))

bed_roots = [bpy.data.objects["bed:All_bed"], bpy.data.objects["bed2:All_bed"]]
b_lo, b_hi = common.world_bbox([o for o in common.subtree(bed_roots[0]) if o.type == "MESH"])
wall_inner_x = common.world_bbox([bpy.data.objects["wall2"]])[1].x
ceiling_z = common.world_bbox([bpy.data.objects["shell_ceiling"]])[0].z
floor_hi = common.world_bbox([bpy.data.objects["floor"]])[1].z
door_lo, door_hi = common.world_bbox(common.subtree(bpy.data.objects["doorAnd_win:DOOR.001"]))
wall_back_hi_y = common.world_bbox([bpy.data.objects["wall1"]])[1].y
door_x = (door_lo.x + door_hi.x) / 2

# ceiling light panels (two per room, hung from the ceiling plane)
lamp_root = bpy.data.objects["prop_ceiling_lamp"]
lamp = bpy.data.objects["lamp_panel"]
S = Matrix.Diagonal((*lamp_root.scale, 1.0))
for pos in (Vector((-0.9, -1.8, ceiling_z)), Vector((-0.9, 1.8, ceiling_z))):
    pieces.add_object(lamp, Matrix.Translation(pos) @ S @ lamp.matrix_basis)

# the monitor screens, the call lights, the shell, the patients
tpl_nodes = {}


def tpl_object(name, mesh, material=None, extra=None):
    o = bpy.data.objects.new(f"tpl_{name}", mesh)
    o["twin_assembly"] = True
    o["twin_id"] = name
    if material is not None:
        mesh.materials.append(material)
    for k, v in (extra or {}).items():
        o[k] = v
    tcoll.objects.link(o)
    o.parent = tpl
    tpl_nodes[name] = o
    return o


for i, kit_name in enumerate(("kit:bed:All_bed", "kit:bed2:All_bed"), start=1):
    sc = next(o for (k, _), o in screens.items() if k == kit_name)
    me = sc.data.copy()
    me.transform(sc.matrix_world)
    tpl_object(f"screen_bed{i}", me, mat("screen_off"))

call_mat = bpy.data.materials.get("call_light") or bpy.data.materials.new("call_light")
call_mat.use_nodes = True
bsdf = call_mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1)
bsdf.inputs["Emission Color"].default_value = (1.0, 0.25, 0.1, 1)
bsdf.inputs["Emission Strength"].default_value = 0.0      # off; the web app lights it per call


def call_light_mesh(centre, size):
    cube = bpy.data.meshes.new("calllight")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=centre, verts=bm.verts)
    bm.to_mesh(cube)
    bm.free()
    return cube


bed_ys, mattress_tops = [], []
for i, br in enumerate(bed_roots, start=1):
    lo, hi = common.world_bbox([o for o in common.subtree(br) if o.type == "MESH"])
    bed_ys.append((lo.y + hi.y) / 2)
    mats = [common.world_bbox([o])[1].z for o in common.subtree(br)
            if o.type == "MESH" and o.active_material and o.active_material.name == "mattress_vinyl"]
    mattress_tops.append(max(mats))
    tpl_object(f"calllight_bed{i}", call_light_mesh(Vector((wall_inner_x + 0.04, bed_ys[-1], 1.75)),
                                                    Vector((0.05, 0.16, 0.10))), call_mat)
tpl_object("calllight_door", call_light_mesh(Vector((door_x, wall_back_hi_y + 0.04, 2.30)), Vector((0.30, 0.05, 0.12))),
           call_mat)
for n in ("shell_wall_east", "shell_wall_south", "shell_ceiling"):
    src = bpy.data.objects[n]
    o = tpl_object(n, src.data.copy(), src.active_material)
    o.matrix_world = src.matrix_world
    o["twin_cutaway"] = True
    o["twin_normal"] = {"shell_wall_east": [1, 0, 0], "shell_wall_south": [0, -1, 0], "shell_ceiling": [0, 0, 1]}[n]
patient_tpl = []
for i, br in enumerate(bed_roots, start=1):
    p = build_patient(br, mattress_tops[i - 1], tcoll)
    p.name = f"tpl_patient_bed{i}"
    p["twin_id"] = f"patient_bed{i}"
    p["twin_assembly"] = True
    p.parent = tpl
    for c in p.children:
        c["twin_assembly"] = True
    patient_tpl.append(p)

merged = pieces.merge("tpl_room", tcoll, parent=tpl)
for o in merged:
    o["twin_id"] = o.name.replace("tpl_", "")
print("template:", sum(len(o.data.polygons) for o in merged), "polygons in", len(merged), "merged meshes")

# template anchors (template coordinates)
anchors = {
    "door": Vector((door_x, wall_back_hi_y, 0)),
    "via": [Vector((door_x, y - 0.7, 0)) for y in bed_ys],
    "bedside": [Vector(((b_lo.x + b_hi.x) / 2 - 0.2 + 0.0, y - 0.7, 0)) for y in bed_ys],
}

# 2. SIX ROOMS ------------------------------------------------------------------------------------
layout = {"version": 1, "unit": "m", "rooms": [], "staff": [], "station": {}, "corridor": {}}
for room in rooms:
    north = room["y"] > 0
    door_world = Vector((room["x"], HALF if north else -HALF, 0))
    turn = Matrix.Rotation(math.pi if north else 0.0, 4, "Z")
    M = Matrix.Translation(door_world) @ turn @ Matrix.Translation(-Vector((door_x, wall_back_hi_y, 0)))
    inst = common.linked_copy(tpl, f"room_{room['id']}", M, collection=ward)
    yaw_in = math.pi if north else 0.0          # facing into the room (a figure faces -Y at yaw 0)
    for o in common.subtree(inst):
        o["twin_assembly"] = True
        base = o.get("twin_id")
        if not base or o is inst:
            continue
        if base == "calllight_door":
            o.name = f"callLightDoor_{room['id']}"
        elif base.startswith("calllight_bed"):
            o.name = f"callLight_{room['beds'][int(base[-1]) - 1]}"
        elif base.startswith("screen_bed"):
            o.name = f"screen_{room['beds'][int(base[-1]) - 1]}"
        elif base.startswith("patient_bed"):
            o.name = f"patient_{room['beds'][int(base[-1]) - 1]}"
        else:
            o.name = f"{room['id']}_{base}"
        if o.get("twin_cutaway"):
            n = M.to_3x3() @ Vector(o["twin_normal"])
            o["twin_normal"] = [round(n.x, 3), round(n.z, 3), round(-n.y, 3)]
    entry = {"id": room["id"], "side": "north" if north else "south",
             "door": {"pos": three(door_world), "yaw": round(yaw_in, 4)}, "beds": []}
    for i, bed in enumerate(room["beds"]):
        entry["beds"].append({
            "id": bed,
            "bedside": {"pos": three(M @ anchors["bedside"][i]), "yaw": round(yaw_in + math.pi, 4)},   # faces the bed
            "via": three(M @ anchors["via"][i]),
        })
    layout["rooms"].append(entry)

# room footprints along the corridor (x ranges), for the corridor walls
footprints = {"north": [], "south": []}
rl, rh = common.world_bbox([o for o in common.subtree(bpy.data.objects["Hospital"]) if o.type == "MESH" and o in view])
for room in rooms:
    north = room["y"] > 0
    x_lo = room["x"] - (rh.x - door_x if north else door_x - rl.x)
    x_hi = room["x"] + (door_x - rl.x if north else rh.x - door_x)
    footprints["north" if north else "south"].append((min(x_lo, x_hi), max(x_lo, x_hi)))

# 3. CORRIDOR -------------------------------------------------------------------------------------
cpieces = Pieces()
floor_m, wall_m, ceil_m, rail_m, cutaway = mat("floor_vinyl"), mat("wall_paint"), mat("ceiling_tile"), mat("chrome"), []
H = ceiling_z


def add_box(name, lo, hi, material, tile=None, cut=None):
    """A box of the corridor. With `cut` (outward normal, Blender axes) it stays a separate node tagged
    twin_cutaway, so the web view can hide it when it faces the camera; otherwise it is merged."""
    o = box_object(name, Vector(lo), Vector(hi), material, tile)
    if cut is None:
        cpieces.add_object(o)
        bpy.data.objects.remove(o, do_unlink=True)
        return
    o["twin_assembly"] = o["twin_cutaway"] = True
    o["twin_normal"] = [cut[0], cut[2], -cut[1]]
    for c in list(o.users_collection):
        c.objects.unlink(o)
    ward.objects.link(o)


add_box("corr_floor", (ENDS[0], -HALF, -0.04), (ENDS[1], HALF, 0.0), floor_m, 2.4)
add_box("bay_floor", (HALL[0], HALL[2], -0.04), (HALL[1], HALL[3], 0.0), floor_m, 2.4)
for sign, key in ((1, "north"), (-1, "south")):
    covered = sorted(footprints[key])
    if key == "south":
        covered.append((HALL[0], HALL[1]))               # the bay opens the south wall
    covered.sort()
    x = ENDS[0]
    gaps = []
    for lo, hi in covered:
        if lo > x + 0.05:
            gaps.append((x, lo))
        x = max(x, hi)
    if x < ENDS[1] - 0.05:
        gaps.append((x, ENDS[1]))
    for lo, hi in gaps:
        y0, y1 = (HALF, HALF + WALL_T) if sign > 0 else (-HALF - WALL_T, -HALF)
        add_box(f"corr_wall_{key}", (lo, y0, 0), (hi, y1, H), wall_m, 2.0, cut=(0, sign, 0))
    for lo, hi in gaps + footprints[key]:                               # handrails along every wall
        yy = sign * (HALF - RAIL_T / 2 - 0.03)
        add_box("rail", (lo, yy - RAIL_T / 2, RAIL_Z), (hi, yy + RAIL_T / 2, RAIL_Z + RAIL_T), rail_m)
for x in (ENDS[0], ENDS[1]):
    add_box("corr_end", (x - (WALL_T if x > 0 else 0), -HALF, 0), (x + (0 if x > 0 else WALL_T), HALF, H), wall_m, 2.0,
            cut=(1 if x > 0 else -1, 0, 0))
add_box("bay_wall_south", (HALL[0], HALL[2] - WALL_T, 0), (HALL[1], HALL[2], H), wall_m, 2.0, cut=(0, -1, 0))
add_box("bay_wall_west", (HALL[0] - WALL_T, HALL[2] - WALL_T, 0), (HALL[0], -HALF, H), wall_m, 2.0, cut=(-1, 0, 0))
add_box("bay_wall_east", (HALL[1], HALL[2] - WALL_T, 0), (HALL[1] + WALL_T, -HALF, H), wall_m, 2.0, cut=(1, 0, 0))
for x in np.arange(-13.5, 13.6, 3.0):                                   # ceiling light panels
    cpieces.add_object(lamp, Matrix.Translation(Vector((float(x), 0.0, H))) @ S @ lamp.matrix_basis)
for x, y in ((-2.0, -3.4), (2.0, -3.4), (0.0, -3.4)):
    cpieces.add_object(lamp, Matrix.Translation(Vector((x, y, H))) @ S @ lamp.matrix_basis)
corridor = cpieces.merge("corridor", ward)
for o in corridor:
    o["twin_id"] = o.name
for name, lo, hi in (("corr_ceiling", (ENDS[0], -HALF, H), (ENDS[1], HALF, H + WALL_T)),
                     ("bay_ceiling", (HALL[0], HALL[2], H), (HALL[1], HALL[3], H + WALL_T))):
    o = box_object(name, Vector(lo), Vector(hi), ceil_m, 1.2)
    o["twin_assembly"] = True
    o["twin_cutaway"] = True
    o["twin_normal"] = [0, 1, 0]
    for c in list(o.users_collection):
        c.objects.unlink(o)
    ward.objects.link(o)

# 4. STATION, TV, PROPS ----------------------------------------------------------------------------
station = bpy.data.objects["station_root"]
station.location = STATION_AT
tv = bpy.data.objects["tv_station"]
tv.location = Vector((HALL[0] + 0.07, STATION_AT.y, 1.6))        # on the bay's west wall, facing +x (into the bay)
tv.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()
for root in (station, tv):
    for o in common.subtree(root):
        if o.name not in ward.objects:
            ward.objects.link(o)
        o["twin_assembly"] = True
for src, name, pos, yaw in ((bpy.data.objects["prop_cart"], "crash_cart", Vector((4.2, 0.85, 0)), math.pi / 2),
                            (bpy.data.objects["prop_wheelchair"], "wheelchair", Vector((-4.6, -0.8, 0)), 0.0)):
    pose = Matrix.Translation(pos) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Diagonal((*src.scale, 1.0))
    c = common.linked_copy(src, name, pose, collection=ward)
    for o in common.subtree(c):
        o["twin_assembly"] = True

# seats and the layout of the station
parts = common.loose_parts(bpy.data.objects["station_chairs"])
seats = []
for p in parts:
    lo, hi = common.world_bbox([p])
    if len(p.data.polygons) == 160 and hi.z - lo.z < 0.25 and lo.z > 0.6:
        seats.append(((lo + hi) / 2, hi.z))
for p in parts:
    bpy.data.objects.remove(p, do_unlink=True)
seats.sort(key=lambda s: s[0].x)
desk_c = common.world_bbox([bpy.data.objects["station_desk"]])
desk_centre = (desk_c[0] + desk_c[1]) / 2
SOUTH = -4.0                 # staff leave the station along this y, around the arms of the counter
layout["station"] = {
    "pos": three(STATION_AT),
    "seats": [{"pos": three(Vector((s.x, s.y, 0))), "lift": round(top - SIT_HIPS + 0.08, 3),
               "yaw": round(math.atan2(-(desk_centre.x - s.x), desk_centre.y - s.y) + math.pi, 4)} for s, top in seats],
    # clear of the three chairs (which sit at about x -1.4, -0.1 and 1.4): behind the middle one and at the arm ends
    "standing": [{"pos": three(Vector((0.0, SOUTH + 0.1, 0))), "yaw": math.pi},
                 {"pos": three(Vector((-2.6, SOUTH + 0.3, 0))), "yaw": math.pi},
                 {"pos": three(Vector((2.6, SOUTH + 0.3, 0))), "yaw": math.pi}],
    "exit": three(Vector((0.0, SOUTH, 0))),
}
layout["tv"] = {"pos": three(tv.matrix_world.translation), "facing": three(Vector((1, 0, 0)))}
layout["corridor"] = {"y": 0.0, "x": [ENDS[0], ENDS[1]], "bay": list(HALL), "walkY": 0.3,
                      "hall": {"southZ": -SOUTH, "westX": HALL[0] + 0.3, "eastX": HALL[1] - 0.3}}
layout["staff"] = [{"id": s["id"], "name": s["name"], "role": s["role"]} for s in staff_seed]
nurses = [s["id"] for s in staff_seed if s["role"] == "nurse"]
layout["home"] = {sid: {"kind": "seat", "index": i} for i, sid in enumerate(nurses)}
for i, sid in enumerate(s["id"] for s in staff_seed if s["role"] != "nurse"):
    layout["home"][sid] = {"kind": "stand", "index": i}
scene = bpy.context.scene
scene["twin_layout"] = json.dumps(layout)

# the template and everything it was built from stay out of the export
common.get_collection(TEMPLATE, exclude=True)
common.purge_new(start)
bpy.context.view_layer.update()
polys = sum(len(o.data.polygons) for o in ward.all_objects if o.type == "MESH")
print(f"ward: {len(ward.all_objects)} objects, {polys} polygons (shared meshes counted once per node)")
