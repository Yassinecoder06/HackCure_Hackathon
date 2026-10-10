# 0003. Raspberry Pi as the bedside node for the demo

Status: accepted (kickoff)

## Context

The whitepaper (4.2) designs one ESP32 node per bed and a Pi as the ward gateway. The team has **one Raspberry Pi, push buttons, LEDs and a speaker**, and no ESP32.

## Decision

- The Pi runs `bedside-node/` (Python with `gpiozero`). It has two buttons (assist, comfort), LEDs for the call states (amber = sent, green = acknowledged, red blink = not sent) and a speaker for pre-recorded phrases.
- It speaks the same MQTT contract an ESP32 node would: it publishes `call` and subscribes to the retained `call/state`.
- Store-and-forward: if no `call/state` arrives within a few seconds, the node shows `not_sent` and plays the "use the emergency bell" phrase. It queues the press locally and replays it with `deliveredLate=true`.
- A mock GPIO mode (gpiozero `MockFactory`) lets the node run on any laptop for development and CI.
- The Pi may also run the gateway when the hardware version of the demo is used.

## Consequences

- The pitch must say that production uses a cheaper, more robust ESP32 per bed, and that the Pi stands in for it in the demo.
- The `firmware/` folder from the kickoff plan is dropped.
