"""Isolated branch entry point; core integration can include these routers in main.py."""

from .main import app
from .streaming import router as streaming_router
from .costream import router as costream_router
from .athletes import router as athletes_router

if not any(route.path == "/audit/v1/stream/key" for route in app.routes):
    app.include_router(streaming_router)
if not any(route.path == "/audit/v1/costream/session" for route in app.routes):
    app.include_router(costream_router)
if not any(route.path == "/api/v1/athletes/{player_id}" for route in app.routes):
    app.include_router(athletes_router)
