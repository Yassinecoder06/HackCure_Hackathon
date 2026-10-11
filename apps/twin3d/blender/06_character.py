"""Step 6: the ward staff character: a skinned, animated figure with role-coloured outfits.

Run after steps 1-5 (it does not depend on them; any scene works):
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/06_character.py")

One nurse model is used for all staff (CN1, N1-N3, CA1, DR1 in seed/ward-W1.yaml). The web app
clones it and sets the shirt and trousers colour per role, so "same mesh, different colour"
costs nothing extra. What this script has to solve:

1. The model's skeleton is made of plain "Null" nodes (3ds Max Biped), so Blender imports 66
   empties, a lying mesh and NO skin. The skin weights are still in the file (132 skin clusters),
   so we read them straight from the FBX with Blender's own parser and rebuild the rig:
   - the mesh's own coordinates already match the skeleton (checked: head-top bone 1.727 m vs
     mesh 1.717 m; fingertip bones +-0.82 m vs mesh +-0.818 m), so the importer's extra rotation
     on the mesh objects is simply removed;
   - one real bone per node, its rest pose = the node's pose;
   - vertex groups from the clusters, at most 4 influences per vertex (the glTF limit).
2. The nine Mixamo clips are keyed per node. Each is baked onto the bones as a Blender action
   (basis = rest_local^-1 @ animated_local, both from world matrices), under short stable
   names for the web app: idle, walk, type, talk, sit_idle, sit_to_stand, stand_to_sit,
   sit_to_type, type_to_sit. All are 30 fps and in place (the web app moves the figure).
3. Outfit colour. The shirt, trousers and scrub cap textures are blue, and a blue texture cannot become
   a white coat by multiplying. So we make a neutral (grey) copy of those three textures and put
   the role colour in a Multiply node, which glTF stores as a plain base-colour factor.

The mesh parts are named nurse_body, nurse_top, nurse_bottom, ...; the materials nurse_top,
nurse_bottom and nurse_hat are the ones the web app recolours. Everything is parked in a review row near
(14, 12). Re-running is safe.
"""
import importlib
import json
import os
import sys

import bpy
import numpy as np
from io_scene_fbx import parse_fbx
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

importlib.reload(common)   # a long-lived Blender session may hold an older copy

ASSETS = os.environ.get("BORJ_ASSETS", os.path.join(os.path.expanduser("~"), "Desktop", "borj-assets"))
CHARS = os.path.join(ASSETS, "characters")
NURSE_FBX = os.path.join(CHARS, "nurse", "source", "Nurse_Woman_FBX.fbx")
TEX = os.path.join(CHARS, "nurse", "textures")
NEUTRAL = os.path.join(CHARS, "nurse", "textures_neutral")
ANIM_DIR = os.path.join(CHARS, "animations")

COLLECTION = "Characters_source"
RIG = "nurse_rig"
PARK = Vector((14, 12, 0))
FPS = 30
MAX_INFLUENCES = 4                    # glTF allows 4 joints per vertex
SKELETON_ROOT = "Biped"               # the first real bone; its parent is the model's pivot node
# Mixamo file -> action name the web app plays; True = loops
ANIMS = {
    "idle": ("Idle", True), "walk": ("Walking", True), "type": ("Typing", True), "talk": ("Talking", True),
    "sit_idle": ("Sitting Idle", True), "sit_to_stand": ("Sit To Stand", False),
    "stand_to_sit": ("Stand To Sit", False), "sit_to_type": ("Sit To Type", False),
    "type_to_sit": ("Type To Sit", False),
}
# Linear RGB tints for the three recoloured parts (shirt, trousers, scrub cap), per role in
# seed/ward-W1.yaml. The neutral textures average ~0.8, so these are close to the final colour.
OUTFITS = {
    # blue scrubs
    "nurse":          {"top": (0.05, 0.30, 0.70), "bottom": (0.04, 0.22, 0.55), "hat": (0.05, 0.30, 0.70)},
    # navy
    "charge_nurse":   {"top": (0.02, 0.07, 0.28), "bottom": (0.02, 0.05, 0.20), "hat": (0.02, 0.07, 0.28)},
    # green
    "care_assistant": {"top": (0.08, 0.50, 0.22), "bottom": (0.10, 0.25, 0.15), "hat": (0.08, 0.50, 0.22)},
    # white coat, dark trousers and cap
    "doctor":         {"top": (0.90, 0.90, 0.90), "bottom": (0.06, 0.06, 0.07), "hat": (0.10, 0.10, 0.12)},
}
PARTS = {        # imported mesh object -> (our name, material it uses)
    "Body008": ("nurse_body", "Body"), "Eyes002": ("nurse_eyes", "Body"), "Eyelashes002": ("nurse_eyelashes", "Body"),
    "Tops002": ("nurse_top", "Top"), "Bottoms002": ("nurse_bottom", "Bottom"), "Shoes002": ("nurse_shoes", "Shoes"),
    "Gloves002": ("nurse_gloves", "Glove"), "Hair002": ("nurse_hair", "Hair"),
    "Hats002": ("nurse_hat", "Hat"), "Masks002": ("nurse_mask", "Mask"),
}
OPTIONAL = ("nurse_mask",)      # a ward does not need a surgical mask; hidden, kept in the file. The cap stays: the
                                # model's hair is only the part under it, so without it the scalp is bare


# ------------------------------------------------------------- reading the skin from the FBX
def fbx_name(elem):
    return elem.props[1].split(b"\x00")[0].decode()


def read_skin(path):
    """{mesh name: {bone name: (vertex indices, weights)}} straight from the FBX skin clusters."""
    root, _ = parse_fbx.parse(path)
    objs = [e for e in root.elems if e.id == b"Objects"][0]
    conns = [e for e in root.elems if e.id == b"Connections"][0]
    byid = {e.props[0]: e for e in objs.elems if e.props and isinstance(e.props[0], int)}
    kids = {}
    for c in conns.elems:
        if c.id == b"C" and c.props[0] == b"OO":
            kids.setdefault(c.props[2], []).append(c.props[1])
    out = {}
    for mid, model in byid.items():
        if model.id != b"Model" or model.props[2] != b"Mesh":
            continue
        for gid in [k for k in kids.get(mid, []) if byid[k].id == b"Geometry"]:
            for sid in [k for k in kids.get(gid, []) if byid[k].id == b"Deformer" and byid[k].props[2] == b"Skin"]:
                bones = {}
                for cid in [k for k in kids.get(sid, []) if byid[k].id == b"Deformer"]:
                    bone = [byid[k] for k in kids.get(cid, []) if byid[k].id == b"Model"]
                    if not bone:
                        continue
                    get = {e.id: e for e in byid[cid].elems}
                    if b"Indexes" in get and b"Weights" in get:
                        bones[fbx_name(bone[0])] = (list(get[b"Indexes"].props[0]), list(get[b"Weights"].props[0]))
                out[fbx_name(model)] = bones
    return out


# ------------------------------------------------------------------------- the rig
def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    bpy.context.view_layer.update()
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        o["twin_temp_import"] = True        # so a run that fails midway can never leave debris behind
    return new


def build_armature(nodes, coll):
    """One bone per skeleton node (children of SKELETON_ROOT, plus the root), rest pose = node pose."""
    root_node = nodes[SKELETON_ROOT]
    order, queue = [], [root_node]
    while queue:
        n = queue.pop(0)
        order.append(n)
        queue += [c for c in n.children if c.type == "EMPTY"]
    arm_data = bpy.data.armatures.new(RIG)
    arm = bpy.data.objects.new(RIG, arm_data)
    coll.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    rest = {}
    for n in order:
        eb = arm_data.edit_bones.new(n.name)
        m = n.matrix_world.copy()
        m.normalize()
        # Give the bone its length BEFORE setting the matrix: a zero-length bone has no direction
        # to keep and Blender picks its own, which flipped 61 of 65 bones by up to 180 degrees.
        eb.head, eb.tail = (0, 0, 0), (0, 0.05, 0)
        eb.matrix = m
        if n.parent is not None and n.parent.name in arm_data.edit_bones:
            eb.parent = arm_data.edit_bones[n.parent.name]
        rest[n.name] = n.matrix_world.copy()
    bpy.ops.object.mode_set(mode="OBJECT")
    pos = max((arm_data.bones[k].matrix_local - Matrix(v)).to_translation().length for k, v in rest.items())
    rot = max((arm_data.bones[k].matrix_local.to_3x3().inverted() @ Matrix(v).to_3x3()).to_quaternion().angle
              for k, v in rest.items()) * 180 / 3.14159265
    print(f"rig: {len(order)} bones, worst rest error {pos:.6f} m and {rot:.3f} degrees")
    assert rot < 0.5, "bone rest orientation does not match the skeleton nodes"
    return arm


def skin_meshes(arm, meshes, skin):
    """Vertex groups from the FBX clusters, limited to MAX_INFLUENCES, plus the Armature modifier."""
    bone_names = {b.name for b in arm.data.bones}
    for name, o in meshes.items():
        bones = skin.get(name, {})
        n = len(o.data.vertices)
        per_vertex = [[] for _ in range(n)]
        for bone, (idx, wts) in bones.items():
            if bone not in bone_names:
                continue
            for i, w in zip(idx, wts, strict=True):
                if w > 1e-4 and i < n:
                    per_vertex[i].append((w, bone))
        groups = {}
        unweighted = 0
        for i, infl in enumerate(per_vertex):
            infl = sorted(infl, reverse=True)[:MAX_INFLUENCES]
            total = sum(w for w, _ in infl)
            if not infl:
                unweighted += 1
                continue
            for w, bone in infl:
                groups.setdefault(bone, []).append((i, w / total))
        for bone, items in groups.items():
            vg = o.vertex_groups.new(name=bone)
            for i, w in items:
                vg.add([i], w, "REPLACE")
        mod = o.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        o.parent = arm
        o.matrix_parent_inverse = Matrix.Identity(4)
        print(f"skin {o.name}: {len(groups)} bones, {unweighted} of {n} vertices unweighted")


# ------------------------------------------------------------------- animation baking
def bake_action(arm, name, loop, anim_nodes, bones_in_order):
    """Sample the animated nodes every frame and key the armature's pose bones."""
    scene = bpy.context.scene
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = action
    rest_local = {}
    for b in bones_in_order:
        rest_local[b.name] = (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local.copy()
    frames = sorted({int(round(f)) for o in anim_nodes.values() if o.animation_data and o.animation_data.action
                     for f in o.animation_data.action.frame_range})
    f0, f1 = (frames[0], frames[-1]) if frames else (1, 1)
    loc = {b.name: [] for b in bones_in_order}
    rot = {b.name: [] for b in bones_in_order}
    last_q = {}
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        world = {n: o.matrix_world.copy() for n, o in anim_nodes.items()}
        for b in bones_in_order:
            a = world[b.name]
            local = (world[b.parent.name].inverted() @ a) if b.parent else a
            basis = rest_local[b.name].inverted() @ local
            q = basis.to_quaternion()
            p = last_q.get(b.name)
            if p is not None and p.dot(q) < 0:
                q.negate()                      # keep the quaternion on the short path between frames
            last_q[b.name] = q
            loc[b.name].append(basis.to_translation())
            rot[b.name].append(q)
    n = f1 - f0 + 1
    times = np.arange(f0, f1 + 1, dtype=np.float32)
    for b in bones_in_order:
        L = np.array([tuple(v) for v in loc[b.name]], dtype=np.float32)
        R = np.array([tuple(q) for q in rot[b.name]], dtype=np.float32)
        for path, data, comps in (("location", L, 3), ("rotation_quaternion", R, 4)):
            for k in range(comps):
                data_path = f'pose.bones["{b.name}"].{path}'
                fc = action.fcurve_ensure_for_datablock(arm, data_path, index=k, group_name=b.name)
                fc.keyframe_points.add(n)
                co = np.empty(2 * n, dtype=np.float32)
                co[0::2], co[1::2] = times, data[:, k]
                fc.keyframe_points.foreach_set("co", co)
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"                                # exact reproduction of the samples
                fc.update()
    action.use_frame_range = True
    action.frame_start, action.frame_end = f0, f1
    action.use_cyclic = loop
    return action


# ------------------------------------------------------------------ textures and materials
def neutral_texture(part):
    """A grey copy of <part>_diffuse (so a colour factor can recolour it); cached on disk."""
    src = os.path.join(TEX, f"Nurse Woman1_{part}_diffuse.png")
    dst = os.path.join(NEUTRAL, f"Nurse Woman1_{part}_diffuse_neutral.png")
    if os.path.exists(dst):
        return dst
    os.makedirs(NEUTRAL, exist_ok=True)
    img = bpy.data.images.load(src)
    img.colorspace_settings.name = "Non-Color"             # raw 0..1, no colour transform
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    lum = px[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    lum = np.clip(lum / max(float(lum.mean()), 1e-4) * 0.8, 0, 1)
    px[:, :3] = lum[:, None]
    px[:, 3] = 1.0
    out = bpy.data.images.new("neutral", *img.size, alpha=False, float_buffer=False)
    out.colorspace_settings.name = "Non-Color"
    out.pixels.foreach_set(px.ravel())
    out.file_format = "PNG"
    out.filepath_raw = dst
    out.save()
    bpy.data.images.remove(out)
    bpy.data.images.remove(img)
    return dst


def rgba_texture(part):
    """<part>_diffuse with its separate opacity map stored as the alpha channel (glTF only reads alpha
    from the colour texture); cached on disk. Returns the path."""
    src = os.path.join(TEX, f"Nurse Woman1_{part}_diffuse.png")
    opa = os.path.join(TEX, f"Nurse Woman1_{part}_opacity.png")
    dst = os.path.join(NEUTRAL, f"Nurse Woman1_{part}_diffuse_rgba.png")
    if os.path.exists(dst):
        return dst
    os.makedirs(NEUTRAL, exist_ok=True)
    img = bpy.data.images.load(src)
    alpha = bpy.data.images.load(opa)
    for i in (img, alpha):
        i.colorspace_settings.name = "Non-Color"           # raw 0..1, no colour transform
    if tuple(alpha.size) != tuple(img.size):
        alpha.scale(*img.size)
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    ap = np.empty(len(alpha.pixels), dtype=np.float32)
    alpha.pixels.foreach_get(ap)
    px = px.reshape(-1, 4)
    px[:, 3] = ap.reshape(-1, 4)[:, 0]
    out = bpy.data.images.new("rgba", *img.size, alpha=True, float_buffer=False)
    out.colorspace_settings.name = "Non-Color"
    out.alpha_mode = "STRAIGHT"
    out.pixels.foreach_set(px.ravel())
    out.file_format = "PNG"
    out.filepath_raw = dst
    out.save()
    for i in (out, img, alpha):
        bpy.data.images.remove(i)
    return dst


def tex_node(nodes, part, kind, colorspace, path=None):
    """An image-texture node for <part>_<kind> (or `path`); its colour output, or None if the file is missing."""
    path = path or os.path.join(TEX, f"Nurse Woman1_{part}_{kind}.png")
    if not os.path.exists(path):
        return None
    n = nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path, check_existing=True)
    n.image.colorspace_settings.name = colorspace
    n.image.alpha_mode = "STRAIGHT"
    return n.outputs["Color"], n.outputs["Alpha"]


def build_materials():
    """nurse_<part> materials from the pack's maps (diffuse, gloss -> roughness, normal, opacity)."""
    mats = {}
    for part in sorted({m for _, m in PARTS.values()}):
        name = f"nurse_{part.lower().replace('glove', 'gloves')}"
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        bsdf.inputs["Specular IOR Level"].default_value = 0.3

        recolour = part in ("Top", "Bottom", "Hat")
        has_alpha = part in ("Hair", "Glove", "Body") and os.path.exists(
            os.path.join(TEX, f"Nurse Woman1_{part}_opacity.png"))
        if has_alpha:
            colour, alpha = tex_node(nodes, part, "diffuse", "sRGB", rgba_texture(part))
            links.new(alpha, bsdf.inputs["Alpha"])
            mat.surface_render_method = "DITHERED"
        else:
            colour, alpha = tex_node(nodes, part, "diffuse", "sRGB", neutral_texture(part) if recolour else None) \
                or (None, None)
        if colour is not None and recolour:
            mix = nodes.new("ShaderNodeMix")
            mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            a, b = [s for s in mix.inputs if s.type == "RGBA"]
            b.default_value = (*OUTFITS["nurse"][part.lower()], 1)
            links.new(colour, a)
            colour = [s for s in mix.outputs if s.type == "RGBA"][0]
            mat["tint_node"] = mix.name
        if colour is not None:
            links.new(colour, bsdf.inputs["Base Color"])
        gloss = (tex_node(nodes, part, "gloss", "Non-Color") or (None,))[0]
        if gloss is not None:
            inv = nodes.new("ShaderNodeInvert")
            links.new(gloss, inv.inputs["Color"])
            links.new(inv.outputs["Color"], bsdf.inputs["Roughness"])
        normal = (tex_node(nodes, part, "normal", "Non-Color") or (None,))[0]
        if normal is not None:
            nmap = nodes.new("ShaderNodeNormalMap")
            links.new(normal, nmap.inputs["Color"])
            links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        mats[part] = mat
    return mats


def set_outfit(role):
    """Preview/set the shirt and trousers colour for a role (the web app does the same at runtime)."""
    for part in ("Top", "Bottom", "Hat"):
        mat = bpy.data.materials[f"nurse_{part.lower()}"]
        mix = mat.node_tree.nodes[mat["tint_node"]]
        b = [s for s in mix.inputs if s.type == "RGBA"][1]
        b.default_value = (*OUTFITS[role][part.lower()], 1)


# ------------------------------------------------------------------------------ run
def remove_previous_run():
    """Delete what an earlier run made, including imported pieces left loose by a run that failed."""
    for o in list(bpy.data.objects):
        if o.name == RIG or o.name.startswith("nurse_") or o.get("twin_temp_import"):
            bpy.data.objects.remove(o, do_unlink=True)
    for a in list(bpy.data.actions):
        if a.name in ANIMS:
            bpy.data.actions.remove(a)
    for d in list(bpy.data.armatures):
        if d.name.startswith(RIG) and d.users == 0:
            bpy.data.armatures.remove(d)
    for m in list(bpy.data.meshes):
        if m.users == 0 and m.name.startswith("nurse_"):
            bpy.data.meshes.remove(m)


remove_previous_run()
bpy.context.view_layer.update()
actions_at_start = set(bpy.data.actions)
start = common.snapshot()
scene = bpy.context.scene
scene.render.fps = FPS
coll = common.get_collection(COLLECTION)

# 1. Import the model; the skeleton arrives as empties and the meshes lie down.
new = import_fbx(NURSE_FBX)
nodes = {o.name: o for o in new if o.type == "EMPTY"}
meshes_raw = {o.name: o for o in new if o.type == "MESH"}
skin = read_skin(NURSE_FBX)

# 2. Real armature + skin weights; meshes get identity transforms (their data is already in place).
arm = build_armature(nodes, coll)
meshes = {}
for src_name, (new_name, _) in PARTS.items():
    o = meshes_raw[src_name]
    o.parent = None
    o.matrix_world = Matrix.Identity(4)
    o.name = new_name
    del o["twin_temp_import"]
    for c in list(o.users_collection):
        c.objects.unlink(o)
    coll.objects.link(o)
    meshes[src_name] = o
skin_meshes(arm, meshes, skin)
bones_in_order = []
queue = [arm.data.bones[SKELETON_ROOT]]
while queue:
    b = queue.pop(0)
    bones_in_order.append(b)
    queue += list(b.children)
for o in nodes.values():
    bpy.data.objects.remove(o, do_unlink=True)

# 3. Materials, with the shirt and trousers neutral so a colour factor recolours them.
mats = build_materials()
for src_name, (new_name, mat_part) in PARTS.items():
    o = meshes[src_name]
    o.data.materials.clear()
    o.data.materials.append(mats[mat_part])
    if new_name in OPTIONAL:
        o["twin_optional"] = True
        o.hide_viewport = o.hide_render = True

# 4. Animations: import each Mixamo clip, bake it onto the bones, discard the temporary nodes.
for action_name, (file_name, loop) in ANIMS.items():
    tmp = import_fbx(os.path.join(ANIM_DIR, f"{file_name}.fbx"))
    anim_nodes = {o.name: o for o in tmp if o.type == "EMPTY"}
    missing = [b.name for b in bones_in_order if b.name not in anim_nodes]
    if missing:
        print(f"WARNING: {file_name} lacks nodes {missing[:5]}")
        continue
    act = bake_action(arm, action_name, loop, anim_nodes, bones_in_order)
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)
    print(f"clip {action_name}: frames {int(act.frame_start)}-{int(act.frame_end)}")
for a in list(bpy.data.actions):          # the importer's own per-node curves ("Biped|mixamo.com|Layer0", "Take 001"),
    if a not in actions_at_start and a.name not in ANIMS:    # some with a fake user, which would keep them alive
        bpy.data.actions.remove(a)
arm.animation_data.action = bpy.data.actions["idle"]
scene.frame_set(1)

# 5. Role outfits are stored with the rig for the web app, and the nurse default is applied.
arm["twin_outfits"] = json.dumps(OUTFITS)
arm["twin_clips"] = json.dumps({k: v[1] for k, v in ANIMS.items()})
set_outfit("nurse")
arm.location = PARK
common.purge_new(start)
bpy.context.view_layer.update()
print(f"character: {sum(len(o.data.polygons) for o in meshes.values())} polygons, "
      f"{len(bones_in_order)} bones, {len(ANIMS)} clips")
