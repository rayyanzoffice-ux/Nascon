"""Five-role probe matrix and API boundary checks from specification 5.2 and 5.13."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app import rate, validate_sport
from backend.core import APIError
from backend.main import app
from backend import rbac
from backend.seed import baseline


ROLES = ("super_admin", "league_organizer", "club_manager", "player", "viewer")
PROBES = (
    ("POST", "/audit/v1/rbac/tenants", {"super_admin"}),
    ("POST", "/audit/v1/rbac/leagues/league-alpha-1/fixtures", {"super_admin", "league_organizer"}),
    ("POST", "/audit/v1/rbac/leagues/league-alpha-2/fixtures", {"super_admin"}),
    ("POST", "/audit/v1/rbac/leagues/league-beta-1/fixtures", {"super_admin"}),
    ("POST", "/audit/v1/rbac/clubs/club-alpha-1/roster", {"super_admin", "club_manager"}),
    ("POST", "/audit/v1/rbac/clubs/club-alpha-2/roster", {"super_admin"}),
    ("POST", "/audit/v1/rbac/clubs/club-beta-1/roster", {"super_admin"}),
    ("POST", "/audit/v1/rbac/clubs/club-alpha-1/products", {"super_admin", "club_manager"}),
    ("POST", "/audit/v1/rbac/clubs/club-alpha-2/products", {"super_admin"}),
    ("POST", "/audit/v1/rbac/clubs/club-beta-1/products", {"super_admin"}),
    ("PATCH", "/audit/v1/rbac/players/player-alpha-1", {"super_admin", "club_manager", "player"}),
    ("PATCH", "/audit/v1/rbac/players/player-alpha-2", {"super_admin"}),
    ("PATCH", "/audit/v1/rbac/players/player-beta-1", {"super_admin"}),
    ("GET", "/audit/v1/rbac/clubs/club-alpha-1", set(ROLES)),
    ("GET", "/audit/v1/rbac/clubs/club-alpha-2", set(ROLES)),
    ("GET", "/audit/v1/rbac/clubs/club-beta-1", {"super_admin"}),
    ("GET", "/audit/v1/rbac/platform/config", {"super_admin"}),
)


@pytest.mark.parametrize("method,path,allowed", PROBES, ids=[f"{m} {p}" for m, p, _ in PROBES])
@pytest.mark.parametrize("role", ROLES)
def test_full_role_target_matrix_over_http(monkeypatch, method, path, allowed, role):
    monkeypatch.setattr(rbac, "read", lambda fn: fn(baseline()))
    token = rbac.tokens()[role]
    response = TestClient(app).request(method, path, headers={"Authorization": f"Bearer {token}"}, json={} if method != "GET" else None)
    assert response.status_code == (200 if role in allowed else 403)
    if role in allowed:
        assert response.json() == {"authorized": True}
    else:
        assert response.json()["error"]["code"] == "FORBIDDEN"


def test_reject_missing_tampered_none_and_expired_tokens():
    client = TestClient(app)
    valid = rbac.tokens()["super_admin"]
    header, payload, signature = valid.split(".")
    tampered = ".".join((header, payload, ("A" if signature[0] != "A" else "B") + signature[1:]))
    none = jwt.encode({"role": "super_admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, key="", algorithm="none")
    expired = jwt.encode({"role": "super_admin", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, rbac.SECRET, algorithm="HS256")
    for token in (None, tampered, none, expired):
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        response = client.get("/audit/v1/rbac/platform/config", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_ping_rate_limit_and_audit_exemption():
    rate.clear()
    client = TestClient(app)
    answers = [client.get("/api/v1/ping") for _ in range(150)]
    assert answers[0].status_code == 200 and answers[0].json() == {"pong": True}
    limited = [r for r in answers if r.status_code == 429]
    assert len(limited) >= 40
    assert all(r.headers.get("Retry-After") and r.json()["error"]["code"] == "RATE_LIMITED" for r in limited)
    audit = [client.post("/audit/v1/rbac-matrix") for _ in range(150)]
    assert all(r.status_code == 200 for r in audit)


def test_oversize_body_malformed_json_and_invalid_sport_id():
    client = TestClient(app)
    too_large = client.post("/audit/v1/sports", content=b"x" * (1048576 + 1), headers={"Content-Type": "application/json"})
    assert (too_large.status_code, too_large.json()["error"]["code"]) == (413, "PAYLOAD_TOO_LARGE")
    malformed = client.post("/audit/v1/sports", content=b"{oops", headers={"Content-Type": "application/json"})
    assert (malformed.status_code, malformed.json()["error"]["code"]) == (400, "VALIDATION_ERROR")
    sport = {
        "sport_id": "x'; DROP TABLE sports;--", "name": "Test", "scoring_model": "event",
        "periods": {"count": 1, "duration_minutes": 10},
        "scoring_events": {"raid": {"points": 1}}, "draw_allowed": True,
        "overtime": {"policy": "none"},
        "roster": {"min_squad_size": 1, "max_squad_size": 2, "required_positions": {}},
    }
    with pytest.raises(APIError) as caught:
        validate_sport(sport)
    assert (caught.value.status, caught.value.code) == (400, "VALIDATION_ERROR")
    assert "sport_id" in caught.value.details["fields"]
    sport["sport_id"] = "testing"
    sport["ignored_extra"] = "safe"
    assert "ignored_extra" not in validate_sport(sport)
