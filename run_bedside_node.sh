#!/usr/bin/env bash
# Launch the PiCare Bedside Node on Raspberry Pi (Ward W1, Chamber 3 / Bed B06)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="contracts:bedside-node:${PYTHONPATH}"

# Broker account, TLS 1.3 CA and signing keys come from .env and infra/certs (python infra/gen_secrets.py,
# python infra/gen_certs.py). On a Raspberry Pi copy infra/certs/ca.crt and put MQTT_PASSWORD / BORJ_DEVICE_KEYS
# (this node's entry) in the environment instead.
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi
export MQTT_CA_CERT="${MQTT_CA_CERT:-infra/certs/ca.crt}"
export MQTT_USERNAME="${MQTT_USERNAME:-node-${BED:-B06}}"
if [ -z "${MQTT_PASSWORD:-}" ] && [ -n "${BORJ_MQTT_USERS:-}" ]; then
    MQTT_PASSWORD="$(printf '%s' "$BORJ_MQTT_USERS" | tr ',' '
' | sed -n "s/^${MQTT_USERNAME}://p")"
    export MQTT_PASSWORD
fi

echo "=========================================================="
echo " Starting PiCare Bedside Node"
echo " Ward: W1 | Chamber: 3 (Room R3) | Bed: B06"
echo " Broker: ${BROKER:-10.42.0.1:8883}"
echo " Physical: Green LED=25, Red LED=22, Buttons=17/27, Rotary=23/24"
echo "=========================================================="

PYTHON_BIN="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

exec "$PYTHON_BIN" -m borj_node \
    --ward "${WARD:-W1}" \
    --bed "${BED:-B06}" \
    --broker "${BROKER:-10.42.0.1:8883}" \
    --pin-assist 17 \
    --pin-comfort 27 \
    --pin-led-green 25 \
    --pin-led-red 22 \
    --pin-clk 23 \
    --pin-dt 24 \
    "$@"
