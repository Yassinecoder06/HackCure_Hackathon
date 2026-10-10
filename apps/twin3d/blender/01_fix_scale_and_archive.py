"""Step 1: put room "Hospital" at real-world size and archive what we cannot use.

Run inside Blender (Blender MCP or the Scripting tab):
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/01_fix_scale_and_archive.py")

Why:
- The room came out of an FBX export about 1/7 of real size. A hospital bed is about
  2 m long; in the file it was 0.29 m. We measured the bed (2.05 m), the door
  (0.8 x 2.0 m) and the wall height (2.56 m) and they all agree on one factor, so we
  fix it once on the root empty instead of scaling 600 meshes.
- `lab_tools` (342 meshes, 700 000 triangles of ampoules, syringes, an apple dish...)
  is far too heavy for a web view and not needed.
- `dead_body1` is a stretcher with a covered figure. A figure under a sheet looks like
  a corpse, so it must not ship in a patient room. Occupancy is shown by the bedside
  monitor and, later, by proper patient models.

Nothing is deleted. Archived objects stay in the .blend, in a collection that is
excluded from the view layer (hidden, not rendered, not exported).
"""
import importlib
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

importlib.reload(common)   # a long-lived Blender session may hold an older copy

ROOT = "Hospital"
SCALE = 0.07            # metres per file unit, measured (see above)
ARCHIVE = "Unused_original"
ARCHIVE_ROOTS = ["lab_tools", "dead_body1"]

root = bpy.data.objects[ROOT]
if root.get("borj_step1_done"):
    raise RuntimeError("Step 1 already ran on this scene")

root.scale = (SCALE, SCALE, SCALE)

archive = common.get_collection(ARCHIVE)
for name in ARCHIVE_ROOTS:
    for o in common.subtree(bpy.data.objects[name]):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        archive.objects.link(o)
common.get_collection(ARCHIVE, exclude=True)

root["borj_step1_done"] = True
bpy.context.view_layer.update()
