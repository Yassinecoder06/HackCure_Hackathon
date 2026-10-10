# 0006. No NVIDIA Omniverse / OpenUSD; 2D floor plan instead

Status: accepted (kickoff)

## Context

The team considered Omniverse/OpenUSD for a 3D digital twin.

## Decision

Do not use it. The station board shows a **2D floor plan** (SVG) built from `seed/ward-W1.yaml`, with beds coloured by NEWS2, pulsing calls and greyed-out stale data.

## Why

- The whitepaper's "digital twin" is a state model plus discrete-event simulation. The what-if numbers do not depend on 3D geometry.
- Omniverse needs an NVIDIA RTX GPU on every machine that shows it. The dev PC has Intel Iris Xe graphics, and typical demo laptops have no RTX card either.
- It would add a large install, a steep learning curve and a fragile demo, and it clashes with the low-cost pitch for budget-constrained public hospitals.
- A photorealistic twin invites over-claiming what the model predicts.

## Revisit if

Someone has RTX hardware and Omniverse experience, and all "Must" and "Should" items are done. Even then it stays an optional read-only viewer, off the critical path. A browser 3D view (three.js) is the lighter alternative.
