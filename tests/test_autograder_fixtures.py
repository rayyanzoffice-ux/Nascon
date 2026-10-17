"""Property checks derived from specification 5.7, independent of bracket layout choices."""

from collections import Counter, defaultdict
import pytest

from backend.core import APIError
from backend.fixtures import generate


def fixture(fmt, n, **params):
    return generate({"format": fmt, "teams": [f"t{i}" for i in range(1, n + 1)], "params": params})


@pytest.mark.parametrize("n", [2, 3, 5, 6, 12, 40])
@pytest.mark.parametrize("legs", [1, 2])
def test_round_robin_pairs_byes_balance_and_ids(n, legs):
    result = fixture("round_robin", n, legs=legs)
    rounds_per_leg = n if n % 2 else n - 1
    assert result["round_count"] == rounds_per_leg * legs
    assert result["summary"] == {
        "total": legs * n * (n - 1) // 2,
        "scheduled": legs * n * (n - 1) // 2,
        "forfeit": 0,
        "voided": 0,
    }
    ordered, unordered = Counter(), Counter()
    for leg in range(1, legs + 1):
        balance = defaultdict(lambda: [0, 0])
        byes = Counter()
        for rd in result["rounds"][(leg - 1) * rounds_per_leg : leg * rounds_per_leg]:
            used = set(rd["byes"])
            assert len(rd["byes"]) == n % 2
            byes.update(rd["byes"])
            assert len(rd["matches"]) == n // 2
            for idx, match in enumerate(rd["matches"], 1):
                assert match["match_id"] == f"RR-L{leg}-R{rd['round']}-M{idx}"
                assert match["leg"] == leg
                assert match["home"] not in used and match["away"] not in used
                used.update((match["home"], match["away"]))
                balance[match["home"]][0] += 1
                balance[match["away"]][1] += 1
                ordered[(match["home"], match["away"])] += 1
                unordered[frozenset((match["home"], match["away"]))] += 1
            assert used == {f"t{i}" for i in range(1, n + 1)}
        assert all(v == 1 for v in byes.values()) if n % 2 else not byes
        assert all(abs(h - a) <= 1 for h, a in balance.values())
    assert len(unordered) == n * (n - 1) // 2
    assert set(unordered.values()) == {legs}
    if legs == 2:
        assert len(ordered) == n * (n - 1)
        assert set(ordered.values()) == {1}


@pytest.mark.parametrize("policy", ["void_all", "forfeit_remaining"])
def test_round_robin_withdrawal_keeps_all_fixtures(policy):
    result = fixture("round_robin", 5, withdrawals=[{"team_id": "t3", "after_round": 2}], withdrawal_policy=policy)
    assert result["summary"]["total"] == 10
    for rd in result["rounds"]:
        for match in rd["matches"]:
            if "t3" not in (match["home"], match["away"]):
                assert (match["status"], match["awarded_to"]) == ("scheduled", None)
            elif policy == "void_all":
                assert (match["status"], match["awarded_to"]) == ("voided", None)
            elif rd["round"] > 2:
                assert match["status"] == "forfeit"
                assert match["awarded_to"] in (match["home"], match["away"]) and match["awarded_to"] != "t3"
            else:
                assert (match["status"], match["awarded_to"]) == ("scheduled", None)


@pytest.mark.parametrize("n", [2, 3, 5, 6, 8, 13])
def test_single_elimination_seed_order_routing_and_byes(n):
    result = fixture("single_elim", n, third_place_match=True)
    size = 1 << (n - 1).bit_length()
    order = [1, 2]
    while len(order) < size:
        new_size = len(order) * 2
        order = [v for seed in order for v in (seed, new_size + 1 - seed)]
    first = [m for m in result["rounds"][0]["matches"] if m["bracket"] == "main"]
    assert result["bracket_size"] == size
    assert len(first) == size // 2
    for idx, match in enumerate(first):
        seeds = sorted(order[2 * idx : 2 * idx + 2])
        assert match["home_seed"] == seeds[0]
        assert match["home"] == f"t{seeds[0]}"
        assert match["away"] == (f"t{seeds[1]}" if seeds[1] <= n else None)
        assert match["bye"] == (seeds[1] > n)
        if match["bye"]:
            assert match["winner"] == match["home"]
    main = [m for rd in result["rounds"] for m in rd["matches"] if m["bracket"] == "main"]
    for match in main:
        if match["winner_to"]:
            target = match["winner_to"]
            assert target == {
                "match_id": f"R{match['round'] + 1}M{(match['index'] + 1) // 2}",
                "slot": "home" if match["index"] % 2 else "away",
            }
    if size >= 4:
        tp = next(m for rd in result["rounds"] for m in rd["matches"] if m["match_id"] == "TP")
        assert tp["bracket"] == "third_place"
        semifinals = next(rd["matches"] for rd in result["rounds"] if rd["round"] == size.bit_length() - 2)
        assert [m["loser_to"] for m in semifinals] == [
            {"match_id": "TP", "slot": "home"},
            {"match_id": "TP", "slot": "away"},
        ]


@pytest.mark.parametrize("n", [3, 4, 6, 8, 13])
def test_double_elimination_graph_counts_and_slots(n):
    result = fixture("double_elim", n, bracket_reset=True)
    size = result["bracket_size"]
    k = size.bit_length() - 1
    winners = [m for rd in result["winners"] for m in rd["matches"]]
    losers = [m for rd in result["losers"] for m in rd["matches"]]
    finals = result["grand_final"]
    assert len(winners) == size - 1
    assert len(losers) == size - 2
    assert len(result["losers"]) == 2 * (k - 1)
    assert [len(rd["matches"]) for rd in result["losers"]] == [
        size // 2 ** (j + 1) for j in range(1, k) for _ in (0, 1)
    ]
    assert [m["match_id"] for m in finals] == ["GF1", "GF2"]
    assert (finals[1]["conditional"], finals[1]["required"]) == (True, None)
    assert all(m["loser_to"] is not None for m in winners)
    assert all(m["loser_to"] is None for m in losers)
    all_matches = {m["match_id"]: m for m in winners + losers + finals}
    feeds = Counter()
    for match in winners + losers:
        for direction in ("winner_to", "loser_to"):
            route = match[direction]
            if route:
                assert route["match_id"] in all_matches
                assert route["slot"] in ("home", "away")
                feeds[(route["match_id"], route["slot"])] += 1
    for match in winners[len(result["winners"][0]["matches"]):] + losers + finals[:1]:
        assert feeds[(match["match_id"], "home")] == 1
        assert feeds[(match["match_id"], "away")] == 1
    assert winners[-1]["winner_to"] == {"match_id": "GF1", "slot": "home"}
    assert losers[-1]["winner_to"] == {"match_id": "GF1", "slot": "away"}


def test_grand_final_reset_required_after_lb_wins():
    # Four seeds make the route explicit: WR1 losers play LR1, its winner meets WR2 loser in LR2.
    results = [
        {"match_id": "WR1M1", "winner": "t1"},
        {"match_id": "WR1M2", "winner": "t2"},
        {"match_id": "LR1M1", "winner": "t4"},
        {"match_id": "WR2M1", "winner": "t1"},
        {"match_id": "LR2M1", "winner": "t4"},
        {"match_id": "GF1", "winner": "t4"},
    ]
    result = fixture("double_elim", 4, bracket_reset=True, results=results)
    gf1, gf2 = result["grand_final"]
    assert (gf1["home"], gf1["away"], gf1["winner"]) == ("t1", "t4", "t4")
    assert gf2["required"] is True
    assert {gf2["home"], gf2["away"]} == {"t1", "t4"}
    results[-1]["winner"] = "t1"
    assert fixture("double_elim", 4, bracket_reset=True, results=results)["grand_final"][1]["required"] is False


def test_swiss_history_scoring_buchholz_bye_and_optimal_distance():
    history = [{"round": 1, "bye": "t5", "matches": [
        {"home": "t1", "away": "t3", "result": "home"},
        {"home": "t2", "away": "t4", "result": "draw"},
    ]}]
    result = fixture("swiss", 5, round=2, total_rounds=4, history=history)
    assert [(r["team_id"], r["score"], r["buchholz"]) for r in result["standings"]] == [
        ("t1", 1.0, 0.0), ("t5", 1.0, 0.0), ("t2", 0.5, 0.5),
        ("t4", 0.5, 0.5), ("t3", 0.0, 1.0),
    ]
    assert result["bye"] == "t3"
    scores = {r["team_id"]: r["score"] for r in result["standings"]}
    seen = {frozenset((m["home"], m["away"])) for m in history[0]["matches"]}
    pairs = [(m["home"], m["away"]) for m in result["pairings"]]
    assert len(pairs) == 2
    assert {x for pair in pairs for x in pair} == {"t1", "t2", "t4", "t5"}
    assert all(frozenset(pair) not in seen for pair in pairs)
    actual = sum(abs(scores[a] - scores[b]) for a, b in pairs)
    eligible = ["t1", "t2", "t4", "t5"]
    alternatives = []
    for x in eligible[1:]:
        remainder = [t for t in eligible if t not in (eligible[0], x)]
        candidate = [(eligible[0], x), tuple(remainder)]
        if all(frozenset(pair) not in seen for pair in candidate):
            alternatives.append(sum(abs(scores[a] - scores[b]) for a, b in candidate))
    assert actual == min(alternatives)


def test_swiss_no_rematch_free_pairing_returns_named_conflict():
    # Three legal prior rounds leave no complete pairing for either remaining bye candidate.
    history = [
        {"round": 1, "bye": "t1", "matches": [
            {"home": "t2", "away": "t3", "result": "home"},
            {"home": "t4", "away": "t5", "result": "home"},
        ]},
        {"round": 2, "bye": "t2", "matches": [
            {"home": "t1", "away": "t4", "result": "home"},
            {"home": "t3", "away": "t5", "result": "home"},
        ]},
        {"round": 3, "bye": "t5", "matches": [
            {"home": "t1", "away": "t3", "result": "home"},
            {"home": "t2", "away": "t4", "result": "home"},
        ]},
    ]
    with pytest.raises(APIError) as exc:
        fixture("swiss", 5, round=4, total_rounds=4, history=history)
    assert (exc.value.status, exc.value.code, exc.value.details) == (409, "NO_VALID_PAIRING", {"round": 4})


@pytest.mark.parametrize("fmt,n", [("round_robin", 1), ("round_robin", 41), ("swiss", 65), ("single_elim", 129), ("double_elim", 2)])
def test_fixture_team_limits(fmt, n):
    with pytest.raises(APIError) as exc:
        fixture(fmt, n)
    assert (exc.value.status, exc.value.code) == (400, "VALIDATION_ERROR")
