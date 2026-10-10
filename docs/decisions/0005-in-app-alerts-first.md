# 0005. Staff alerts: in-app over WebSocket first, Web Push later

Status: accepted (kickoff)

## Context

Web Push needs HTTPS on the phone. A phone hitting a laptop over plain HTTP on the venue Wi-Fi gets nothing. On iOS, push also requires the app to be installed to the home screen.

## Decision

- **Primary path:** the staff view keeps a WebSocket open to the server. Alerts arrive in real time and play sound and vibration while the app is open. Critical alerts stay on screen until acknowledged.
- **Stretch:** Web Push through an HTTPS tunnel, for when the app is in the background.
- **SMS fallback** for the remote on-call doctor and for staff without a smartphone (whitepaper 6), useful on rural networks ([0008](0008-track-2.md)).
- The pitch states the limit honestly: a web app cannot override do-not-disturb or ring like an alarm, so a native app is the production path.
