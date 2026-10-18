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
from .mobile_api import router as mobile_router
app.include_router(mobile_router)
from .moderation import router as moderation_router
from .notifications import router as notification_router
from .observability import router as observability_router
from .privacy import router as privacy_router, revocation_middleware

app.include_router(moderation_router)
app.include_router(notification_router)
app.include_router(observability_router)
app.include_router(privacy_router)
app.middleware("http")(revocation_middleware)
from .qr import router as qr_router
from .guest import router as guest_router
app.include_router(qr_router)
app.include_router(guest_router)
