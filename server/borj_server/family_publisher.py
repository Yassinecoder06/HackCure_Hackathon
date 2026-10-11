"""Family publisher: forwards approved, allow-listed payloads OUTBOUND to family-gateway.

Run as its own process/container on both the ward and DMZ networks (docker-compose.yml):
    python -m borj_server.family_publisher

- It opens no listening socket: nothing on the DMZ can connect into the ward (safety invariant 3).
- It forwards ONLY the `outbound.payload` stored on family events, which the server built from the
  allow-list and validated against the family-* schemas at approval time. It re-validates before
  sending and never reads anything else from an event (invariant 2).
- Store-and-forward: delivery is recorded in `family_outbox`. Anything not yet accepted is retried
  (rural networks, gateway restarts). family-gateway ingest is idempotent by id, so a retry is safe.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import borj_contracts as bc
import httpx
from sqlalchemy import Column, MetaData, String, Table, select

from .store import EventStore
from .timeutil import format_ts, utcnow

log = logging.getLogger("borj_server.family_publisher")
SCHEMA_FOR_TARGET = {"invites": "family-invite", "updates": "family-update", "revocations": "family-revocation"}

_meta = MetaData()
outbox = Table(
    "family_outbox", _meta,
    Column("event_id", String(26), primary_key=True),
    Column("delivered_at", String(32), nullable=False),
)


@dataclass(frozen=True)
class OutboundItem:
    event_id: str
    target: str
    payload: dict[str, Any]


def outbound_items(store: EventStore) -> list[OutboundItem]:
    """Every outbound payload in the log, in event order. Only `outbound` is read from each event."""
    items = []
    for event in store.events():
        if event.schema == "family-event" and "outbound" in event.payload:
            out = event.payload["outbound"]
            items.append(OutboundItem(event.payload["eventId"], out["target"], out["payload"]))
    return items


class FamilyPublisher:
    def __init__(self, store: EventStore, http: httpx.Client, token: str) -> None:
        self.store = store
        self.http = http
        self.token = token
        _meta.create_all(store.engine)

    def delivered(self) -> set[str]:
        with self.store.engine.connect() as conn:
            return set(conn.execute(select(outbox.c.event_id)).scalars())

    def publish_once(self) -> int:
        """Send everything not yet delivered, oldest first. Stops at the first failure to keep order."""
        done = self.delivered()
        sent = 0
        for item in outbound_items(self.store):
            if item.event_id in done:
                continue
            bc.validate(SCHEMA_FOR_TARGET[item.target], item.payload)  # never send anything off the allow-list
            try:
                resp = self.http.post(f"/ingest/v1/{item.target}", json=item.payload,
                                      headers={"Authorization": f"Bearer {self.token}"})
            except httpx.HTTPError as exc:
                log.warning("family-gateway unreachable, will retry: %s", exc)
                return sent
            if resp.status_code >= 300:
                log.warning("family-gateway refused %s (%s), will retry", item.event_id, resp.status_code)
                return sent
            with self.store.engine.begin() as conn:
                conn.execute(outbox.insert().values(event_id=item.event_id, delivered_at=format_ts(utcnow())))
            sent += 1
        return sent


def main() -> None:  # pragma: no cover - process entry point, exercised in compose
    from .crypto import DataCipher

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store = EventStore(os.environ["BORJ_DB_URL"], DataCipher.from_env())
    http = httpx.Client(base_url=os.environ["FAMILY_GATEWAY_URL"], timeout=10)
    publisher = FamilyPublisher(store, http, os.environ["FAMILY_PUBLISHER_TOKEN"])
    interval = float(os.environ.get("FAMILY_PUBLISH_INTERVAL_S", "2"))
    log.info("family publisher started (outbound only, no listening port)")
    while True:
        try:
            if publisher.publish_once():
                log.info("forwarded pending family payloads")
        except Exception:
            log.exception("publish cycle failed")
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover
    main()
