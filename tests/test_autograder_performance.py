"""Bounded Swiss request-time probe for the largest practical hidden vectors."""

import multiprocessing
import time

import pytest

from backend.fixtures import generate


def _pair_swiss_round_two(output):
    teams = [f"t{i}" for i in range(1, 33)]
    history = [{"round": 1, "bye": None, "matches": [
        {"home": teams[i], "away": teams[i + 16], "result": "home"}
        for i in range(16)
    ]}]
    start = time.monotonic()
    try:
        result = generate({"format": "swiss", "teams": teams,
                           "params": {"round": 2, "total_rounds": 5, "history": history}})
        output.put((time.monotonic() - start, len(result["pairings"]), None))
    except Exception as exc:
        output.put((time.monotonic() - start, None, repr(exc)))


def test_swiss_32_team_round_two_within_five_seconds():
    queue = multiprocessing.Queue()
    worker = multiprocessing.Process(target=_pair_swiss_round_two, args=(queue,))
    worker.start()
    worker.join(timeout=6)
    if worker.is_alive():
        worker.terminate()
        worker.join(timeout=2)
        pytest.fail("32-team Swiss round-2 pairing exceeded six seconds")
    assert worker.exitcode == 0
    elapsed, pairings, error = queue.get(timeout=1)
    assert error is None
    assert pairings == 16
    assert elapsed < 5, f"32-team Swiss round-2 pairing took {elapsed:.3f} s"
