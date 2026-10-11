#!/usr/bin/env bash
# Launch the Mock Medical Monitor for Bed B06 (Cardiac / SpO2 / BP / Temp / RR)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="contracts:simulator:${PYTHONPATH}"

# Broker account, TLS 1.3 CA and signing keys come from infra/.env and infra/certs (python infra/gen_secrets.py,
# python infra/gen_certs.py). On a Raspberry Pi copy infra/certs/ca.crt and put MQTT_PASSWORD / BORJ_DEVICE_KEYS
# (this node's entry) in the environment instead.
if [ -f "infra/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source infra/.env
    set +a
fi
export MQTT_CA_CERT="${MQTT_CA_CERT:-infra/certs/ca.crt}"
export MQTT_USERNAME="${MQTT_USERNAME:-sim}"
export MQTT_PASSWORD="${MQTT_PASSWORD:-${MQTT_PW_SIM:-}}"

echo "=========================================================="
echo " Starting Mock Medical Monitor (Bedside Instruments)"
echo " Ward: W1 | Chamber: 3 (Room R3) | Bed: B06"
echo " Simulated Devices: Cardiac Monitor (ECG), Pulse Oximeter,"
echo "                   Blood Pressure, Thermometer, Resp Rate"
echo " Broker: ${BROKER:-10.42.0.1:8883}"
echo " Profile: ${PROFILE:-normal}"
echo "=========================================================="

PYTHON_BIN="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

exec "$PYTHON_BIN" -m borj_sim.mock_monitor \
    --ward "${WARD:-W1}" \
    --bed "${BED:-B06}" \
    --broker "${BROKER:-10.42.0.1:8883}" \
    --profile "${PROFILE:-normal}" \
    "$@"
