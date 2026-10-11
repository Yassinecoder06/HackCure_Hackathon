#!/usr/bin/env python3
"""
fake_mqtt_logs.py
Standalone mock script that generates streaming MQTT telemetry and live event logs
for Borj-PiCare ward devices, beds, parameters, values, and quality flags.

Zero dependencies: uses standard Python 3 libraries only.
Usage:
    python3 scripts/fake_mqtt_logs.py
    python3 scripts/fake_mqtt_logs.py --rate 10    # faster (10 msgs/sec)
    python3 scripts/fake_mqtt_logs.py --bed B06    # filter on bed B06
"""

import argparse
import random
import signal
import sys
import time
from datetime import datetime, timezone

# ANSI Color Codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_WHITE = "\033[37m"
C_BG_RED = "\033[41m\033[37m"

BEDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B10", "B11", "B12"]
DEVICES = {
    "B06": ["DEV-B06-RAD01", "DEV-B06-PI3-BERRY", "DEV-B06-OXIMAX"],
    "B04": ["DEV-B04-RAD02", "DEV-B04-SPO2-ADV", "DEV-B04-NIBP"],
    "B11": ["DEV-B11-VITALS", "DEV-B11-TEMP-PROBE"],
    "B12": ["DEV-B12-RESP-BELT", "DEV-B12-PULSE"],
    "B01": ["DEV-B01-MONITOR"],
    "B02": ["DEV-B02-MONITOR"],
}

PARAMETERS = [
    ("spo2", "%", (93, 100), (86, 92)),
    ("pulse", "bpm", (60, 95), (105, 135)),
    ("resp_rate", "/min", (12, 18), (22, 30)),
    ("sys_bp", "mmHg", (110, 135), (85, 100)),
    ("temp_c", "°C", (36.4, 37.3), (38.5, 39.4)),
    ("consciousness", "", ["alert", "alert", "alert", "voice", "pain"], None),
    ("on_oxygen", "", ["false", "false", "false", "true"], None),
]

QUALITY_FLAGS = [
    ("FRESH_VALID", C_GREEN, "Sensor confidence 0.98, calibrated"),
    ("HMAC_VERIFIED", C_GREEN, "SHA256 signature verified against key store"),
    ("FILTERED_SMOOTH", C_CYAN, "Kalman filter smoothed (noise: -24dB)"),
    ("STALE_WARNING", C_YELLOW, "Age > 30s; awaiting next telemetry frame"),
    ("ANOMALY_DETECTED", C_RED, "Rapid rate-of-change delta > threshold"),
    ("INTERPOLATED", C_MAGENTA, "Time-sync alignment, zero packet loss"),
]


def generate_sig():
    return "".join(random.choices("0123456789abcdef", k=8))


def print_header(ward: str = "W1"):
    print(f"{C_BOLD}{C_CYAN}======================================================================================================{C_RESET}")
    print(f"{C_BOLD}{C_WHITE} 🏥 BORJ-PICARE MQTT BROKER & WARD TELEMETRY INGESTION STREAM (SIMULATED LIVE EVENT FEED){C_RESET}")
    print(f"{C_DIM} Protocol: MQTT 3.1.1 over TLS 1.3 | Ward: {ward} | Port: 8883 | Invariant 13 HMAC: ACTIVE{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}======================================================================================================{C_RESET}")
    print(
        f"{C_BOLD}{C_WHITE}"
        f"{'TIMESTAMP':<24} "
        f"{'MQTT TOPIC':<26} "
        f"{'DEVICE':<17} "
        f"{'BED':<5} "
        f"{'PARAM':<14} "
        f"{'VALUE':<12} "
        f"{'QUALITY FLAG':<18} "
        f"{'HMAC':<10}"
        f"{C_RESET}"
    )
    print(f"{C_DIM}{'-'*114}{C_RESET}")


def stream_logs(target_bed: str = None, rate: float = 3.0):
    count = 0
    running = True

    def sig_handler(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    print_header()

    while running:
        count += 1
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"
        bed = target_bed if target_bed else random.choice(["B06", "B04", "B11", "B12", "B01", "B02"])
        dev_list = DEVICES.get(bed, [f"DEV-{bed}-NODE-01"])
        device = random.choice(dev_list)

        # Occasional special event: Bedside call button or cadence burst (especially on B06)
        r = random.random()
        if r < 0.05:
            # Bedside call button event
            topic = f"borj/W1/bed/{bed}/call"
            param = "call_button"
            val_str = "PRESSED"
            flag_name, flag_color, _ = ("CALL_ALERT", C_YELLOW, "Patient assistance request")
            sig = generate_sig()
            print(
                f"{C_DIM}{ts}{C_RESET} "
                f"{C_YELLOW}{topic:<26}{C_RESET} "
                f"{C_CYAN}{device:<17}{C_RESET} "
                f"{C_BOLD}{C_WHITE}{bed:<5}{C_RESET} "
                f"{C_YELLOW}{param:<14}{C_RESET} "
                f"{C_BOLD}{C_YELLOW}{val_str:<12}{C_RESET} "
                f"{flag_color}[{flag_name}]{C_RESET}{' ' * (16 - len(flag_name))} "
                f"{C_DIM}sig:{sig}{C_RESET}"
            )
        elif r < 0.08 and bed == "B06":
            # Acute Triple-Tap Cadence Burst event on Bed B06
            topic = f"borj/W1/bed/{bed}/call/burst"
            param = "cadence_burst"
            val_str = "3 taps / 0.8s"
            flag_name, flag_color, _ = ("EMERGENCY_PEAK", C_BG_RED, "High frequency alert")
            sig = generate_sig()
            print(
                f"{C_DIM}{ts}{C_RESET} "
                f"{C_RED}{topic:<26}{C_RESET} "
                f"{C_CYAN}{device:<17}{C_RESET} "
                f"{C_BOLD}{C_RED}{bed:<5}{C_RESET} "
                f"{C_RED}{param:<14}{C_RESET} "
                f"{C_BOLD}{C_RED}{val_str:<12}{C_RESET} "
                f"{flag_color}[{flag_name}]{C_RESET}{' ' * max(0, 16 - len(flag_name))} "
                f"{C_DIM}sig:{sig}{C_RESET}"
            )
        else:
            # Standard telemetry parameter reading
            param_tuple = random.choice(PARAMETERS)
            param_name, unit, normal_range, acute_range = param_tuple
            topic = f"borj/W1/bed/{bed}/obs"

            is_acute = acute_range is not None and random.random() < 0.12
            if isinstance(normal_range, list):
                val = random.choice(normal_range)
                val_str = str(val)
                val_color = C_WHITE
            elif isinstance(normal_range[0], float):
                rng = acute_range if is_acute else normal_range
                val = round(random.uniform(rng[0], rng[1]), 1)
                val_str = f"{val} {unit}"
                val_color = C_RED if is_acute else C_GREEN
            else:
                rng = acute_range if is_acute else normal_range
                val = random.randint(rng[0], rng[1])
                val_str = f"{val} {unit}"
                val_color = C_RED if is_acute else C_GREEN

            if is_acute:
                flag_name, flag_color, _ = ("ACUTE_THRESHOLD", C_RED, "Deterioration metric")
            else:
                flag_name, flag_color, _ = random.choice(QUALITY_FLAGS[:3])

            sig = generate_sig()

            print(
                f"{C_DIM}{ts}{C_RESET} "
                f"{C_BLUE}{topic:<26}{C_RESET} "
                f"{C_CYAN}{device:<17}{C_RESET} "
                f"{C_BOLD}{C_WHITE}{bed:<5}{C_RESET} "
                f"{C_WHITE}{param_name:<14}{C_RESET} "
                f"{val_color}{val_str:<12}{C_RESET} "
                f"{flag_color}[{flag_name}]{C_RESET}{' ' * max(0, 16 - len(flag_name))} "
                f"{C_DIM}sig:{sig}{C_RESET}"
            )

        # Sleep interval based on rate
        interval = (1.0 / rate) * random.uniform(0.7, 1.3)
        time.sleep(interval)

    print(f"\n{C_BOLD}{C_CYAN}[INFO]{C_RESET} Stream terminated cleanly. Total messages generated: {C_BOLD}{count}{C_RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="Simulate live MQTT telemetry events (device, bed, parameter, value, quality flag)"
    )
    parser.add_argument("--bed", type=str, default=None, help="Filter on a specific bed (e.g. B06)")
    parser.add_argument("--rate", type=float, default=3.5, help="Messages per second (default: 3.5)")
    args = parser.parse_args()

    stream_logs(target_bed=args.bed, rate=args.rate)


if __name__ == "__main__":
    main()
