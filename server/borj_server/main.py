"""FastAPI app: wires the event store, ward clock, ingest pipeline, MQTT and routes.

Run locally:  uvicorn borj_server.main:app --reload   (with contracts/ and server/ on PYTHONPATH)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import router
from .clock import Clock
from .config import Settings
from .ingest import Ingestor
from .mqtt import MqttListener
from .store import EventStore
from .twin.layout import WardLayout

log = logging.getLogger("borj_server")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = EventStore(settings.db_path)
        ingestor = Ingestor(WardLayout.load(settings.seed_path), store, Clock(settings.clock_mode))
        ingestor.rebuild()  # restore the twin from the persisted log
        app.state.ingestor = ingestor
        listener = None
        if settings.mqtt_enabled:
            listener = MqttListener(ingestor, settings.mqtt_host, settings.mqtt_port)
            listener.start()
        log.info("ward %s ready: %d events replayed", settings.ward, store.count())
        try:
            yield
        finally:
            if listener is not None:
                listener.stop()
            store.close()

    app = FastAPI(title="Borj ward server", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
