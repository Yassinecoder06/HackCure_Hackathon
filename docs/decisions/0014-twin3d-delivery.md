# 0014. 3D twin: what was built, and where it differs from ADR 0012

Status: accepted (2026-10-11). Refines [0012](0012-3d-twin.md).

## Context

ADR 0012 chose Blender plus React Three Fiber, with baked lighting, KTX2 textures and a path-traced photo mode.
The twin had to be finished in one sitting, so some of that was cut and a few decisions were made that the
code does not explain by itself.

## Decisions

- **Real-time lighting, no bake.** Image-based lighting from a hospital HDRI, N8AO ambient occlusion, bloom on the glowing
  screens, AgX tone mapping. Baking needs a second UV set and lightmaps for each of the merged rooms. It is the first upgrade.
- **WebP textures instead of KTX2.** Blender cannot write KTX2 and `toktx` is not in this build. WebP is supported by
  every browser's `GLTFLoader` and is much smaller than PNG. Geometry is Draco-compressed.
- **Photo mode = maximum quality capture**, not path tracing. It keeps the demo stable on any GPU.
- **One model for all staff.** The nurse FBX has no usable armature in Blender, so the rig was rebuilt from the file's skin
  clusters (`blender/06_character.py`). Roles differ only by the colour of shirt, trousers and cap, set at runtime from a
  neutral texture (a blue texture cannot be turned white by multiplying).
- **Rooms are merged per material and copied.** Six rooms of about 400 objects each would be 2400 draw calls. Each room
  becomes ~20 meshes and is copied six times with shared mesh data, so the file does not grow with the room count.
- **Staff movement is inferred.** The API has no staff coordinates. A person walks to a bed when they are the
  `acknowledgedBy` of that bed's open call, and walks back when it resolves. This shows who is answering which call; it is
  not location tracking and says so in the README.
- **Display only, enforced by a test.** `src/logic/logic.test.ts` fails if any source file sends a request other than the
  login, calls `WebSocket.send`, or uses browser storage (safety invariants 1 and 7).
- **A synthetic stream, only on request.** `?demo=1` opens a generated stream for screenshots and offline demos. It is
  labelled DEMO DATA on screen and is never a fallback for a failed connection (invariant 5: never present invented data as real).
- **The dev proxy target is configurable** (`TWIN_API_TARGET`), because port 8000 is reserved by Windows on some machines.
- **No React `StrictMode`.** Its dev-only double mount unmounts the WebGL canvas during render and logs an error.

## Consequences

- The look is good but not photo-baked. Adding the bake later changes the Blender side only (steps 7 and 8), not the app.
- The twin shows scores, so it carries the confidence and the reasons next to them (invariant 12) and an "advisory" line.
- The source rooms' and packs' licences still have to be filled in `apps/twin3d/CREDITS.md` before the model ships outside the team.
