"""CLI entrypoint for running the Borj Bedside Node.

Usage:
    python -m borj_node --ward W1 --bed B06 --broker 10.42.0.1:1883
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from .node import BedsideNode

log = logging.getLogger("borj_node")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Borj Bedside Call Node (Raspberry Pi 3)")
    parser.add_argument("--ward", default="W1", help="Ward ID (default: W1)")
    parser.add_argument("--bed", default="B06", help="Bed ID (default: B06)")
    parser.add_argument("--broker", default="10.42.0.1:1883", help="MQTT broker host:port (default: 10.42.0.1:1883)")
    parser.add_argument("--pin-assist", type=int, default=17, help="GPIO pin for Assist button (default: 17)")
    parser.add_argument("--pin-comfort", type=int, default=27, help="GPIO pin for Comfort button (default: 27)")
    parser.add_argument("--pin-led-green", type=int, default=25, help="GPIO pin for Green LED (default: 25)")
    parser.add_argument("--pin-led-red", type=int, default=22, help="GPIO pin for Red LED (default: 22)")
    parser.add_argument("--pin-led-amber", type=int, default=None, help="GPIO pin for Amber LED (optional)")
    parser.add_argument("--pin-clk", type=int, default=23, help="GPIO pin for Rotary Encoder CLK (default: 23)")
    parser.add_argument("--pin-dt", type=int, default=24, help="GPIO pin for Rotary Encoder DT (default: 24)")
    parser.add_argument("--db", default="node_outbox.db", help="SQLite outbox database path (default: node_outbox.db)")
    parser.add_argument("--timeout", type=float, default=4.0, help="Receipt timeout in seconds (default: 4.0)")
    parser.add_argument("--mock", action="store_true", help="Force mock GPIO mode (for laptops / tests)")
    parser.add_argument("--no-audio", action="store_true", help="Disable audio cues")
    parser.add_argument("--test-audio", action="store_true", help="Play sound effects test and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if args.test_audio:
        from .audio import AudioManager

        log.info("Testing audio cues...")
        audio = AudioManager(enabled=True)
        log.info("1. Playing Beep...")
        audio.play_beep()
        time.sleep(1.0)
        log.info("2. Playing Chime...")
        audio.play_chime()
        time.sleep(1.5)
        log.info("3. Playing Buzzer...")
        audio.play_buzzer()
        time.sleep(1.5)
        log.info("4. Playing Emergency Voice Prompt...")
        audio.play_emergency_bell()
        time.sleep(3.0)
        log.info("Audio test finished.")
        sys.exit(0)

    if ":" in args.broker:
        host, port_str = args.broker.split(":", 1)
        port = int(port_str)
    else:
        host = args.broker
        port = 1883

    print("=" * 65)
    print(f"  Borj-PiCare Bedside Node: Ward {args.ward} / Bed {args.bed}")
    print(f"  Broker: {host}:{port}")
    print(f"  Buttons: Assist=GPIO {args.pin_assist}, Comfort=GPIO {args.pin_comfort}")
    print(f"  LEDs: Green=GPIO {args.pin_led_green}, Red=GPIO {args.pin_led_red}")
    print(f"  Encoder: CLK=GPIO {args.pin_clk}, DT=GPIO {args.pin_dt}")
    print(f"  Outbox: {args.db}")
    print("=" * 65)

    node = BedsideNode(
        ward=args.ward,
        bed=args.bed,
        broker_host=host,
        broker_port=port,
        pin_assist=args.pin_assist,
        pin_comfort=args.pin_comfort,
        pin_led_green=args.pin_led_green,
        pin_led_red=args.pin_led_red,
        pin_led_amber=args.pin_led_amber,
        pin_clk=args.pin_clk,
        pin_dt=args.pin_dt,
        db_path=args.db,
        receipt_timeout_s=args.timeout,
        mock_gpio=args.mock,
        audio_enabled=not args.no_audio,
    )

    def _sig_handler(sig, frame):
        print("\nStopping bedside node...")
        node.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    node.start()
    print("Bedside node is running. Press Ctrl+C to terminate.")

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _sig_handler(None, None)


if __name__ == "__main__":
    main()
