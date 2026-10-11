"""Step 8: export what the web app loads into apps/twin3d/public/.

Run after steps 1-7:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/08_export.py")

Writes:
- models/ward.glb       everything in the "Ward" collection: rooms, corridor, station, props, patients.
                        Static geometry only. Named nodes the app drives: screen_<bed>, callLight_<bed>,
                        callLightDoor_<room>, patient_<bed>, screen_tv_station, screen_station_pc_N, and
                        any node with `twin_cutaway` (extras: the outward normal, in three.js axes).
- models/staff.glb      the skinned nurse with all nine clips and the nurse_top / nurse_bottom / nurse_hat
                        materials the app recolours per role (extras `twin_outfits`).
- models/ward-layout.json   every position the app needs (doors, bedsides, seats, waypoints), in three.js axes.
- hdri/hospital_1k.hdr  the CC0 childrens_hospital HDRI scaled to 1024 x 512 for image-based lighting.

Size choices (ADR 0012 asked for Draco and KTX2): Draco is on for geometry. Textures are WebP instead of
KTX2, because Blender cannot write KTX2 and the `toktx` tool is not part of this build; WebP is read by
every browser's GLTFLoader and is 5 to 10 times smaller than PNG. Lighting is NOT baked (see README).
"""
import importlib
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

importlib.reload(common)   # a long-lived Blender session may hold an older copy

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
OUT = os.path.join(REPO, "apps", "twin3d", "public")
ASSETS = os.environ.get("BORJ_ASSETS", os.path.join(os.path.expanduser("~"), "Desktop", "borj-assets"))
HDRI = os.path.join(ASSETS, "hdri", "childrens_hospital_2k.hdr")
CLIPS = ["idle", "walk", "type", "talk", "sit_idle", "sit_to_stand", "stand_to_sit", "sit_to_type", "type_to_sit"]

SHARED = dict(
    export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_cameras=False,
    export_lights=False, export_materials="EXPORT", export_texcoords=True, export_normals=True,
    export_tangents=False, export_vertex_color="NONE", export_image_format="WEBP", export_image_quality=82,
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
    export_draco_position_quantization=14, export_draco_normal_quantization=10,
    export_draco_texcoord_quantization=12, export_draco_color_quantization=8, export_draco_generic_quantization=12,
)


def select(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def mb(path):
    return f"{os.path.getsize(path) / 1e6:.1f} MB"


os.makedirs(os.path.join(OUT, "models"), exist_ok=True)
os.makedirs(os.path.join(OUT, "hdri"), exist_ok=True)
scene = bpy.context.scene

# 1. the ward: static meshes and the empties that carry names and extras
ward = bpy.data.collections["Ward"]
objs = [o for o in ward.all_objects if o.type in ("MESH", "EMPTY") and not o.hide_viewport]
select(objs)
path = os.path.join(OUT, "models", "ward.glb")
bpy.ops.export_scene.gltf(filepath=path, export_animations=False, export_skins=False, **SHARED)
print("ward.glb", mb(path), len(objs), "nodes")

# 2. the staff figure with its nine clips, as NLA tracks so the exporter writes one animation per track
arm = bpy.data.objects["nurse_rig"]
parts = [o for o in arm.children if o.type == "MESH" and not o.hide_viewport]
home, active = arm.location.copy(), arm.animation_data.action
arm.location = (0, 0, 0)
ad = arm.animation_data
ad.action = None
for name in CLIPS:
    act = bpy.data.actions[name]
    track = ad.nla_tracks.new()
    track.name = name
    track.strips.new(name, int(act.frame_start), act)
select([arm] + parts)
path = os.path.join(OUT, "models", "staff.glb")
bpy.ops.export_scene.gltf(filepath=path, export_animations=True, export_animation_mode="NLA_TRACKS",
                          export_frame_step=2, export_optimize_animation_size=True, export_skins=True,
                          export_def_bones=False, export_apply=False, **SHARED)
for track in list(ad.nla_tracks):
    ad.nla_tracks.remove(track)
ad.action = active
arm.location = home
print("staff.glb", mb(path), len(parts), "meshes,", len(CLIPS), "clips")

# 3. the layout record
layout = json.loads(scene["twin_layout"])
layout["outfits"] = json.loads(arm["twin_outfits"])
layout["clips"] = CLIPS
path = os.path.join(OUT, "models", "ward-layout.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(layout, f, indent=1)
print("ward-layout.json", mb(path))

# 4. a small HDRI for image-based lighting
img = bpy.data.images.load(HDRI)
img.scale(1024, 512)
img.filepath_raw = os.path.join(OUT, "hdri", "hospital_1k.hdr")
img.file_format = "HDR"
img.save()
bpy.data.images.remove(img)
print("hospital_1k.hdr", mb(os.path.join(OUT, "hdri", "hospital_1k.hdr")))
