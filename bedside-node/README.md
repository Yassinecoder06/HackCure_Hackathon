# Bedside Call Node (Role A)

Raspberry Pi 3 bedside call node: Assist & Comfort push buttons, multi-color LED feedback, speaker audio prompts, local SQLite store-and-forward outbox, and MQTT integration.

Implements **Whitepaper section 4.2**, **ADR 0003**, and **contracts v1**.

---

## 1. Hardware & Wiring (Raspberry Pi 3)

The hardware for the demo runs on a Raspberry Pi 3 Model B:
- **Button 1 (Assist - Clinical):** GPIO 17 (Physical Pin 11) to GND
- **Button 2 (Comfort - Non-clinical):** GPIO 27 (Physical Pin 13) to GND
- **Green LED:** GPIO 22 (Physical Pin 15) via 220Ω resistor to GND
- **Red LED:** GPIO 23 (Physical Pin 16) via 220Ω resistor to GND
- **Speaker:** MAX98357A I2S DAC (Pins 12, 35, 40) or 3.5mm audio jack.

### Pinout Table

| Component | Function | BCM GPIO | Physical Header Pin | Wiring |
|---|---|---|---|---|
| **Push Button 1** | Assist (Nurse help) | GPIO 17 | Pin 11 | Other terminal to GND (Pin 9 or 14) |
| **Push Button 2** | Comfort (Water / assistance) | GPIO 27 | Pin 13 | Other terminal to GND (Pin 9 or 14) |
| **Green LED** | Sent steady / Ack pulsing | GPIO 22 | Pin 15 | Anode to Pin 15, Cathode via 220Ω to GND |
| **Red LED** | Not sent (fast blink) | GPIO 23 | Pin 16 | Anode to Pin 16, Cathode via 220Ω to GND |
| **Speaker / DAC** | Audio prompts & alarms | I2S / 3.5mm | Card 1 / Card 0 | `aplay` PCM output |

---

## 2. Call Feedback States

The patient is always kept informed of call delivery status:

| State | Patient Sees / Hears | System Behaviour |
|---|---|---|
| **Pressed** | Short audio click/beep + brief LED pulse | Event created with unique ULID `eventId` and `callId`. |
| **Sent** | Steady Green / Amber LED | Delivered to ward tower server. |
| **Acknowledged** | Green LED pulses + pleasant chime tone | Staff accepted call in the ward app; help is on the way. |
| **Not Sent** | Fast Red LED blink + buzzer alarm + spoken audio prompt: *"Veuillez utiliser la sonnette d'urgence"* | Link down or no response within 4 s. Call saved in local outbox; replayed with `deliveredLate: true` upon reconnect. |
| **Resolved** | LEDs turn off | Staff resolved the call at bedside. |

> **Safety invariant:** The bedside node is non-authoritative and **never replaces the existing emergency bell**. The hospital's physical call bell remains in place.

---

## 3. Installation & Running

### Requirements
```bash
pip install -r requirements.txt
```

### Running on the Raspberry Pi
```bash
python -m borj_node --ward W1 --bed B06 --broker 10.42.0.1:8883
```

### Options
- `--ward W1`: Ward identifier (default: `W1`)
- `--bed B06`: Bed identifier (default: `B06`)
- `--broker IP:PORT`: MQTT broker address (default: `10.42.0.1:8883`)
- `--pin-assist 17`: GPIO pin for Assist button (default: `17`)
- `--pin-comfort 27`: GPIO pin for Comfort button (default: `27`)
- `--pin-led-green 22`: GPIO pin for Green LED (default: `22`)
- `--pin-led-red 23`: GPIO pin for Red LED (default: `23`)
- `--timeout 4.0`: Timeout before triggering `not_sent` (default: `4.0` s)
- `--test-audio`: Test speaker sounds and exit
- `--mock`: Run with mock GPIO on a development laptop

---

## 4. Systemd Service (Optional Auto-start on Pi)

To run automatically on boot on the Raspberry Pi:
```ini
[Unit]
Description=Borj-PiCare Bedside Call Node
After=network.target

[Service]
Type=simple
User=berry
WorkingDirectory=/home/berry/bedside-node
ExecStart=/usr/bin/python3 -m borj_node --ward W1 --bed B06 --broker 10.42.0.1:8883
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
