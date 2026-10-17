from .app import app
from .fixtures import router as fixture_router
app.include_router(fixture_router)
