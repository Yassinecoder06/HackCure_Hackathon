#!/usr/bin/env bash
# Launch the Borj Bedside Node on Raspberry Pi (Ward W1, Chamber 3 / Bed B06)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="contracts:bedside-node:${PYTHONPATH}"

echo "=========================================================="
echo " Starting Borj-PiCare Bedside Node"
echo " Ward: W1 | Chamber: 3 (Room R3) | Bed: B06"
echo " Broker: ${BROKER:-10.42.0.1:1883}"
echo " Physical: Green LED=25, Red LED=22, Buttons=17/27, Rotary=23/24"
echo "=========================================================="

exec python3 -m borj_node \
    --ward "${WARD:-W1}" \
    --bed "${BED:-B06}" \
    --broker "${BROKER:-10.42.0.1:1883}" \
    --pin-assist 17 \
    --pin-comfort 27 \
    --pin-led-green 25 \
    --pin-led-red 22 \
    --pin-clk 23 \
    --pin-dt 24 \
    "$@"
