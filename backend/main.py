from .app import app
from .fixtures import router as fixture_router
from .scoring import router as scoring_router
from .leagues import router as leagues_router
from .standings import router as standings_router
from .store import router as store_router
from .rbac import router as rbac_router
from .roster import router as roster_router
from .offline import router as offline_router

app.include_router(fixture_router)
app.include_router(scoring_router)
app.include_router(leagues_router)
app.include_router(standings_router)
app.include_router(store_router)
app.include_router(rbac_router)
app.include_router(roster_router)
app.include_router(offline_router)
