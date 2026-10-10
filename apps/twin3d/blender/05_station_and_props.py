"""Step 5: a compact ward nurse station and the props, from the packs in borj-assets/models.

Run after steps 1-4:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/05_station_and_props.py")

What came in: "hospital-reception-environment" is a 12 x 9 m lobby (curved desk under a huge
overhead canopy with lettering, two rows of waiting chairs, magazine racks, signs, wall rails,
two TVs, a wheelchair). That reads as a hospital reception, not a ward nurse station, so only
the useful parts are kept and everything else is deleted from the import (the pack on disk is
untouched):
    kept:    the 3-workstation counter, 3 monitors, 3 office chairs, one wall TV, the wheelchair
    dropped: canopy and its letters, waiting chairs, magazine racks, direction/wet-floor signs,
             wall rails, walls, floor (our own corridor and rails come later)
Also built from the other downloads: a crash cart (412k triangles in the file, cut to ~15k),
one ceiling light panel, and a keyboard (47k triangles, cut to ~3k) placed in front of each of
the three monitors, which had none.

Every asset gets its own root empty and its parts sit inside it, so step 6 places, turns or
scales an asset by moving just the root. Conventions: station staff side (chairs) is local -Y
and the public counter faces +Y; the TV's front is local +X; the wheelchair, cart and lamp
roots are at floor level (the lamp at its top face, so it hangs from the ceiling plane).
Everything is parked in a review row near (14, 0) until step 6. Re-running is safe.
"""
import importlib
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

importlib.reload(common)   # a long-lived Blender session may hold an older copy

ASSETS = os.environ.get("BORJ_ASSETS", os.path.join(os.path.expanduser("~"), "Desktop", "borj-assets"))
MODELS = os.path.join(ASSETS, "models")
RECEPTION_FBX = os.path.join(MODELS, "reception", "source", "Environment Export.fbx")
RECEPTION_TEX = os.path.join(MODELS, "reception", "textures")
CART_USDZ = os.path.join(MODELS, "emergency_cart", "Emergency_Cart.usdz")
LAMP_GLB = os.path.join(MODELS, "ceiling_lamp", "source", "Fluorescent_lamps.glb")
KEYBOARD_GLB = os.path.join(MODELS, "keyboard", "keyboard.glb")

STATION, PROPS = "Nurse_station", "Props_source"
PARK = Vector((14, 0, 0))            # review row; step 6 moves things to the seed layout
CART_SCALE = 0.57                    # the cart's drawers are 1.14 wide in the file; real ones ~0.65 m
LAMP_SCALE = 0.75                    # 0.8 m panel -> 0.6 m, the usual ceiling-grid size
KEYBOARD_GAP = 0.35                  # keyboard centre, from the monitor toward the chair (m)
ROOTS = ["station_root", "tv_station", "prop_cart", "prop_wheelchair", "prop_ceiling_lamp", "keyboard_template"]
KEEP = {"polySurface83": "desk", "ComputerAndMonitor": "computers", "Office_Chair": "chairs",
        "TV": "tv", "Wheelchair": "wheelchair"}


# ------------------------------------------------------------------- small helpers
def import_new(importer):
    """Run an importer; return (new objects, new materials)."""
    objs, mats = set(bpy.data.objects), set(bpy.data.materials)
    importer()
    bpy.context.view_layer.update()
    return ([o for o in bpy.data.objects if o not in objs], [m for m in bpy.data.materials if m not in mats])


def unparent_keep_pose(o):
    pose = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = pose


def move_to(o, coll):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    coll.objects.link(o)


def drop(objs):
    """Delete objects and the meshes nothing else uses."""
    meshes = {o.data for o in objs if o.type == "MESH"}
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for m in meshes:
        if m.users == 0:
            bpy.data.meshes.remove(m)


def new_root(name, coll):
    root = bpy.data.objects.new(name, None)
    coll.objects.link(root)
    return root


def adopt(child, root, pose=None):
    """Put `child` inside `root`: `pose` (default: its current world pose) becomes its pose
    in the root's own frame, so moving, turning or scaling the root moves the whole asset."""
    pose = (child.matrix_world if pose is None else pose).copy()
    child.parent = root
    child.matrix_parent_inverse = Matrix.Identity(4)
    child.matrix_basis = pose


def bottom_centre(objs):
    lo, hi = common.world_bbox(objs)
    return Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))


def tris(objs):
    return sum(len(o.data.polygons) for o in objs if o.type == "MESH")


# ---------------------------------------------------------- the pack's own materials
def pack_name(mat):
    """The importer renames repeats ("Desk_Wood.001"); the texture files use the plain name."""
    return re.sub(r"\.\d+$", "", mat.name)


def pack_material(mat):
    """Wire the pack's PNG maps (BaseColor, Roughness, Metallic, Normal) into a Principled BSDF."""
    base = os.path.join(RECEPTION_TEX, pack_name(mat))
    path = {k: f"{base}_{k}.tga.png" for k in ("BaseColor", "Roughness", "Metallic", "Normal")}
    if not os.path.exists(path["BaseColor"]):
        return False
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def image(kind, colorspace):
        n = nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path[kind], check_existing=True)
        n.image.colorspace_settings.name = colorspace
        return n.outputs["Color"]

    links.new(image("BaseColor", "sRGB"), bsdf.inputs["Base Color"])
    for kind in ("Roughness", "Metallic"):
        if os.path.exists(path[kind]):
            links.new(image(kind, "Non-Color"), bsdf.inputs[kind])
    if os.path.exists(path["Normal"]):
        nmap = nodes.new("ShaderNodeNormalMap")
        links.new(image("Normal", "Non-Color"), nmap.inputs["Color"])
        links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return True


# ------------------------------------------------------------------ the pieces
def remove_previous_run():
    """Delete what an earlier run made, including pieces left loose by a run that failed midway."""
    for name in ROOTS + list(KEEP):
        if name in bpy.data.objects:
            common.delete_tree(bpy.data.objects[name])
    for m in list(bpy.data.materials):          # the pack's materials, now unused
        if m.users == 0 and os.path.exists(os.path.join(RECEPTION_TEX, pack_name(m) + "_BaseColor.tga.png")):
            bpy.data.materials.remove(m)


def measure_workstations(computers, chairs, coll):
    """Monitor-head and seat centres, the desk-top height, and a dark screen quad over each
    monitor (the pack bakes a blue error screen into the monitor texture; ours is neutral and
    can later show something real). Measured from the loose pieces of the two meshes."""
    cparts, hparts = common.loose_parts(computers), common.loose_parts(chairs)
    heads, seats = [], []
    for p in cparts:
        lo, hi = common.world_bbox([p])
        if hi.z - lo.z > 0.4 and lo.z > 1.0:          # 0.44 m tall, above the desk top
            heads.append(p)
    desk_top = min(common.world_bbox([p])[0].z for p in cparts)
    for p in hparts:
        lo, hi = common.world_bbox([p])
        if len(p.data.polygons) == 160 and hi.z - lo.z < 0.25 and lo.z > 0.6:   # the seat pads
            seats.append((lo + hi) / 2)
    monitors, screens = [], []
    for i, p in enumerate(heads):
        lo, hi = common.world_bbox([p])
        centre = (lo + hi) / 2
        monitors.append(centre)
        if seats:
            seat = min(seats, key=lambda s: (s - centre).length)
            toward = Vector((seat.x - centre.x, seat.y - centre.y, 0)).normalized()
            q = common.screen_quad(p, f"screen_station_pc_{i}", coll, inset=0.01, toward=toward)
            q["twin_role"] = "station_pc_screen"
            screens.append(q)
    drop(cparts + hparts)
    return monitors, seats, desk_top, screens


def import_keyboard_template(coll):
    """The keyboard, slimmed, in its own root (origin at the bottom centre; front is -Y)."""
    new, _ = import_new(lambda: bpy.ops.import_scene.gltf(filepath=KEYBOARD_GLB))
    meshes = [o for o in new if o.type == "MESH"]
    for o in meshes:
        unparent_keep_pose(o)
    drop([o for o in new if o.type != "MESH"])
    root = new_root("keyboard_template", coll)
    shift = Matrix.Translation(-bottom_centre(meshes))
    for o in meshes:
        pose = shift @ o.matrix_world
        move_to(o, coll)
        adopt(o, root, pose)
    bpy.context.view_layer.update()
    for o in meshes:
        common.decimated(o, common.poly_budget(o, hi=1500))
    return root


def build_station(kept, coll):
    """Desk, monitors and chairs under one root, turned so the chairs are on local -Y."""
    desk, computers, chairs = kept["desk"], kept["computers"], kept["chairs"]
    lo, hi = common.world_bbox([desk, computers, chairs])
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0))
    d_lo, d_hi = common.world_bbox([desk])
    c_lo, c_hi = common.world_bbox([chairs])
    to_staff = (c_lo + c_hi) / 2 - (d_lo + d_hi) / 2
    turn = Matrix.Rotation(-math.pi / 2 - math.atan2(to_staff.y, to_staff.x), 4, "Z")
    frame = turn @ Matrix.Translation(-centre)
    root = new_root("station_root", coll)
    root["twin_role"] = "nurse_station"
    for o, name in ((desk, "station_desk"), (computers, "station_computers"), (chairs, "station_chairs")):
        unparent_keep_pose(o)
        pose = frame @ o.matrix_world
        move_to(o, coll)
        o.name = name
        adopt(o, root, pose)
    bpy.context.view_layer.update()
    return root, centre


# ------------------------------------------------------------------------ run
remove_previous_run()
bpy.context.view_layer.update()
station_coll = common.get_collection(STATION)
props_coll = common.get_collection(PROPS)

# 1. Reception pack: import, keep the useful parts, delete the rest of what was imported.
new, new_mats = import_new(lambda: bpy.ops.import_scene.fbx(filepath=RECEPTION_FBX))
kept = {role: next(o for o in new if o.name == name) for name, role in KEEP.items()}
for o in kept.values():
    unparent_keep_pose(o)
drop([o for o in new if o not in kept.values()])
for m in new_mats:
    if not m.users:
        bpy.data.materials.remove(m)
    elif not pack_material(m):
        print("no pack textures for material", m.name)

# 2. The station (root at the origin while we place the keyboards, parked at the end).
station, lobby_centre = build_station(kept, station_coll)

# 3. Keyboards: one in front of each monitor, facing its chair.
monitors, seats, desk_top, pc_screens = measure_workstations(
    bpy.data.objects["station_computers"], bpy.data.objects["station_chairs"], station_coll)
for q in pc_screens:
    adopt(q, station)
keyboard = import_keyboard_template(props_coll)
if len(monitors) == len(seats) == 3:
    for i, m in enumerate(monitors):
        seat = min(seats, key=lambda s: (s - m).length)
        d = Vector((seat.x - m.x, seat.y - m.y, 0)).normalized()
        at = Vector((m.x, m.y, desk_top)) + d * KEYBOARD_GAP
        # the keyboard's front (space bar) is local -Y; turn it to face the chair
        place = Matrix.Translation(at) @ Matrix.Rotation(math.atan2(d.x, -d.y), 4, "Z")
        kb = common.linked_copy(keyboard, f"keyboard.{i}", place, collection=station_coll)
        adopt(kb, station)
else:
    print("WARNING: expected 3 monitors and 3 seats, found", len(monitors), len(seats), "- no keyboards placed")
keyboard.location = PARK + Vector((10, 8, 1))

# 4. The TV: keep one of the two, give it its own screen quad, front facing local +X.
tv_parts = common.loose_parts(kept["tv"])
tv_parts.sort(key=lambda p: common.world_bbox([p])[0].x)
tv_frame = tv_parts[0]
drop([kept["tv"]] + tv_parts[1:])
t_lo, t_hi = common.world_bbox([tv_frame])
t_centre = (t_lo + t_hi) / 2
facing = Vector((lobby_centre.x - t_centre.x, lobby_centre.y - t_centre.y, 0)).normalized()
screen = common.screen_quad(tv_frame, "screen_tv_station", station_coll, inset=0.04, toward=facing)
screen["twin_role"] = "station_tv_screen"
upright = Matrix.Rotation(-math.atan2(facing.y, facing.x), 4, "Z") @ Matrix.Translation(-t_centre)
tv_root = new_root("tv_station", station_coll)
tv_root["twin_role"] = "station_tv"
tv_frame.name = "tv_frame"
for o in (tv_frame, screen):
    pose = upright @ o.matrix_world
    move_to(o, station_coll)
    adopt(o, tv_root, pose)
tv_root.location = PARK + Vector((-3, 6, t_centre.z))

screen_mat = bpy.data.materials.get("screen_off")      # made by step 4
for q in pc_screens + [screen]:
    q.data.materials.clear()
    if screen_mat:
        q.data.materials.append(screen_mat)

# 5. Wheelchair.
wc_root = new_root("prop_wheelchair", props_coll)
wc = kept["wheelchair"]
pose = Matrix.Translation(-bottom_centre([wc])) @ wc.matrix_world
move_to(wc, props_coll)
adopt(wc, wc_root, pose)
wc_root.location = PARK + Vector((3, 8, 0))

# 6. Crash cart (USDZ): meshes under one scaled root, every part slimmed.
new, _ = import_new(lambda: bpy.ops.wm.usd_import(filepath=CART_USDZ))
cart = [o for o in new if o.type == "MESH"]
for o in cart:
    unparent_keep_pose(o)
drop([o for o in new if o.type != "MESH"])
cart_root = new_root("prop_cart", props_coll)
shift = Matrix.Translation(-bottom_centre(cart))
for o in cart:
    pose = shift @ o.matrix_world
    move_to(o, props_coll)
    adopt(o, cart_root, pose)
cart_root.scale = (CART_SCALE,) * 3
cart_root.location = PARK + Vector((6, 8, 0))
bpy.context.view_layer.update()
for o in cart:
    common.decimated(o, common.poly_budget(o, per_metre=1200, lo=30, hi=600))

# 7. Ceiling light panel (the lit variant only), origin at its top face.
new, _ = import_new(lambda: bpy.ops.import_scene.gltf(filepath=LAMP_GLB))
on = next(o for o in new if o.type == "MESH" and o.name.startswith("Fluorescent_Diffuser_ON"))
unparent_keep_pose(on)
drop([o for o in new if o is not on])
lamp_root = new_root("prop_ceiling_lamp", props_coll)
lo, hi = common.world_bbox([on])
pose = Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z))) @ on.matrix_world
move_to(on, props_coll)
on.name = "lamp_panel"
adopt(on, lamp_root, pose)
lamp_root.scale = (LAMP_SCALE,) * 3
lamp_root.location = PARK + Vector((8, 8, 2.4))

station.location = PARK
bpy.context.view_layer.update()
for name in ROOTS:
    print(f"{name}: {tris(common.subtree(bpy.data.objects[name]))} polygons")
