"""Small HTTP smoke check for the Phase I submission.

Run inside the API container with DAY1_SALT set to a test value, for example
``demo-salt``. This resets the stack's test data.
"""

import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = os.getenv("NASCON_BASE_URL", "http://localhost:8080")
SALT = os.environ["DAY1_SALT"]


def call(method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(
        BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(req, timeout=8) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def signed(id_, payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(SALT.encode(), (id_ + "|" + canonical).encode(), hashlib.sha256).hexdigest()


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS", message)


def main():
    status, health = call("GET", "/health")
    check(status == 200 and health == {"status": "ok"}, "health")
    reset = call("POST", "/audit/v1/reset", {})
    check(reset[0] == 200 and call("POST", "/audit/v1/reset", {}) == reset, "repeatable reset")

    init = {"event_id": "smoke-init", "match_id": "smoke-match", "type": "match_init",
            "payload": {"sport_id": "football", "home_team_id": "t1", "away_team_id": "t2"}}
    start = {"event_id": "smoke-start", "match_id": "smoke-match", "type": "match_start", "payload": {}}
    score = {"event_id": "smoke-score", "match_id": "smoke-match", "type": "score",
             "payload": {"team_id": "t1", "event_type": "goal"}}
    for event in (init, start, score):
        status, answer = call("POST", "/audit/v1/events", event)
        check(status == 201 and answer["signature"] == signed(event["event_id"], event["payload"]),
              "signed " + event["type"])
    status, projection = call("GET", "/audit/v1/score/smoke-match")
    check(status == 200 and projection["home"]["score"] == 1, "score projection")

    def buy(i):
        return call("POST", "/audit/v1/checkout", {
            "order_id": f"smoke-order-{i}", "customer_id": f"smoke-customer-{i}",
            "items": [{"variant_id": "var-jersey-001-M", "quantity": 1}],
            "discount_code": None, "payment": {"token": "tok_success"}})

    with ThreadPoolExecutor(max_workers=20) as pool:
        orders = list(pool.map(buy, range(20)))
    counts = {code: sum(status == code for status, _ in orders) for code in (201, 409)}
    check(counts == {201: 1, 409: 19}, "20 buyers for last unit")
    receipt = next(body["receipt"] for status, body in orders if status == 201)
    check(receipt["signature"] == signed(receipt["payload"]["order_id"], receipt["payload"]),
          "signed receipt")
    status, inventory = call("GET", "/audit/v1/inventory/var-jersey-001-M")
    check(status == 200 and inventory["stock"] == 0 and inventory["reserved"] == 0,
          "inventory after burst")

    status, matrix = call("POST", "/audit/v1/rbac-matrix", {})
    check(status == 200 and len(matrix["tokens"]) == 5, "five role tokens")
    status, denied = call("GET", "/audit/v1/rbac/platform/config", token=matrix["tokens"]["viewer"])
    check(status == 403 and denied["error"]["code"] == "FORBIDDEN", "viewer denied platform config")
    status, allowed = call("GET", "/audit/v1/rbac/platform/config", token=matrix["tokens"]["super_admin"])
    check(status == 200 and allowed["authorized"] is True, "admin allowed platform config")

    action = {"action_id": "smoke-action", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z",
              "base_version": 2, "payload": {"event_id": "smoke-offline", "match_id": "smoke-match",
                                         "type": "score", "payload": {"team_id": "t2", "event_type": "goal"}}}
    envelope = {"device_id": "smoke-device", "actions": [action]}
    status, result = call("POST", "/audit/v1/offline-sync", envelope)
    check(status == 200 and result["results"][0]["status"] == "applied", "offline action applied")
    status, replay = call("POST", "/audit/v1/offline-sync", envelope)
    check(status == 200 and replay["results"][0]["status"] == "duplicate", "offline replay duplicate")
    rejected_action = dict(action, action_id="smoke-rejected", base_version=999,
                           payload={**action["payload"], "event_id": "smoke-future"})
    rejected_envelope = {"device_id": "smoke-device", "actions": [rejected_action]}
    status, rejected = call("POST", "/audit/v1/offline-sync", rejected_envelope)
    check(status == 200 and rejected["results"][0]["status"] == "rejected", "future version rejected")
    status, rejected_replay = call("POST", "/audit/v1/offline-sync", rejected_envelope)
    check(status == 200 and rejected_replay["results"][0]["status"] == "duplicate", "rejected action replay duplicate")

    status, login = call("POST", "/mobile/v1/login",
                         {"email": "organizer@nascon.test", "password": "Nascon@26"})
    check(status == 200 and login["role"] == "league_organizer", "mobile demo login")
    status, demo = call("POST", "/mobile/v1/demo-setup", {}, login["token"])
    check(status == 200 and demo["status"] == "ready", "mobile demo setup")
    for path in ("/mobile/v1/fixtures", "/audit/v1/standings/demo-league",
                 "/mobile/v1/clubs", "/mobile/v1/catalogue", "/audit/v1/score/demo-match-1"):
        status, _ = call("GET", path, token=login["token"])
        check(status == 200, "mobile route " + path)

    mobile_actions = [
        {"action_id": "smoke-mobile-score", "type": "score_event",
         "queued_at": "2026-10-17T11:01:00Z", "base_version": 1,
         "payload": {"event_id": "smoke-mobile-event", "match_id": "demo-match-1", "type": "score",
                     "payload": {"team_id": "demo-team-a", "event_type": "goal"}}},
        {"action_id": "smoke-mobile-roster", "type": "roster_transfer",
         "queued_at": "2026-10-17T11:02:00Z", "base_version": 0,
         "payload": {"request_id": "smoke-mobile-transfer", "league_id": "demo-roster",
                     "player_id": "player-demo-1", "type": "transfer", "from_squad_id": "sq-demo-alpha",
                     "to_squad_id": "sq-demo-beta", "effective_date": "2026-10-17",
                     "loan_end_date": None, "reason": "Demo", "requested_by": "organizer@nascon.test"}},
    ]
    status, mobile_result = call("POST", "/audit/v1/offline-sync",
                                 {"device_id": "smoke-mobile", "actions": mobile_actions})
    check(status == 200 and mobile_result["summary"]["applied"] == 2,
          "mobile scoring and roster queue sync")


if __name__ == "__main__":
    main()
