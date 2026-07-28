"""Shared rate limiter.

The customer-facing demo endpoints are unauthenticated, so they are limited by
client IP. Behind Render's proxy the real client address arrives in
``X-Forwarded-For``.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_key, default_limits=[])
