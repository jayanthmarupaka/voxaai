"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.limiter import limiter
from app.routers import (
    business,
    dashboard,
    documents,
    health,
    integrations_google,
    public,
    voice,
    webhooks,
)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.services import stt, tts

    # Loading the speech models up front costs a few seconds at boot but keeps
    # the first customer turn from stalling.
    await stt.warmup()
    await tts.warmup()
    logger.info("Voxa API ready.")
    yield


app = FastAPI(
    title="Voxa API",
    version="1.0.0",
    description="AI voice receptionist for small businesses.",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(business.router)
app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(integrations_google.router)
app.include_router(public.router)
app.include_router(webhooks.router)
app.include_router(voice.router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "voxa-api", "docs": "/docs", "health": "/health"}
