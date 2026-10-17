"""Ordered roster business checks and deferred/loan behavior from specification 5.11."""

from copy import deepcopy

import pytest

from backend.core import APIError
from backend.roster import setup_apply, transfer_apply
from backend.seed import baseline


def scenario(max_size=3, required=None, dest_players=0, live=False):
    return {
        "league": {"league_id": "lg-rules", "tenant_id": "tenant-alpha", "sport_id": "football",
                   "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
                   "max_squad_size": max_size, "required_positions": required or {}},
        "squads": [
            {"squad_id": "s1", "club_id": "club-alpha-1", "tenant_id": "tenant-alpha", "name": "One"},
            {"squad_id": "s2", "club_id": "club-alpha-2", "tenant_id": "tenant-alpha", "name": "Two"},
        ],
        "players": [{"player_id": "p1", "name": "Ali", "position": "gk", "squad_id": "s1", "role": "captain"}] + [
            {"player_id": f"p-dest-{i}", "name": f"Other {i}", "position": "df", "squad_id": "s2", "role": "starter"}
            for i in range(dest_players)
        ],
        "matches_in_progress": ([{"match_id": "m-live", "home_squad_id": "s1", "away_squad_id": "s2"}] if live else []),
    }


def move(**changes):
    return {"request_id": "request-1", "league_id": "lg-rules", "player_id": "p1", "type": "transfer",
            "from_squad_id": "s1", "to_squad_id": "s2", "effective_date": "2026-09-30",
            "loan_end_date": None, "reason": "Tactical", "requested_by": "manager", **changes}


@pytest.mark.parametrize("change,status,code", [
    ({"effective_date": "2026-02-30", "league_id": "missing"}, 400, "VALIDATION_ERROR"),
    ({"league_id": "missing"}, 404, "LEAGUE_NOT_FOUND"),
    ({"player_id": "missing"}, 404, "PLAYER_NOT_FOUND"),
    ({"to_squad_id": "missing"}, 404, "SQUAD_NOT_FOUND"),
    ({"from_squad_id": "s2"}, 409, "NOT_IN_SQUAD"),
    ({"effective_date": "2026-10-01"}, 409, "TRANSFER_WINDOW_CLOSED"),
    ({"type": "loan", "loan_end_date": "2026-09-30"}, 400, "VALIDATION_ERROR"),
])
def test_ordered_schema_id_and_business_failures_leave_no_audit(change, status, code):
    state = baseline()
    setup_apply(state, scenario())
    with pytest.raises(APIError) as caught:
        transfer_apply(state, move(**change))
    assert (caught.value.status, caught.value.code) == (status, code)
    assert state["players"]["p1"]["history"] == []


def test_squad_full_precedes_minimum_position_check():
    state = baseline()
    setup_apply(state, scenario(max_size=2, required={"gk": 1}, dest_players=2))
    with pytest.raises(APIError) as caught:
        transfer_apply(state, move())
    assert (caught.value.status, caught.value.code) == (409, "SQUAD_FULL")
    assert state["players"]["p1"]["history"] == []
    setup_apply(state, scenario(max_size=3, required={"gk": 1}, dest_players=0))
    with pytest.raises(APIError) as caught:
        transfer_apply(state, move())
    assert (caught.value.status, caught.value.code) == (409, "MIN_POSITION_VIOLATION")


def test_loan_blocks_subsequent_move_and_last_window_day_can_defer():
    state = baseline()
    setup_apply(state, scenario(live=True))
    request = move(type="loan", loan_end_date="2026-10-03")
    code, response = transfer_apply(state, request)
    assert code == 201
    assert (response["state"], response["blocking_match_id"]) == ("deferred_until_match_end", "m-live")
    assert transfer_apply(state, request) == (200, response)
    assert response["audit_entry"]["state"] == "deferred_until_match_end"
    with pytest.raises(APIError) as caught:
        transfer_apply(state, move(request_id="release-loan", type="release", from_squad_id="s2", to_squad_id=None))
    assert (caught.value.status, caught.value.code) == (409, "PLAYER_ON_LOAN")
    assert len(state["players"]["p1"]["history"]) == 1


@pytest.mark.xfail(strict=True, reason="backend/roster.py resolves squads only within the current league; 5.11 requires global existence then CROSS_TENANT_TRANSFER")
def test_foreign_existing_squad_is_cross_tenant_conflict():
    state = baseline()
    setup_apply(state, scenario())
    foreign = deepcopy(scenario())
    foreign["league"].update({"league_id": "lg-beta", "tenant_id": "tenant-beta"})
    foreign["squads"] = [{"squad_id": "foreign-squad", "club_id": "club-beta-1", "tenant_id": "tenant-beta", "name": "Foreign"}]
    foreign["players"] = []
    setup_apply(state, foreign)
    with pytest.raises(APIError) as caught:
        transfer_apply(state, move(to_squad_id="foreign-squad"))
    assert (caught.value.status, caught.value.code) == (409, "CROSS_TENANT_TRANSFER")
