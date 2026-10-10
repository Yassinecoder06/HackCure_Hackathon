"""CLI entrypoint for running the Borj Ward Simulator.

Usage:
    python -m borj_sim --scenario simulator/scenarios/deterioration.yaml --speed 10
    python -m borj_sim --scenario simulator/scenarios/normal-night.yaml --dry-run
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from .config import ScenarioConfig, WardConfig
from .runner import SimulationRunner

log = logging.getLogger("borj_sim")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Borj Ward Telemetry Simulator")
    parser.add_argument(
        "--scenario",
        default="simulator/scenarios/deterioration.yaml",
        help="Path to scenario YAML file",
    )
    parser.add_argument(
        "--ward",
        default="seed/ward-W1.yaml",
        help="Path to ward layout YAML file (default: seed/ward-W1.yaml)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Simulation speed multiplier (default: 1.0; 0 for as fast as possible)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Output JSON lines to stdout instead of publishing to MQTT broker",
    )
    parser.add_argument(
        "--broker",
        default="localhost:1883",
        help="MQTT broker host:port (default: localhost:1883)",
    )
    parser.add_argument(
        "--max-min",
        type=int,
        default=None,
        help="Maximum minutes to simulate (optional)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else (logging.WARNING if args.dry_run else logging.INFO)
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        sys.exit(f"Scenario file not found: {scenario_path}")

    scenario = ScenarioConfig.load(scenario_path)

    ward_path = Path(args.ward)
    if not ward_path.exists():
        # Try resolving relative to scenario file
        ward_path = (scenario_path.parent / scenario.ward_file).resolve()
        if not ward_path.exists():
            sys.exit(f"Ward layout file not found: {ward_path}")

    ward = WardConfig.load(ward_path)

    if ":" in args.broker:
        host, port_str = args.broker.split(":", 1)
        port = int(port_str)
    else:
        host = args.broker
        port = 1883

    runner = SimulationRunner(
        scenario=scenario,
        ward=ward,
        speed=args.speed,
        dry_run=args.dry_run,
        broker_host=host,
        broker_port=port,
    )

    def _sig_handler(sig, frame):
        log.info("Simulation interrupted, stopping...")
        runner.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    runner.run(max_minutes=args.max_min)


if __name__ == "__main__":
    main()
