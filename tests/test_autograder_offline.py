"""Offline queue ordering, versioning and replay rules from specification 5.14."""

import hashlib
import hmac
import json

import pytest

from backend.offline import sync_apply
from backend.roster import setup_apply
from backend.scoring import new_match
from backend.seed import baseline


def score_action(action_id, queued_at, base_version, event_id, match_id="m", event_type="goal"):
    return {
        "action_id": action_id, "type": "score_event", "queued_at": queued_at,
        "base_version": base_version,
        "payload": {"event_id": event_id, "match_id": match_id, "type": "score",
                    "payload": {"team_id": "a", "event_type": event_type}},
    }


def started_match():
    state = baseline()
    state["matches"]["m"] = new_match("m", "football", "a", "b")
    state["matches"]["m"]["events"] = [{
        "event_id": "start", "type": "match_start", "payload": {}, "signature": "seeded",
    }]
    return state


def test_actions_sort_by_queued_at_and_return_in_request_order(monkeypatch):
    monkeypatch.setenv("DAY1_SALT", "offline-test-salt")
    state = started_match()
    later = score_action("later", "2026-10-17T11:02:00Z", 1, "goal-later")
    earlier = score_action("earlier", "2026-10-17T11:01:00Z", 1, "goal-earlier")
    request = {"device_id": "phone-1", "actions": [later, earlier]}
    response = sync_apply(state, request)
    assert [r["action_id"] for r in response["results"]] == ["later", "earlier"]
    assert [r["processed_order"] for r in response["results"]] == [2, 1]
    assert [r["resolution"] for r in response["results"]] == ["rebased_append", "appended"]
    assert [r["server_version"] for r in response["results"]] == [3, 2]
    assert response["summary"] == {"applied": 2, "rejected": 0, "duplicate": 0}
    for action, result in zip(request["actions"], response["results"]):
        payload = action["payload"]["payload"]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(b"offline-test-salt", (action["payload"]["event_id"] + "|" + canonical).encode(), hashlib.sha256).hexdigest()
        assert result["signature"] == expected
    repeated = sync_apply(state, request)
    assert repeated["summary"] == {"applied": 0, "rejected": 0, "duplicate": 2}
    assert all(r["resolution"] == "skipped_duplicate" for r in repeated["results"])
    assert len(state["matches"]["m"]["events"]) == 3


def test_future_base_version_rejected_without_changing_match():
    state = started_match()
    response = sync_apply(state, {"device_id": "phone-2", "actions": [
        score_action("future", "2026-10-17T11:00:00Z", 99, "goal-future"),
    ]})
    result = response["results"][0]
    assert (result["status"], result["resolution"], result["error_code"], result["server_version"]) == (
        "rejected", "server_wins", "INVALID_BASE_VERSION", 1,
    )
    assert len(state["matches"]["m"]["events"]) == 1


def test_roster_transfer_conflict_is_per_action_not_envelope_failure():
    state = baseline()
    setup_apply(state, {
        "league": {"league_id": "lg-offline", "tenant_id": "tenant-alpha", "sport_id": "football",
                   "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
                   "max_squad_size": 3, "required_positions": {}},
        "squads": [
            {"squad_id": "s1", "club_id": "c1", "tenant_id": "tenant-alpha", "name": "First"},
            {"squad_id": "s2", "club_id": "c2", "tenant_id": "tenant-alpha", "name": "Second"},
        ],
        "players": [{"player_id": "p1", "name": "Ali", "position": "df", "squad_id": "s1", "role": "starter"}],
    })
    payload = {"request_id": "tr-offline", "league_id": "lg-offline", "player_id": "p1",
               "type": "transfer", "from_squad_id": "s1", "to_squad_id": "s2",
               "effective_date": "2026-09-30", "loan_end_date": None,
               "reason": "Move", "requested_by": "manager"}
    actions = [
        {"action_id": "first", "type": "roster_transfer", "queued_at": "2026-10-17T11:00:00Z", "base_version": 0, "payload": payload},
        {"action_id": "second", "type": "roster_transfer", "queued_at": "2026-10-17T11:01:00Z", "base_version": 0,
         "payload": {**payload, "request_id": "tr-offline-2"}},
    ]
    response = sync_apply(state, {"device_id": "phone-3", "actions": actions})
    assert [r["status"] for r in response["results"]] == ["applied", "rejected"]
    assert response["results"][1]["error_code"] == "NOT_IN_SQUAD"
    assert response["results"][1]["server_version"] == 1
    assert response["summary"] == {"applied": 1, "rejected": 1, "duplicate": 0}


@pytest.mark.xfail(strict=True, reason="backend/offline.py does not record rule-rejected action IDs; 5.14 requires duplicate on replay")
def test_rejected_action_is_duplicate_on_identical_replay():
    state = baseline()
    state["matches"]["m"] = new_match("m", "football", "a", "b")  # upcoming
    request = {"device_id": "phone-4", "actions": [
        score_action("bad-before-start", "2026-10-17T11:00:00Z", 0, "early-goal"),
    ]}
    first = sync_apply(state, request)["results"][0]
    assert (first["status"], first["error_code"]) == ("rejected", "MATCH_NOT_IN_PROGRESS")
    replay = sync_apply(state, request)["results"][0]
    assert (replay["status"], replay["resolution"], replay["error_code"]) == (
        "duplicate", "skipped_duplicate", None,
    )
