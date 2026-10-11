# Build from the repo root: docker build -f simulator/Dockerfile .
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/contracts:/app/simulator \
    BORJ_SEED_PATH=/app/seed/ward-W1.yaml

COPY simulator/requirements.txt simulator/requirements.txt
RUN pip install --no-cache-dir -r simulator/requirements.txt

COPY contracts contracts
COPY seed seed
COPY simulator/scenarios simulator/scenarios
COPY simulator/borj_sim simulator/borj_sim

# Broker address, account and TLS come from MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_CA_CERT.
CMD ["python", "-m", "borj_sim", "--scenario", "simulator/scenarios/night-shift-peak.yaml", "--speed", "10"]
