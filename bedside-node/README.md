# bedside-node/ (owner: A)

Raspberry Pi bedside call node: assist and comfort buttons, LEDs, speaker. **Not implemented yet.** See [ADR 0003](../docs/decisions/0003-pi-bedside-node.md) and [`docs/roles/A-edge.md`](../docs/roles/A-edge.md), P2.

- Python + `gpiozero`; mock GPIO mode for laptops and CI.
- Publishes `borj/{ward}/{bed}/call`. Drives the LEDs from the retained `borj/{ward}/{bed}/call/state`.
- Feedback: pressed = beep + pulse, sent = amber, acknowledged = green, not sent = red blink + buzzer + "please use the emergency bell" phrase, with local queueing and late replay.
- **Never the only route**: the ward's existing emergency bell stays in use.
- Add the wiring diagram (GPIO pins) here once built.
