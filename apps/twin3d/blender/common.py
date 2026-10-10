"""Small helpers shared by the Blender build scripts.

Each numbered script adds `this folder` to sys.path and does `import common`.
Run the scripts with runpy so that `__file__` is set:
    import runpy; runpy.run_path(r"<repo>/apps/twin3d/blender/03_bedside_kit.py")
"""
import collections

import bmesh
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


def delete_tree(obj):
    """Delete an object tree and any mesh data nothing else uses."""
    objs = subtree(obj)
    meshes = {o.data for o in objs if o.type == "MESH"}
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for m in meshes:
        if m.users == 0:
            bpy.data.meshes.remove(m)


# ------------------------------------------------------------------ geometry diet
def poly_budget(obj, per_metre=8000, lo=150, hi=3000):
    """Polygons a part deserves: small parts get few, big ones up to `hi`.
    Measured in world metres (obj.dimensions ignores the parent's scale)."""
    a, b = world_bbox([obj])
    return min(hi, max(lo, int(per_metre * max(b - a))))


def decimated(obj, budget):
    """Give `obj` its own, lighter mesh of about `budget` polygons (the original mesh data
    is left alone). Duplicated vertices are welded first: imported files often leave many
    unwelded, which stops the collapse from reaching its target."""
    n = len(obj.data.polygons)
    if n <= budget:
        return
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


def loose_parts(obj):
    """Split a mesh object into one new object per connected piece (the original is kept).
    Returns the new objects, in the same collections, with the same transform."""
    me = obj.data
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for p in me.polygons:
        root = find(p.vertices[0])
        for v in p.vertices[1:]:
            parent[find(v)] = root
    groups = collections.defaultdict(list)
    for p in me.polygons:
        groups[find(p.vertices[0])].append(p.index)
    parts = []
    for n, face_ids in enumerate(groups.values()):
        bm = bmesh.new()
        bm.from_mesh(me)
        keep = set(face_ids)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        mesh = bpy.data.meshes.new(f"{me.name}.part{n}")
        bm.to_mesh(mesh)
        bm.free()
        for m in me.materials:
            mesh.materials.append(m)
        part = bpy.data.objects.new(f"{obj.name}.part{n}", mesh)
        part.matrix_world = obj.matrix_world
        for c in obj.users_collection:
            c.objects.link(part)
        parts.append(part)
    return parts


# --------------------------------------------------------------------- screens
def screen_quad(src, name, collection, inset=0.10, to_frame=None, toward=None):
    """A flat, UV-mapped quad on the largest flat face of `src` (a display's front), pushed
    2 mm out so it does not z-fight. `inset` leaves that fraction of the face as bezel on
    each side. `toward` (a world direction) picks the face looking that way when a display's
    back is as large as its front (a wall TV: pass the direction to the room). Vertices are
    in world metres (or `to_frame @ world` if given). Returns the new, unparented object; the
    web app swaps its texture for live data."""
    nm = src.matrix_world.to_3x3()
    area = collections.defaultdict(float)
    faces = collections.defaultdict(list)
    for p in src.data.polygons:
        n = (nm @ p.normal).normalized()
        key = tuple(round(v, 1) for v in n)
        area[key] += p.area
        faces[key].append(p)
    candidates = [k for k in area if toward is None or Vector(k).dot(toward) > 0.3] or list(area)
    key = max(candidates, key=area.get)
    pts = [src.matrix_world @ src.data.vertices[i].co for p in faces[key] for i in p.vertices]
    n = Vector(key).normalized()
    right = Vector((0, 0, 1)).cross(n).normalized()   # as seen by someone facing the screen
    up = n.cross(right)
    s = [v.dot(right) for v in pts]
    t = [v.dot(up) for v in pts]
    d = sum(v.dot(n) for v in pts) / len(pts) + 0.002
    ds, dt = (max(s) - min(s)) * inset, (max(t) - min(t)) * inset
    s0, s1, t0, t1 = min(s) + ds, max(s) - ds, min(t) + dt, max(t) - dt
    corners = [right * a + up * b + n * d for a, b in ((s0, t0), (s1, t0), (s1, t1), (s0, t1))]
    if to_frame is not None:
        corners = [to_frame @ c for c in corners]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(corners, [], [(0, 1, 2, 3)])
    mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj
