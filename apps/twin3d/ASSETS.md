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

## 3. Models received (2026-10-11), and what is still missing

Unzipped into `models\` (the zips stay in `Imports\`). All four are used by `05_station_and_props.py`:

| Pack | Used for | Not used |
|---|---|---|
| `hospital-reception-environment` | station counter, 3 monitors, 3 chairs, 1 wall TV, wheelchair | overhead canopy and lettering ("welcome"), waiting chairs, magazine racks, direction and wet-floor signs, wall rails, walls, floor |
| `emergency-cart` | crash cart for the corridor (cut from 412k to 28k polygons) | |
| `ceiling-lowpoly-fluorescent-lamps-with-diffuser` | ceiling light panel (lit variant) for the rooms and corridor | the "off" variant |
| `keyboard.glb` | one keyboard per workstation (47k to 3k triangles) | |

Note: the keyboard has a generic Windows-style symbol on one key, baked into its texture. It is not
legible at the web view's distance. If you want it gone, say so and I paint that key out.

Characters received and used (`06_character.py`): the surgical nurse (rigged, 10 mesh parts, 8 PBR
sets) and nine Mixamo clips (Idle, Walking, Typing, Talking, Sitting Idle, Sit To Stand, Stand To Sit,
Sit To Type, Type To Sit). One model serves all six staff: the web app recolours the shirt, trousers
and scrub cap per role. The surgical mask is hidden (kept in the file). The model's hair is only the
part under the cap, so the cap stays.

Limits of one model for everyone: all staff share one face, hair and shoes, and are all women. If you
later want variety, a second rigged model with the same skeleton names would slot in.

Still needed:

| Priority | What | Search terms | Why |
|---|---|---|---|
| 2 | Patient lying in a bed, clothed and awake (the nurse can be re-used with a hospital-gown recolour if you prefer) | `patient low poly rigged`, `human base mesh male`, `human base mesh female` | so occupied and empty beds differ. Nothing with a shroud or sheet over the face |

Optional later: a few waiting seats for the corridor entrance (the reception pack has some), a wall
sink and sanitiser dispenser.

I build without downloads: the corridor, walls, floor, doors, handrails, call lights.

## 4. Two things I need from you

- **Room A ("Sketchfab_model") and Room B ("Hospital") look like Sketchfab downloads** (their
  object names come from a Sketchfab/FBX import). If you made them, ignore this. If not, send me
  the Sketchfab URL, author and licence of each. A CC-BY-NC or CC-BY-ND model must not ship in
  the demo, and CC-BY needs the credit in `CREDITS.md`.
- Mixamo is Adobe's licence, not CC: free to use in a project, not to redistribute as raw files.
  Keep the `.fbx` out of git; only the baked `.glb` ships.
