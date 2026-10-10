"""Step 4: real PBR materials instead of one flat grey for everything.

Run after steps 1-3:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/04_materials.py")

How it works (kept simple on purpose, so it can be explained):
1. MATERIALS is a table: name -> base colour, roughness, metallic, optional emission
   or transparency. Each one becomes a Principled BSDF, which is what glTF's
   "metallic-roughness" PBR model maps onto one to one.
2. pick() decides which material a part gets, from its name, its parents' names and
   its size. Room B has meaningful names (bed, cabinet, door...). The machines copied
   from Room A do not (Cylinder.405...), so for them we use size: thin and long =
   chrome pole, everything else = white plastic.
3. If a material has a `tex` slug AND its image maps exist in
   <BORJ_ASSETS>/textures/<slug>/ (made by prepare_textures.py from the Poly Haven
   downloads: <slug>_diff_*.jpg, <slug>_rough_*, <slug>_nor_gl_*.png) they are wired in.
   Tiled surfaces
   (floor, walls) get UVs measured in real metres so a texture repeats every `tile` m.
   Without the files, the plain colour is used, so the script always works.

Room A is not touched. Re-running is safe.
"""
import glob
import importlib
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

importlib.reload(common)   # a long-lived Blender session may hold an older copy

ASSETS = os.environ.get("BORJ_ASSETS", os.path.join(os.path.expanduser("~"), "Desktop", "borj-assets"))
TEX_DIR = os.path.join(ASSETS, "textures")

# Colours are linear RGB. `tex`: Poly Haven / ambientCG slug (see ASSETS.md); `tile`: metres per repeat.
MATERIALS = {
    # `tint` multiplies the texture's colour (lighten, or recolour a white fabric).
    "floor_vinyl":      dict(color=(0.35, 0.40, 0.42), rough=0.30, tex="floor_tiles_06", tile=2.4,
                             tint=(1.7, 1.7, 1.7)),
    "wall_paint":       dict(color=(0.70, 0.74, 0.72), rough=0.85, tex="white_stucco", tile=2.0),
    "ceiling_tile":     dict(color=(0.80, 0.80, 0.78), rough=0.90, tile=1.2),
    "paint_white":      dict(color=(0.75, 0.75, 0.73), rough=0.50),
    "laminate_white":   dict(color=(0.72, 0.72, 0.68), rough=0.45),
    "wood_door":        dict(color=(0.25, 0.12, 0.06), rough=0.55, tex="oak_veneer_01", tile=1.0),
    "metal_painted":    dict(color=(0.55, 0.58, 0.60), rough=0.35, metal=0.8),
    "chrome":           dict(color=(0.80, 0.80, 0.82), rough=0.15, metal=1.0),
    "steel_brushed":    dict(color=(0.60, 0.62, 0.65), rough=0.35, metal=1.0),
    "mattress_vinyl":   dict(color=(0.15, 0.30, 0.38), rough=0.45, tex="leather_white", tile=0.6,
                             tint=(0.25, 0.5, 0.65)),
    "sheet_cotton":     dict(color=(0.85, 0.85, 0.88), rough=0.90, tex="rough_linen", tile=0.5),   # pale blue linen
    "upholstery_fabric": dict(color=(0.45, 0.30, 0.02), rough=0.80, tex="waffle_pique_cotton",
                              tile=0.4),                                         # mustard accent
    "curtain_fabric":   dict(color=(0.25, 0.50, 0.58), rough=0.95, tex="fabric_pattern_05", tile=0.6),
    "rubber_black":     dict(color=(0.02, 0.02, 0.02), rough=0.80),
    "cable_black":      dict(color=(0.02, 0.02, 0.02), rough=0.60),
    "plastic_white":    dict(color=(0.80, 0.80, 0.82), rough=0.40),
    "plastic_clear":    dict(color=(0.80, 0.90, 1.00), rough=0.10, alpha=0.35),
    "glass_clear":      dict(color=(0.75, 0.90, 1.00), rough=0.02, alpha=0.20),
    "screen_off":       dict(color=(0.01, 0.015, 0.02), rough=0.10),
    "paper_print":      dict(color=(0.85, 0.85, 0.82), rough=0.80),
    "frame_dark":       dict(color=(0.02, 0.015, 0.01), rough=0.50),
    "light_emissive":   dict(color=(1, 1, 1), rough=0.50, emit=(1.0, 0.95, 0.85), emit_strength=3.0),
    "light_board":      dict(color=(1, 1, 1), rough=0.50, emit=(0.9, 0.95, 1.0), emit_strength=1.0),
}


# ------------------------------------------------------------------ materials
def find_map(slug, kind):
    hits = sorted(glob.glob(os.path.join(TEX_DIR, slug, f"{slug}_{kind}_*")))
    hits = [h for h in hits if h.lower().endswith((".jpg", ".png"))]
    return hits[0] if hits else None


def image_node(nodes, path, colorspace):
    n = nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path, check_existing=True)
    n.image.colorspace_settings.name = colorspace
    return n


def build_material(name, spec):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*spec["color"], 1)
    bsdf.inputs["Roughness"].default_value = spec["rough"]
    bsdf.inputs["Metallic"].default_value = spec.get("metal", 0.0)
    if "alpha" in spec:
        bsdf.inputs["Alpha"].default_value = spec["alpha"]
        mat.surface_render_method = "BLENDED"
    if "emit" in spec:
        bsdf.inputs["Emission Color"].default_value = (*spec["emit"], 1)
        bsdf.inputs["Emission Strength"].default_value = spec["emit_strength"]
    slug = spec.get("tex")
    if slug:
        diff, rough, nor = (find_map(slug, k) for k in ("diff", "rough", "nor_gl"))
        if diff:
            colour = image_node(nodes, diff, "sRGB").outputs["Color"]
            if "tint" in spec:                     # colour x tint (Mix node, Multiply)
                mix = nodes.new("ShaderNodeMix")
                mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
                mix.inputs["Factor"].default_value = 1.0
                a, b = [s for s in mix.inputs if s.type == "RGBA"]
                b.default_value = (*spec["tint"], 1)
                links.new(colour, a)
                colour = [s for s in mix.outputs if s.type == "RGBA"][0]
            links.new(colour, bsdf.inputs["Base Color"])
        if rough:
            links.new(image_node(nodes, rough, "Non-Color").outputs["Color"], bsdf.inputs["Roughness"])
        if nor:
            nmap = nodes.new("ShaderNodeNormalMap")
            links.new(image_node(nodes, nor, "Non-Color").outputs["Color"], nmap.inputs["Color"])
            links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def world_box_uv(obj, tile):
    """UVs in real metres / `tile`, projected along each face's dominant axis."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    layer = bm.loops.layers.uv.get("tiled") or bm.loops.layers.uv.new("tiled")
    mw, rot = obj.matrix_world, obj.matrix_world.to_3x3()
    for f in bm.faces:
        n = rot @ f.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            p = mw @ loop.vert.co
            u, v = ((p.y, p.z), (p.x, p.z), (p.x, p.y))[axis]
            loop[layer].uv = (u / tile, v / tile)
    bm.to_mesh(mesh)
    bm.free()
    mesh.uv_layers["tiled"].active = True
    mesh.uv_layers["tiled"].active_render = True


# --------------------------------------------------------------- which part gets what
def ancestors(obj):
    names, o = [], obj
    while o:
        names.append(o.name.lower())
        o = o.parent
    return names


def pick(o):
    chain = ancestors(o)
    me = chain[0]
    lo, hi = common.world_bbox([o])
    d = sorted(hi - lo, reverse=True)                      # longest side first
    rod = d[0] > 6 * max(d[1], 0.005) and d[1] < 0.06      # thin and long: a pole or rail

    def under(*tokens):
        """True if any ancestor's name (or the part's own) contains one of the tokens."""
        return any(t in n for n in chain for t in tokens)

    # "glass" is the original material; "glass_clear" is what an earlier run of this script gave it
    was_glass = any(s.material and s.material.name in ("glass", "glass_clear") for s in o.material_slots)

    if me.startswith("screen_monitor"):                    # also screen_monitor.001 (a copy)
        return "screen_off"
    if under("bedside_monitor", "iv_pole", "headwall_unit"):          # copied from Room A
        if rod:
            return "chrome"
        if me.startswith(("nurbspath", "beziercurve", "circle")):
            return "cable_black"
        if under("iv_pole") and me.startswith(("plane", "cylinder.35")):
            return "plastic_clear"                                     # the drip bag
        return "plastic_white"
    if me == "floor":
        return "floor_vinyl"
    if me in ("wall", "wall1", "wall2") or me.startswith("shell_wall"):
        return "wall_paint"
    if me == "shell_ceiling":
        return "ceiling_tile"
    if was_glass:
        return "glass_clear"
    if under("doorand_win"):
        if ":dastgire" in me:
            return "chrome"
        return "wood_door" if (":door" in me and ":frame" not in me) else "paint_white"
    if under("all_bed"):
        if "ppipe" in me or "pcylinder" in me:
            return "metal_painted"
        return "mattress_vinyl" if "pcube" in me else "sheet_cotton"
    if under("chair", "sofa"):
        return "chrome" if (rod or "pcylinder" in me) else "upholstery_fabric"
    if under("cabinet", "shelf"):
        return "laminate_white"
    if under("screen_with_curtain"):
        return "curtain_fabric" if (d[0] > 0.6 and d[2] < 0.1) else "metal_painted"
    if under("trolley"):
        if "wheel" in me:
            return "rubber_black"
        return "sheet_cotton" if "towel" in me else "steel_brushed"
    if under("serum"):                                     # IV stand: bags hang high, the rest is metal
        hanging_bag = (lo.z + hi.z) / 2 > 1.0 and d[0] < 0.45 and not rod
        return "plastic_clear" if hanging_bag else ("chrome" if rod else "steel_brushed")
    if under("light_board"):
        return "light_board" if ":board" in me else "paper_print"
    if under("poster"):
        return "frame_dark" if "frame" in me else "paper_print"
    if under("light"):
        return "light_emissive"
    return "paint_white"


# ------------------------------------------------------------------------- run
bpy.context.view_layer.update()
mats = {name: build_material(name, spec) for name, spec in MATERIALS.items()}
counts = {}
done = set()
for o in bpy.context.view_layer.objects:            # visible only: archive and kit source are excluded
    if o.type != "MESH" or "sketchfab_model" in ancestors(o) or o.data in done:
        continue
    name = pick(o)
    o.data.materials.clear()
    o.data.materials.append(mats[name])
    tile = MATERIALS[name].get("tile")
    if tile:
        world_box_uv(o, tile)
    done.add(o.data)
    counts[name] = counts.get(name, 0) + 1
print("materials assigned (meshes per material):", counts)
