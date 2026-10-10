"""FastAPI app: wires the event store, ward clock, ingest pipeline, MQTT and routes.

Run locally:  uvicorn borj_server.main:app --reload   (with contracts/ and server/ on PYTHONPATH)
"""

from __future__ import annotations

import asyncio
import base64
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .api.routes import router
from .auth import Auth, AuthError, parse_pins
from .clock import Clock
from .config import Settings
from .crypto import DataCipher
from .inference_client import InferenceClient
from .ingest import Ingestor
from .mqtt import MqttListener
from .store import EventStore
from .stream import StreamHub
from .twin.layout import WardLayout

log = logging.getLogger("borj_server")


def create_app(
    settings: Settings | None = None,
    inference_http: httpx.Client | None = None,
    cipher: DataCipher | None = None,
) -> FastAPI:
    """inference_http and cipher let tests plug in an in-process inference app and a test key."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.token_key_b64:
            raise AuthError("BORJ_TOKEN_KEY is not set; run `python infra/gen_secrets.py`")
        layout = WardLayout.load(settings.seed_path)
        app.state.auth = Auth(
            pins=parse_pins(settings.staff_pins),
            roles={s.staff_id: s.role for s in layout.staff},
            token_key=base64.b64decode(settings.token_key_b64),
            ttl_s=settings.token_ttl_s,
        )
        store = EventStore(settings.db_url, cipher or DataCipher.from_env())
        ingestor = Ingestor(layout, store, Clock(settings.clock_mode))
        ingestor.rebuild()  # restore the twin from the persisted log
        app.state.ingestor = ingestor
        app.state.settings = settings
        app.state.hub = StreamHub()
        app.state.hub.loop = asyncio.get_running_loop()
        ingestor.listeners.append(app.state.hub.on_ingest)
        if inference_http is not None:
            app.state.inference = InferenceClient(inference_http)
        elif settings.inference_url:
            app.state.inference = InferenceClient.from_url(settings.inference_url, settings.inference_timeout_s)
        else:
            app.state.inference = None
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
            if app.state.inference is not None and inference_http is None:
                app.state.inference.close()
            store.close()

    app = FastAPI(title="Borj ward server", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def contract_errors(_request: Request, exc: HTTPException) -> JSONResponse:
        # contracts/openapi.yaml Error shape: {"error": ..., "detail": ...}
        body = exc.detail if isinstance(exc.detail, dict) else {"error": "http_error", "detail": str(exc.detail)}
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    app.include_router(router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
