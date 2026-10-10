# Assets to download for the twin (outside the repo)

Everything goes under `Desktop\borj-assets\` (not in git; the baked `.glb` is what ships).
Only **CC0 or CC-BY** (ADR 0012). For every file, write the page URL, author and licence into
a `SOURCE.txt` next to it; they are copied into [CREDITS.md](CREDITS.md). No brand logos, no real people.

```
borj-assets/
  backup/    rooms-original.blend          (made already, do not overwrite)
  work/      rooms-step4-materials.blend   (made already, my progress copy)
  textures/  <slug>/<slug>_diff_2k.jpg, <slug>_rough_2k.jpg, <slug>_nor_gl_2k.jpg
  hdri/      childrens_hospital_2k.hdr
  models/    <name>/ (+ SOURCE.txt)
  characters/ (Mixamo .fbx, + SOURCE.txt)
```

## 1. Textures (Poly Haven, CC0). Slugs checked against the Poly Haven API

On `https://polyhaven.com/a/<slug>` choose **2K**, **JPG**, and download Diffuse, Rough and
**nor_gl** (OpenGL normal, the one Blender and glTF expect). 2K is the maximum (ADR 0012).

| Used for | Slug | Notes |
|---|---|---|
| Floor (rooms and corridor) | `floor_tiles_06` | tagged clean, indoor. Alternative: `anti_skid_tiles` |
| Walls | `white_stucco` | tagged indoor. Alternatives: `plastered_wall`, `beige_wall_001` |
| Door and cabinet wood | `oak_veneer_01` | alternatives `ash_veneer`, `okoume_veneer` (lighter) |
| Mattress / vinyl | `leather_white` | |
| Bed sheets / blanket | `waffle_pique_cotton` | alternative `rough_linen` |
| Privacy curtains | `rough_linen` | alternative `stretch_poplin` |
| Chair / armchair upholstery | `fabric_pattern_05` | check the look on the page; any plain fabric works |
| Ceiling | none confirmed | plain paint is fine. Optional: on ambientcg.com search "office ceiling" and check the page says CC0 |

After you download, tell me and I set the `tex=` slugs in `blender/04_materials.py`; the script
wires the maps in and re-measures the tiling in metres.

## 2. HDRI (lighting and reflections in the web view)

- `childrens_hospital`, Poly Haven, CC0 (tagged indoor, artificial light). Download the **2K .hdr**.
  It is a real hospital interior, so reflections on chrome and glass look right. If it is too
  contrasty: `blender_institute` or `brown_photostudio_03` (low contrast).

## 3. Models to find (search terms)

Look on Sketchfab (filter: Downloadable, License = CC0 or CC-BY), Poly Haven models, Quaternius and
Kenney (both CC0). Keep each under about 30k triangles; prefer `.glb`/`.gltf`, `.fbx` also fine.

| Priority | What | Search terms | Why |
|---|---|---|---|
| 1 | Nurse station desk | `nurse station`, `reception desk`, `hospital reception counter` | the seed's `station` at x = 0 |
| 1 | Office chair, PC monitors, keyboard | `office chair low poly`, `computer monitor`, `desktop pc` | station dressing |
| 1 | Nurse / doctor / care assistant characters (rigged) | `nurse rigged low poly`, `doctor scrubs rigged`, `scrubs character` | seed has CN1, N1, N2, N3, CA1, DR1 |
| 1 | Animations for them (Mixamo, free Adobe account) | `Idle`, `Walking`, `Typing`, `Talking` | nurses walk to the call. Pick any neutral character, I recolour to scrubs |
| 2 | Patient lying in bed (clothed, awake) | `patient low poly rigged`, `human base mesh male`, `human base mesh female` | so occupied and empty beds differ. Do **not** pick anything with a shroud or sheet over the face |
| 2 | Medicine / crash cart | `crash cart`, `emergency trolley`, `medicine cart` | corridor dressing |
| 2 | Wheelchair | `wheelchair` | corridor dressing |
| 2 | Hand sanitiser dispenser | `hand sanitizer dispenser wall` | one per door |
| 2 | Wall clock | `wall clock simple` | station and rooms |
| 2 | Pedal waste bin, sharps container | `pedal bin`, `sharps container` | rooms |
| 3 | Corridor handrail | `wall handrail`, `grab bar` | corridor |
| 3 | Ceiling light panel | `ceiling light panel led`, `recessed ceiling light` | the bake needs visible sources |
| 3 | Wall sink, mirror | `hospital sink`, `wall mounted sink` | rooms |
| 3 | Oxygen cylinder, medical gas outlet | `oxygen cylinder`, `medical gas outlet` | headwall detail |
| 3 | Plants, visitor chairs | `visitor chair`, `potted plant` | station and corridor warmth |

I build without downloads: the corridor, walls, floor, doors, call lights, the station TV (as a
separate screen mesh) and the call-light fixtures.

## 4. Two things I need from you

- **Room A ("Sketchfab_model") and Room B ("Hospital") look like Sketchfab downloads** (their
  object names come from a Sketchfab/FBX import). If you made them, ignore this. If not, send me
  the Sketchfab URL, author and licence of each. A CC-BY-NC or CC-BY-ND model must not ship in
  the demo, and CC-BY needs the credit in `CREDITS.md`.
- Mixamo is Adobe's licence, not CC: free to use in a project, not to redistribute as raw files.
  Keep the `.fbx` out of git; only the baked `.glb` ships.
