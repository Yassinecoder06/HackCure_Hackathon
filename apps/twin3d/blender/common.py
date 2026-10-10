"""Small helpers shared by the Blender build scripts (no logic of its own).

Each numbered script adds `this folder` to sys.path and does `import common`.
Run the scripts with runpy so that `__file__` is set:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/03_bedside_kit.py")
"""
import bpy
from mathutils import Vector


def subtree(obj):
    """The object and all of its descendants."""
    items = [obj]
    for child in obj.children:
        items += subtree(child)
    return items


def world_bbox(objs):
    """(min corner, max corner) in world metres of all the meshes in `objs`."""
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = Vector(min(p[i] for p in pts) for i in range(3))
    hi = Vector(max(p[i] for p in pts) for i in range(3))
    return lo, hi


def linked_copy(src_root, new_name, matrix_world=None, collection=None):
    """Copy an object tree. Mesh data is shared with the original ("linked"), so
    the copy costs no extra memory and no extra file size.

    matrix_world: where the copy's root goes (default: same place as the original).
    collection:   link the copies here instead of into the original's collections.
    """
    mapping = {}
    for o in subtree(src_root):
        n = o.copy()
        targets = [collection] if collection else list(o.users_collection)
        for c in targets:
            c.objects.link(n)
        mapping[o] = n
    for o, n in mapping.items():
        if o.parent in mapping:
            n.parent = mapping[o.parent]   # keep the copy's tree self-contained
    new_root = mapping[src_root]
    new_root.name = new_name
    if matrix_world is not None:
        bpy.context.view_layer.update()
        new_root.matrix_world = matrix_world
    return new_root


def get_collection(name, parent=None, exclude=False):
    """Fetch or create a collection under the scene (or `parent`), optionally hidden."""
    coll = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if name not in parent.children:
        parent.children.link(coll)
    if exclude:
        bpy.context.view_layer.layer_collection.children[name].exclude = True
    return coll
