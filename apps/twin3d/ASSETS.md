# Assets to download for the twin (outside the repo)

Everything goes under `Desktop\borj-assets\` (not in git; the baked `.glb` is what ships).
Only **CC0 or CC-BY** (ADR 0012). For every file, write the page URL, author and licence into
a `SOURCE.txt` next to it; they are copied into [CREDITS.md](CREDITS.md). No brand logos, no real people.

```
borj-assets/
  backup/    rooms-original.blend          (made already, do not overwrite)
  work/      rooms-step4b-textures.blend   (my latest progress copy)
  Imports/   your downloads (untouched)
  textures/  <slug>/<slug>_diff_<res>.jpg, <slug>_rough_<res>.png|jpg, <slug>_nor_gl_<res>.png
  hdri/      childrens_hospital_2k.hdr
  models/    <name>/ (+ SOURCE.txt)
  characters/ (Mixamo .fbx, + SOURCE.txt)
```

## 1. Textures (Poly Haven, CC0): DONE, downloaded and converted

You downloaded the seven bundles (1K, oak at 2K) into `Imports\`; `prepare_textures.py` made the
plain maps in `textures\<slug>\` and the HDRI is in `hdri\`. What each one turned out to look like:
`floor_tiles_06` dark/light stone checker, `white_stucco` pale grey, `oak_veneer_01` vertical oak,
`leather_white` grey-green taupe (not white; tinted teal for mattresses), `rough_linen` pale blue,
`waffle_pique_cotton` mustard, `fabric_pattern_05` sage check with blue lines. Used as: floor,
walls, door, mattress, bed linen, armchair and stools, curtains. Easy swaps if you dislike one:
another slug from the list below, then re-run `04_materials.py`.

As used now (change a slug in `04_materials.py`, re-run it):

| Surface | Slug | Looks like | Alternatives (all checked on the Poly Haven API) |
|---|---|---|---|
| Floor | `floor_tiles_06` (tile 2.4 m, lightened) | stone checker | `anti_skid_tiles`, `brown_floor_tiles`, `dirty_tiles` |
| Walls | `white_stucco` | pale grey plaster | `plastered_wall`, `beige_wall_001`, `beige_wall_002` |
| Door | `oak_veneer_01` | oak, vertical grain | `ash_veneer`, `okoume_veneer`, `washed_grey_oak_veneer` |
| Mattress | `leather_white` (tinted teal) | taupe leather | `fabric_leather_01`, `fabric_leather_02` |
| Bed linen | `rough_linen` | pale blue linen | `cotton_jersey`, `stretch_poplin` |
| Curtains | `fabric_pattern_05` | sage check | `gingham_check`, `book_pattern` |
| Armchair, stools | `waffle_pique_cotton` | mustard waffle | `velour_velvet`, `wool_boucle` |
| Ceiling | none (plain paint) | | no confirmed CC0 ceiling tile; optionally ambientcg.com "office ceiling", check it says CC0 |

To add another: download the **.blend.zip** bundle (any resolution up to 2K) from
`https://polyhaven.com/a/<slug>`, put it in `Imports\`, unzip each into its own folder, then run
`prepare_textures.py` (command in the README).

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
