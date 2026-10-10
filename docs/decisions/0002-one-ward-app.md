# 0002. One ward app (board + staff view), separate family app

Status: accepted (kickoff)

## Context

The kickoff plan had three front-ends: `station-board`, `staff-pwa` and `family-pwa`, all owned by one person.

## Decision

- `apps/ward`: one Vite/React app with two routes. `/board` is the big screen. `/staff` is the phone view with alerts, ack, fast entry, approvals, medication and the what-if panel. The two routes share the API client, components and state handling.
- `apps/family`: a **separate build**, served by family-gateway, which talks only to the family-gateway API.

## Why

The board and the staff view run on the same network against the same API, so splitting them would duplicate setup and code. The family app must stay separate, because it must not even contain the code or URLs for the ward API (safety invariants 2 and 3).
