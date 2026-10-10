#!/usr/bin/env bash
# Launch the Mock Medical Monitor for Bed B06 (Cardiac / SpO2 / BP / Temp / RR)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="contracts:simulator:${PYTHONPATH}"

echo "=========================================================="
echo " Starting Mock Medical Monitor (Bedside Instruments)"
echo " Ward: W1 | Chamber: 3 (Room R3) | Bed: B06"
echo " Simulated Devices: Cardiac Monitor (ECG), Pulse Oximeter,"
echo "                   Blood Pressure, Thermometer, Resp Rate"
echo " Broker: ${BROKER:-10.42.0.1:1883}"
echo " Profile: ${PROFILE:-normal}"
echo "=========================================================="

PYTHON_BIN="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

exec "$PYTHON_BIN" -m borj_sim.mock_monitor \
    --ward "${WARD:-W1}" \
    --bed "${BED:-B06}" \
    --broker "${BROKER:-10.42.0.1:1883}" \
    --profile "${PROFILE:-normal}" \
    "$@"
