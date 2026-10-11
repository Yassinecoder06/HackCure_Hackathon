#!/bin/sh
# Builds the broker's runtime files, then starts mosquitto. Runs as root inside the container.
#   BORJ_MQTT_USERS  "user:password,user:password,..." (.env, written by infra/gen_secrets.py)
set -eu
RUN=/mosquitto/run
mkdir -p "$RUN"
: > "$RUN/passwd"
OLD_IFS=$IFS
IFS=','
for pair in ${BORJ_MQTT_USERS:?missing - run python infra/gen_secrets.py}; do
  mosquitto_passwd -b "$RUN/passwd" "${pair%%:*}" "${pair#*:}"
done
IFS=$OLD_IFS
cp /mosquitto/certs/ca.crt /mosquitto/certs/server.crt /mosquitto/certs/server.key "$RUN/"
cp /mosquitto/config/acl.conf "$RUN/acl.conf"
chown mosquitto:mosquitto "$RUN"/*
chmod 600 "$RUN"/*
exec mosquitto -c /mosquitto/config/mosquitto.conf
