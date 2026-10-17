"""HTTP wiring checks with a fresh in-memory state for rubric services."""

import base64

from fastapi.testclient import TestClient

from backend.main import app
from backend.seed import baseline
from backend import roster, scoring, standings, store


def install_state(monkeypatch, module, state):
    if hasattr(module, "mutate"):
        monkeypatch.setattr(module, "mutate", lambda fn: fn(state))
    if hasattr(module, "read"):
        monkeypatch.setattr(module, "read", lambda fn: fn(state))


def test_checkout_and_inventory_http_statuses(monkeypatch):
    state = baseline()
    install_state(monkeypatch, store, state)
    client = TestClient(app)
    data = {"order_id": "http-order", "customer_id": "buyer", "items": [
        {"variant_id": "var-jersey-001-M", "quantity": 1}],
        "payment": {"token": "tok_success"}}
    bought = client.post("/audit/v1/checkout", json=data)
    assert bought.status_code == 201
    assert base64.b64decode(bought.json()["receipt"]["pdf_base64"]).startswith(b"%PDF")
    assert client.post("/audit/v1/checkout", json=data).status_code == 200
    inventory = client.get("/audit/v1/inventory/var-jersey-001-M")
    assert inventory.json() == {"variant_id": "var-jersey-001-M", "stock": 0, "reserved": 0}
    unknown = client.get("/audit/v1/inventory/missing")
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "VARIANT_NOT_FOUND")


def test_roster_setup_transfer_history_and_automatic_return_over_http(monkeypatch):
    state = baseline()
    install_state(monkeypatch, roster, state)
    client = TestClient(app)
    scenario = {
        "league": {"league_id": "lg-routes", "tenant_id": "tenant-alpha", "sport_id": "football",
                   "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
                   "max_squad_size": 3, "required_positions": {}},
        "squads": [
            {"squad_id": "source", "club_id": "c1", "tenant_id": "tenant-alpha", "name": "Source"},
            {"squad_id": "dest", "club_id": "c2", "tenant_id": "tenant-alpha", "name": "Dest"},
        ],
        "players": [{"player_id": "p-route", "name": "Ali", "position": "df", "squad_id": "source", "role": "captain"}],
    }
    configured = client.post("/audit/v1/roster/setup", json=scenario)
    assert configured.status_code == 201
    assert configured.json()["squad_counts"] == {"source": 1, "dest": 0}
    request = {"request_id": "loan-route", "league_id": "lg-routes", "player_id": "p-route", "type": "loan",
               "from_squad_id": "source", "to_squad_id": "dest", "effective_date": "2026-09-30",
               "loan_end_date": "2026-10-03", "reason": "Cover", "requested_by": "manager"}
    moved = client.post("/audit/v1/roster/transfer", json=request)
    assert moved.status_code == 201 and moved.json()["registration"]["squad_id"] == "dest"
    assert client.post("/audit/v1/roster/transfer", json=request).status_code == 200
    before = client.get("/audit/v1/roster/history/p-route?as_of=2026-10-03")
    assert before.json()["current_squad_id"] == "dest"
    after = client.get("/audit/v1/roster/history/p-route?as_of=2026-10-04")
    assert after.json()["current_squad_id"] == "source"
    assert [x["action"] for x in after.json()["history"]] == ["loan", "loan_return"]
    assert len(client.get("/audit/v1/roster/history/p-route?as_of=2026-10-05").json()["history"]) == 2
    missing = client.get("/audit/v1/roster/history/absent")
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "PLAYER_NOT_FOUND")


def test_event_and_standings_http_statuses(monkeypatch):
    state = baseline()
    install_state(monkeypatch, scoring, state)
    install_state(monkeypatch, standings, state)
    client = TestClient(app)
    init = client.post("/audit/v1/events", json={"event_id": "http-init", "match_id": "http-match",
        "type": "match_init", "payload": {"sport_id": "football", "home_team_id": "a", "away_team_id": "b"}})
    assert init.status_code == 201
    assert client.post("/audit/v1/events", json={"event_id": "http-start", "match_id": "http-match",
        "type": "match_start", "payload": {}}).status_code == 201
    assert client.get("/audit/v1/score/http-match").json()["version"] == 2
    missing = client.get("/audit/v1/score/absent")
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "MATCH_NOT_FOUND")
    missing_league = client.get("/audit/v1/standings/absent")
    assert (missing_league.status_code, missing_league.json()["error"]["code"]) == (404, "LEAGUE_NOT_FOUND")
