"""Turn downloaded Poly Haven bundles into the small, plain image set the build uses.

Poly Haven's ".blend.zip" bundles hold maps in mixed formats (.exr normals and roughness,
`col_01` instead of `diff`, extra maps we do not need). glTF and the later KTX2 compression
want ordinary 8-bit images, so for each material this keeps only three maps:

    <slug>_diff_<res>.jpg    base colour (sRGB)
    <slug>_rough_<res>.png   roughness  (data, not colour)  [.jpg if it already was one]
    <slug>_nor_gl_<res>.png  OpenGL normal map (data)

Run headless from the repo root (unzip the bundles first, one folder per zip):
    blender --background --python apps/twin3d/blender/prepare_textures.py -- \
        <folder with the unzipped bundles> <output textures folder>

Not kept on purpose: displacement, AO, metal, anisotropy, spec/IOR. glTF has no displacement,
and the fabrics are non-metal; the Principled BSDF defaults are right for them.
Data maps are copied value for value (no colour transform), then read back and compared.
"""
import os
import re
import shutil
import sys

import bpy
import numpy as np

SRC, DST = sys.argv[sys.argv.index("--") + 1:][:2]
EXT = (".jpg", ".jpeg", ".png", ".exr")
KINDS = {          # output kind -> input file-name tokens, best first
    "diff": ("diff", "col_01"),
    "rough": ("rough",),
    "nor_gl": ("nor_gl",),
}


def find(folder, slug, tokens, res):
    for t in tokens:
        for ext in EXT:
            p = os.path.join(folder, f"{slug}_{t}_{res}{ext}")
            if os.path.exists(p):
                return p
    return None


def load(path, srgb):
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    return img


def pixels(img):
    a = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(a)
    return a


def write(img, out_path, fmt, srgb):
    """Save `img` as an 8-bit file by copying its pixel values (no view transform)."""
    out = bpy.data.images.new("out", *img.size, alpha=False, float_buffer=False)
    out.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    px = pixels(img).reshape(-1, 4)
    px[:, 3] = 1.0
    out.pixels.foreach_set(px.ravel())
    out.file_format = fmt
    out.filepath_raw = out_path
    out.save()
    back = bpy.data.images.load(out_path)
    back.colorspace_settings.name = out.colorspace_settings.name
    err = float(np.abs(pixels(back).reshape(-1, 4)[:, :3] - px[:, :3]).mean())
    bpy.data.images.remove(back)
    bpy.data.images.remove(out)
    return err


for folder in sorted(os.listdir(SRC)):
    m = re.match(r"(.+)_(\d+k)$", folder)
    tex_dir = os.path.join(SRC, folder, "textures")
    if not m or not os.path.isdir(tex_dir):
        continue
    slug, res = m.groups()
    out_dir = os.path.join(DST, slug)
    os.makedirs(out_dir, exist_ok=True)
    for kind, tokens in KINDS.items():
        src = find(tex_dir, slug, tokens, res)
        if not src:
            print(f"{slug}: no {kind} map")
            continue
        srgb = kind == "diff"
        ext = os.path.splitext(src)[1].lower()
        if kind == "diff":
            target, fmt = os.path.join(out_dir, f"{slug}_diff_{res}.jpg"), "JPEG"
        else:
            target, fmt = os.path.join(out_dir, f"{slug}_{kind}_{res}.png"), "PNG"
        if ext in (".jpg", ".jpeg") and fmt == "JPEG" or (kind == "rough" and ext in (".jpg", ".jpeg")):
            target = os.path.join(out_dir, f"{slug}_{kind}_{res}.jpg")
            shutil.copyfile(src, target)          # already the right kind of file
            print(f"{slug}: {kind} copied -> {os.path.basename(target)}")
            continue
        img = load(src, srgb)
        err = write(img, target, fmt, srgb)
        bpy.data.images.remove(img)
        print(f"{slug}: {kind} {ext} -> {os.path.basename(target)}  (mean abs error {err:.4f})")
