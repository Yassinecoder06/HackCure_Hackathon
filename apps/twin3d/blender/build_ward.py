"""Run all build steps in order and print a short report.

Headless, from the repo root, on a COPY of your scene (it does not save anything unless
you pass --save):
    blender --background <rooms.blend> --python apps/twin3d/blender/build_ward.py [-- --save out.blend]

Inside the open Blender you can also run the numbered scripts one at a time (see README).
"""
import os
import runpy
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    "01_fix_scale_and_archive.py",
    "02_second_bed_and_shell.py",
    "03_bedside_kit.py",
    "04_materials.py",
    "05_station_and_props.py",
]

for step in STEPS:
    print(f"== {step}")
    runpy.run_path(os.path.join(HERE, step))


def ancestors(o):
    while o:
        yield o.name
        o = o.parent


room = [o for o in bpy.context.view_layer.objects
        if o.type == "MESH" and "Sketchfab_model" not in set(ancestors(o))]
print("REPORT meshes:", len(room), "triangles(polys):", sum(len(o.data.polygons) for o in room))
print("REPORT beds:", [o.name for o in bpy.data.objects if o.name.startswith(("bed:All_bed", "bed2:"))])
print("REPORT kits:", [o.name for o in bpy.data.objects if o.name.startswith("kit:")])
print("REPORT screens:", [o.name for o in bpy.data.objects if o.name.startswith("screen_monitor")])
print("REPORT shell:", [o.name for o in bpy.data.collections["Room_shell"].objects])

if "--save" in sys.argv:
    out = sys.argv[sys.argv.index("--save") + 1]
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("saved", out)
