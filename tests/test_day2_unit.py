import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.core import APIError
from backend.guest import merge_apply, reject_guest_write
from backend import qr
from backend.qr import resolve
from backend.seed import baseline


@pytest.fixture(autouse=True)
def day2_salt(monkeypatch):
    monkeypatch.setenv("DAY2_SALT", "test-salt")


def request(token="guest_anon_tok_7721", quantity=1):
    return {"guest_token": token, "registered_user_id": "player-alpha-1",
            "guest_cart": [{"variant_id": "var-jersey-001-L", "quantity": quantity}], "test_write_block": True}


def test_qr_target_mutation_and_private_telemetry():
    state = baseline()
    initial = resolve(state, "match-m1", inspect=True)
    assert initial["scan_count"] == 0 and initial["target_route"].endswith("/live")
    scanned = resolve(state, "match-m1", user_agent="Mozilla Android private", inspect=False)
    assert scanned["scan_count"] == 1
    assert "private" not in str(state["qr_telemetry"])
    state["matches"]["match-m1"]["events"].append({"event_id": "end", "type": "match_end", "payload": {}, "signature": ""})
    completed = resolve(state, "match-m1", inspect=True)
    assert completed["target_route"].endswith("/vod")
    assert completed["short_url"] == initial["short_url"]
    assert completed["signature"] != initial["signature"]
    state["matches"]["match-m1"]["status"] = "postponed"
    assert resolve(state, "match-m1", inspect=True)["target_route"].endswith("notice?state=postponed")


def test_atomic_merge_retry_and_conflict():
    state = baseline()
    lock = threading.Lock()
    payload = request()

    def apply(_):
        with lock:
            return merge_apply(state, payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(apply, range(8)))
    assert all(result == results[0] for result in results)
    assert results[0]["active_cart"]["total_items"] == 1
    assert results[0]["write_block_verified"] is True
    assert state["inventory"]["var-jersey-001-L"]["reserved"] == 1
    with pytest.raises(APIError) as error:
        merge_apply(state, request(quantity=2))
    assert error.value.status == 409 and error.value.code == "GUEST_TOKEN_ALREADY_MERGED"
    with pytest.raises(APIError) as error:
        merge_apply(state, request(token="guest_anon_tok_next", quantity=5))
    assert error.value.status == 409 and error.value.code == "OUT_OF_STOCK"
    assert state["inventory"]["var-jersey-001-L"]["reserved"] == 1


def test_qr_exports_and_write_rejection(monkeypatch):
    state = baseline()
    monkeypatch.setattr(qr, "mutate", lambda fn: fn(state))
    formats = (("svg", "image/svg+xml", (b"<svg", b"<?xml")),
               ("png", "image/png", (b"\x89PNG\r\n\x1a\n",)),
               ("pdf", "application/pdf", (b"%PDF-",)))
    for extension, content_type, prefixes in formats:
        response = qr.export_qr("match-m1", extension)
        assert response.status_code == 200
        assert response.media_type == content_type
        assert response.body.startswith(prefixes)
    with pytest.raises(APIError) as error:
        reject_guest_write("guest_anon_tok_7721")
    assert error.value.status == 403 and error.value.code == "GUEST_WRITE_FORBIDDEN"
