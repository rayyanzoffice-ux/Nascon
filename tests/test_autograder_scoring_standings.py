"""Scoring and table vectors from specification 5.3, 5.6, 5.9 and 5.10."""

import hashlib
import hmac
import json

import pytest

from backend.core import APIError
from backend.scoring import event_apply, new_match, projection
from backend.seed import baseline
from backend.standings import build


def append(state, mid, event_id, kind, payload=None):
    return event_apply(state, {
        "event_id": event_id, "match_id": mid, "type": kind, "payload": payload or {},
    })


def assert_error(expected_status, expected_code, fn):
    with pytest.raises(APIError) as caught:
        fn()
    assert (caught.value.status, caught.value.code) == (expected_status, expected_code)


def test_mystery_sport_arbitrary_scoring_key_and_signed_log(monkeypatch):
    monkeypatch.setenv("DAY1_SALT", "qa-é-salt")
    state = baseline()
    state["sports"]["kabaddi"] = {
        "sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
        "periods": {"count": 2, "duration_minutes": 20},
        "scoring_events": {"raid_point": {"points": 1}, "all_out": {"points": 2}},
        "draw_allowed": False, "overtime": {"policy": "golden_score"},
        "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
        "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {}},
    }
    append(state, "mystery-match", "init", "match_init", {
        "sport_id": "kabaddi", "home_team_id": "red", "away_team_id": "blue",
    })
    append(state, "mystery-match", "start", "match_start")
    payload = {"event_type": "all_out", "team_id": "red", "note": "é"}
    code, response = append(state, "mystery-match", "point", "score", payload)
    assert (code, response["sequence"], response["match_version"]) == (201, 3, 3)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected = hmac.new("qa-é-salt".encode(), ("point|" + canonical).encode(), hashlib.sha256).hexdigest()
    assert response["signature"] == expected
    assert projection(state["matches"]["mystery-match"], state["sports"])["home"]["score"] == 2
    replay_code, replay = append(state, "mystery-match", "point", "score", payload)
    assert (replay_code, replay) == (200, response)
    assert_error(409, "DUPLICATE_EVENT_ID", lambda: append(state, "mystery-match", "point", "score", {"event_type": "raid_point", "team_id": "red"}))
    append(state, "mystery-match", "undo", "compensation", {"compensates": "point", "reason": "Review"})
    projected = projection(state["matches"]["mystery-match"], state["sports"])
    assert projected["home"]["score"] == 0
    assert projected["events"][2]["payload"] == payload
    assert projected["events"][2]["compensated_by"] == "undo"
    assert projected["events"][3]["signature"] == hmac.new(
        "qa-é-salt".encode(),
        ("undo|" + json.dumps({"compensates": "point", "reason": "Review"}, sort_keys=True, separators=(",", ":"))).encode(),
        hashlib.sha256,
    ).hexdigest()


@pytest.mark.parametrize("model,event_type,expected", [
    ("innings", "wide", (1, 0, 0, "0.0")),
    ("innings", "six", (6, 0, 1, "0.1")),
    ("round", "round_win", (1, None, None, None)),
])
def test_scoring_models_project_configured_values(model, event_type, expected):
    state = baseline()
    sport = "cricket" if model == "innings" else "esports"
    state["matches"]["model-match"] = new_match("model-match", sport, "a", "b")
    append(state, "model-match", "start", "match_start")
    append(state, "model-match", "score", "score", {"team_id": "a", "event_type": event_type})
    home = projection(state["matches"]["model-match"], state["sports"])["home"]
    assert (home["score"], home["wickets"], home["balls"], home["overs"]) == expected


def test_innings_and_series_limits_respect_compensation():
    state = baseline()
    state["sports"]["cricket"]["periods"].update({"overs_per_innings": 1, "wickets_per_innings": 1})
    state["matches"]["innings"] = new_match("innings", "cricket", "a", "b")
    append(state, "innings", "start-i", "match_start")
    append(state, "innings", "wicket", "score", {"team_id": "a", "event_type": "wicket"})
    assert_error(409, "INNINGS_COMPLETE", lambda: append(state, "innings", "later", "score", {"team_id": "a", "event_type": "single"}))
    append(state, "innings", "undo-wicket", "compensation", {"compensates": "wicket", "reason": "No ball"})
    assert append(state, "innings", "legal", "score", {"team_id": "a", "event_type": "single"})[0] == 201

    state["matches"]["series"] = new_match("series", "esports", "a", "b")
    append(state, "series", "start-r", "match_start")
    for i in (1, 2):
        append(state, "series", f"round-{i}", "score", {"team_id": "a", "event_type": "round_win"})
    assert_error(409, "SERIES_ALREADY_DECIDED", lambda: append(state, "series", "round-3", "score", {"team_id": "b", "event_type": "round_win"}))
    append(state, "series", "undo-round", "compensation", {"compensates": "round-2", "reason": "Replay"})
    assert append(state, "series", "replacement", "score", {"team_id": "b", "event_type": "round_win"})[0] == 201


def test_event_error_catalogue_and_transition_precedence():
    state = baseline()
    assert_error(404, "MATCH_NOT_FOUND", lambda: append(state, "missing", "start", "match_start"))
    state["matches"]["m"] = new_match("m", "basketball", "a", "b")
    assert_error(409, "MATCH_NOT_IN_PROGRESS", lambda: append(state, "m", "early", "score", {"team_id": "a", "event_type": "two_pointer"}))
    assert_error(409, "ILLEGAL_TRANSITION", lambda: append(state, "m", "end-early", "match_end"))
    append(state, "m", "started", "match_start")
    assert_error(409, "ILLEGAL_TRANSITION", lambda: append(state, "m", "started-twice", "match_start"))
    assert_error(400, "UNKNOWN_EVENT_TYPE", lambda: append(state, "m", "unknown", "score", {"team_id": "a", "event_type": "goal"}))
    assert_error(404, "EVENT_NOT_FOUND", lambda: append(state, "m", "bad-undo", "compensation", {"compensates": "missing", "reason": "x"}))
    assert_error(409, "INVALID_COMPENSATION", lambda: append(state, "m", "bad-start-undo", "compensation", {"compensates": "started", "reason": "x"}))
    assert_error(409, "TIE_NOT_ALLOWED", lambda: append(state, "m", "tied-end", "match_end"))
    append(state, "m", "tie-win", "tiebreak_winner", {"team_id": "a"})
    append(state, "m", "ended", "match_end")
    assert_error(409, "MATCH_NOT_IN_PROGRESS", lambda: append(state, "m", "late", "score", {"team_id": "b", "event_type": "two_pointer"}))
    assert projection(state["matches"]["m"], state["sports"])["outcome"] == "home_win"
    append(state, "m", "undo-tie", "compensation", {"compensates": "tie-win", "reason": "Penalty"})
    assert projection(state["matches"]["m"], state["sports"])["outcome"] == "undecided"


def complete(state, mid, home_goals, away_goals):
    append(state, mid, f"{mid}-start", "match_start")
    goals = {}
    match = state["matches"][mid]
    for team, total in ((match["home"], home_goals), (match["away"], away_goals)):
        goals[team] = []
        for idx in range(total):
            eid = f"{mid}-{team}-{idx}"
            append(state, mid, eid, "score", {"team_id": team, "event_type": "goal"})
            goals[team].append(eid)
    append(state, mid, f"{mid}-end", "match_end")
    return goals


def test_three_way_mini_league_restarts_after_split_and_correction_recomputes():
    state = baseline()
    fixtures = [
        ("ab", "a", "b", 2, 0), ("bc", "b", "c", 1, 0),
        ("ca", "c", "a", 3, 0), ("ad", "a", "d", 1, 0),
        ("bd", "b", "d", 10, 0), ("cd", "c", "d", 1, 0),
    ]
    state["leagues"]["lg-mini"] = {
        "league_id": "lg-mini", "sport_id": "football", "teams": ["a", "b", "c", "d"],
        "fixtures": [{"match_id": mid, "home": h, "away": a} for mid, h, a, _, _ in fixtures],
        "points": {"win": 3, "draw": 1, "loss": 0},
        "qualification": {"spots": 2},
        "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
        "lots_seed": 42,
    }
    for mid, home, away, _, _ in fixtures:
        state["matches"][mid] = new_match(mid, "football", home, away, "lg-mini")
    goals = {}
    for mid, _, _, home_goals, away_goals in fixtures:
        goals[mid] = complete(state, mid, home_goals, away_goals)
    table = build(state, "lg-mini")["table"]
    assert [row["team_id"] for row in table] == ["c", "a", "b", "d"]
    assert [row["points"] for row in table] == [6, 6, 6, 0]
    assert [row["status"] for row in table] == ["still_possible", "still_possible", "still_possible", "eliminated"]
    assert table[2]["diff"] > table[0]["diff"]  # Overall goal difference must not override the mini-league.
    assert build(state, "lg-mini")["h2h"]["a"]["b"] == {"played": 1, "points": 3, "scored": 2, "conceded": 0}
    for idx, target in enumerate(goals["ca"]["c"]):
        append(state, "ca", f"correct-{idx}", "compensation", {"compensates": target, "reason": "Result correction"})
    corrected = build(state, "lg-mini")["table"]
    assert [row["team_id"] for row in corrected] == ["a", "b", "c", "d"]
    assert [row["points"] for row in corrected] == [7, 6, 4, 0]
    assert [row["status"] for row in corrected] == ["clinched", "clinched", "eliminated", "eliminated"]
    assert projection(state["matches"]["ca"], state["sports"])["status"] == "completed"


def test_draw_lots_uses_seeded_sha256_exactly():
    state = baseline(42)
    teams = ["t1", "t2", "t3"]
    state["leagues"]["lg-1"] = {
        "league_id": "lg-1", "sport_id": "football", "teams": teams, "fixtures": [],
        "points": {"win": 3, "draw": 1, "loss": 0}, "qualification": {"spots": 1},
        "tie_break_order": ["draw_lots"], "lots_seed": 42,
    }
    expected = sorted(teams, key=lambda t: hashlib.sha256(f"42|lg-1|{t}".encode()).hexdigest())
    assert [row["team_id"] for row in build(state, "lg-1")["table"]] == expected


def test_innings_nrr_uses_legal_balls_and_rounds_to_three_decimals():
    state = baseline()
    state["sports"]["cricket"]["periods"]["overs_per_innings"] = 2
    state["leagues"]["lg-nrr"] = {
        "league_id": "lg-nrr", "sport_id": "cricket", "teams": ["a", "b"],
        "fixtures": [{"match_id": "nrr-match", "home": "a", "away": "b"}],
        "points": {"win": 3, "draw": 1, "loss": 0},
        "qualification": {"spots": 1}, "tie_break_order": ["overall_diff", "draw_lots"], "lots_seed": 42,
    }
    state["matches"]["nrr-match"] = new_match("nrr-match", "cricket", "a", "b", "lg-nrr")
    append(state, "nrr-match", "nrr-start", "match_start")
    for team, events in (("a", ["single"] + ["dot_ball"] * 6),
                         ("b", ["single", "single"] + ["dot_ball"] * 3)):
        for idx, event_type in enumerate(events):
            append(state, "nrr-match", f"{team}-{idx}", "score", {"team_id": team, "event_type": event_type})
    append(state, "nrr-match", "nrr-end", "match_end")
    result = build(state, "lg-nrr")
    rows = {row["team_id"]: row for row in result["table"]}
    assert rows["a"]["diff"] == -1.543  # (1 / (7/6)) - (2 / (5/6))
    assert rows["b"]["diff"] == 1.543
    projection_ = projection(state["matches"]["nrr-match"], state["sports"])
    assert (projection_["home"]["balls"], projection_["home"]["overs"]) == (7, "1.1")
    assert (projection_["away"]["balls"], projection_["away"]["overs"]) == (5, "0.5")
