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

from .alerts import FirstSeen
from .api.fhir_routes import router as fhir_router
from .api.routes import router
from .assignment import AssignmentService
from .auth import Auth, AuthError, parse_pins
from .calls import CallConfig, CallEngine
from .clock import Clock
from .config import Settings
from .crypto import DataCipher
from .inference_client import InferenceClient
from .ingest import Ingestor
from .live import news2_by_bed, news2_total
from .meds import MedsConfig
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
        listener = MqttListener(ingestor, settings.mqtt_host, settings.mqtt_port) if settings.mqtt_enabled else None

        app.state.call_config = CallConfig.load(settings.calls_config_path)
        app.state.meds_config = MedsConfig.load(settings.meds_config_path)
        app.state.first_seen = FirstSeen()
        app.state.calls = CallEngine(
            ingestor, app.state.call_config,
            news2_total=lambda bed: news2_total(app, bed),
            publish=listener.publish_retained if listener else None,
        )
        ingestor.listeners.append(app.state.calls.on_event)
        app.state.assignment = AssignmentService(
            ingestor,
            solve=lambda nurses, beds: app.state.inference.assignment(nurses, beds) if app.state.inference else None,
            news2_by_bed=lambda: news2_by_bed(app),
            on_suggestion=app.state.hub.on_suggestion,
        )
        if settings.auto_suggest:
            ingestor.listeners.append(app.state.assignment.on_event)

        async def escalation_timer() -> None:
            # Wall-clock mode needs a timer; in demo mode clock messages also trigger tick().
            while True:
                await asyncio.sleep(settings.escalation_tick_s)
                try:
                    await asyncio.to_thread(app.state.calls.tick)
                except Exception:
                    log.exception("escalation tick failed")

        timer = asyncio.create_task(escalation_timer())
        if listener is not None:
            listener.start()
        log.info("ward %s ready: %d events replayed", settings.ward, store.count())
        try:
            yield
        finally:
            timer.cancel()
            app.state.assignment.close()
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
    app.include_router(fhir_router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
