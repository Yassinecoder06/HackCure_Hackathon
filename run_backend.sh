#!/usr/bin/env bash
# Run PiCare backend (Inference engine on 8001 + Twin Server on 8000)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

export BORJ_WARD="${BORJ_WARD:-W1}"
export BORJ_CLOCK_MODE="${BORJ_CLOCK_MODE:-wall}"
export MQTT_HOST="${MQTT_HOST:-localhost}"
export MQTT_PORT="${MQTT_PORT:-8883}"
export MQTT_CA_CERT="${MQTT_CA_CERT:-infra/certs/ca.crt}"
export MQTT_USERNAME="${MQTT_USERNAME:-server}"
export MQTT_PASSWORD="${MQTT_PASSWORD:-${MQTT_PW_SERVER:-}}"
export INFERENCE_URL="${INFERENCE_URL:-http://localhost:8001}"
export BORJ_DB_URL="${BORJ_DB_URL:-sqlite:///$(pwd)/data/borj.sqlite}"
mkdir -p data

echo "=========================================================="
echo " Starting PiCare Core Services (Local Dev Mode)"
echo " Ward: ${BORJ_WARD} | Clock: ${BORJ_CLOCK_MODE}"
echo " Database: ${BORJ_DB_URL}"
echo " MQTT Broker: ${MQTT_HOST}:${MQTT_PORT}"
echo "=========================================================="

echo "Starting Inference Engine on port 8001..."
PYTHONPATH="contracts:inference" .venv/bin/uvicorn borj_inference.main:app --host 0.0.0.0 --port 8001 &
INF_PID=$!

sleep 1

echo "Starting Ward Twin Server on port 8000..."
PYTHONPATH="contracts:server" .venv/bin/uvicorn borj_server.main:app --host 0.0.0.0 --port 8000 &
SRV_PID=$!

cleanup() {
    echo -e "\nStopping backend services..."
    kill "$INF_PID" "$SRV_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
