# Credits and licences (3D twin)

Rule ([ADR 0012](../../docs/decisions/0012-3d-twin.md)): CC0 or CC-BY only, PBR textures at 2K max,
no brand logos, no real people. **Every asset used in the shipped `.glb` is listed here with
source, author and licence.** An asset that is not listed here must not be in the export.

| Asset | Used for | Source | Author | Licence | State |
|---|---|---|---|---|---|
| Room "Hospital" (Room B), also the `bed:All_bed` bed, cabinets, curtains, trolleys, door | base room | **to confirm** (looks like a Sketchfab import) | **to confirm** | **to confirm** | blocking: do not ship until filled |
| Room "Sketchfab_model" (Room A): monitor cart, IV pole, headwall unit | bedside kit | **to confirm** (Sketchfab import) | **to confirm** | **to confirm** | blocking: do not ship until filled |
| `screen_monitor`, shell walls and ceiling, materials table | our own geometry and scripts | this repo | the team | project licence | done |
| Poly Haven textures: `floor_tiles_06`, `white_stucco`, `oak_veneer_01`, `leather_white`, `rough_linen`, `waffle_pique_cotton`, `fabric_pattern_05` | floor, walls, door, mattress, linen, armchair, curtains | https://polyhaven.com/a/<slug> | see each page (author names to copy in) | CC0 | in use (1K, oak 2K) |
| Poly Haven HDRI `childrens_hospital` | lighting, reflections | https://polyhaven.com/a/childrens_hospital | see page (author name to copy in) | CC0 | downloaded (2K) |
| `hospital-reception-environment` pack (counter, monitors, chairs, TV, wheelchair, textures) | nurse station | **to confirm** | **to confirm** | CC0 or self-made (owner's statement, 2026-10-11) | in use. Author and URL still to fill |
| `emergency-cart` (USDZ) | crash cart | **to confirm** (its parts are named like a Sketchfab export) | **to confirm** | CC0 or self-made (owner's statement) | in use. Author and URL still to fill |
| `ceiling-lowpoly-fluorescent-lamps-with-diffuser` | ceiling light panel | **to confirm** | **to confirm** | CC0 or self-made (owner's statement) | in use. Author and URL still to fill |
| `keyboard.glb` | workstation keyboards | **to confirm** (Sketchfab export) | **to confirm** | CC0 or self-made (owner's statement) | in use. Author and URL still to fill |
| Mixamo characters and animations | nurses, doctor | https://www.mixamo.com | Adobe | Adobe Mixamo terms (not CC) | not downloaded yet |

Removed from the scene on purpose, not shipped: the `dead_body1` stretcher figure and the
`lab_tools` set (kept only in the hidden `Unused_original` collection of the working `.blend`).
