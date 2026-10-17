"""Live Docker API probes. Set NASCON_BASE_URL and QA_TEST_SALT to run these tests."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import re
import time
import zlib

import httpx
import pytest


BASE = os.environ.get("NASCON_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="Requires an isolated live Compose API (NASCON_BASE_URL)")


def post(path, payload):
    with httpx.Client(base_url=BASE, timeout=5.0) as client:
        return client.post(path, json=payload)


def reset(stock=None):
    payload = {"seed": 42}
    if stock is not None:
        payload["stock"] = stock
    response = post("/audit/v1/reset", payload)
    assert response.status_code == 200, response.text
    return response.json()


def order(order_id, token="tok_success", discount=None):
    return {"order_id": order_id, "customer_id": "buyer '<script>",
            "items": [{"variant_id": "var-jersey-001-M", "quantity": 1}],
            "discount_code": discount, "payment": {"token": token}}


def pdf_text(data):
    """Extract ReportLab text from PDF content streams without another test dependency."""
    chunks = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            encoded = stream.strip()
            decoded = zlib.decompress(base64.a85decode(encoded[:-2] if encoded.endswith(b"~>") else encoded))
        except (ValueError, zlib.error):
            continue
        chunks.extend(re.findall(rb"\((.*?)\)\s*Tj", decoded))
    return b" ".join(chunks).decode("latin-1")


def test_reset_repeatability_and_seed_ids():
    one = reset({"var-jersey-001-M": 1, "var-jersey-001-L": 5})
    two = reset({"var-jersey-001-M": 1, "var-jersey-001-L": 5})
    assert one == two
    assert one == {"status": "reset_complete", "seed": 42,
                   "sports": ["football", "basketball", "cricket", "esports"],
                   "tenants": ["tenant-alpha", "tenant-beta"],
                   "stock": {"var-jersey-001-M": 1, "var-jersey-001-L": 5}}
    with httpx.Client(base_url=BASE, timeout=5.0) as client:
        assert client.get("/health").json() == {"status": "ok"}
        matrix = client.post("/audit/v1/rbac-matrix").json()
    assert set(matrix["tokens"]) == {"super_admin", "league_organizer", "club_manager", "player", "viewer"}
    assert matrix["context"]["foreign_player_id"] == "player-beta-1"


@pytest.mark.parametrize("token,code", [("tok_declined", "PAYMENT_DECLINED"), ("tok_capture_fail", "PAYMENT_CAPTURE_FAILED")])
def test_failed_payment_releases_stock_and_next_purchase_succeeds(token, code):
    reset({"var-jersey-001-M": 1})
    failed = post("/audit/v1/checkout", order("failed-" + token, token))
    assert (failed.status_code, failed.json()["error"]["code"]) == (402, code)
    with httpx.Client(base_url=BASE, timeout=5.0) as client:
        assert client.get("/audit/v1/inventory/var-jersey-001-M").json() == {
            "variant_id": "var-jersey-001-M", "stock": 1, "reserved": 0,
        }
    assert post("/audit/v1/checkout", order("after-" + token)).status_code == 201


def test_20_simultaneous_last_unit_buyers_and_receipt_contract():
    reset({"var-jersey-001-M": 1})
    from threading import Barrier
    barrier = Barrier(20)

    def buy(index):
        with httpx.Client(base_url=BASE, timeout=10.0) as client:
            barrier.wait(timeout=5)
            return client.post("/audit/v1/checkout", json=order(f"burst-{index}"))

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(buy, range(20)))
    assert time.monotonic() - started < 10
    assert sorted(r.status_code for r in responses) == [201] + [409] * 19
    assert all(r.json()["error"]["code"] == "OUT_OF_STOCK" for r in responses if r.status_code == 409)
    winner = next(r.json() for r in responses if r.status_code == 201)
    assert (winner["subtotal_minor"], winner["discount_minor"], winner["total_minor"], winner["currency"]) == (450000, 0, 450000, "PKR")
    receipt = winner["receipt"]
    payload = receipt["payload"]
    assert payload["order_id"] == winner["order_id"]
    assert payload["total_minor"] == winner["total_minor"]
    salt = os.environ["QA_TEST_SALT"].encode()
    message = (winner["order_id"] + "|" + json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))).encode()
    assert receipt["signature"] == hmac.new(salt, message, hashlib.sha256).hexdigest()
    pdf = base64.b64decode(receipt["pdf_base64"], validate=True)
    assert pdf.startswith(b"%PDF")
    text = pdf_text(pdf)
    assert winner["order_id"] in text
    assert "PKR 4500.00" in text
    with httpx.Client(base_url=BASE, timeout=5.0) as client:
        inventory = client.get("/audit/v1/inventory/var-jersey-001-M").json()
    assert inventory == {"variant_id": "var-jersey-001-M", "stock": 0, "reserved": 0}
    replay = post("/audit/v1/checkout", order(winner["order_id"]))
    assert replay.status_code == 200 and replay.json() == winner


def test_welcome10_and_validation_precedence():
    reset({"var-jersey-001-M": 1})
    discounted = post("/audit/v1/checkout", order("welcome", discount="WELCOME10"))
    assert discounted.status_code == 201
    assert (discounted.json()["discount_minor"], discounted.json()["total_minor"]) == (45000, 405000)
    reset({"var-jersey-001-M": 1})
    malformed = post("/audit/v1/checkout", {"order_id": "bad"})
    assert (malformed.status_code, malformed.json()["error"]["code"]) == (400, "VALIDATION_ERROR")
    unknown_variant = order("unknown-variant", discount="BOGUS")
    unknown_variant["items"][0]["variant_id"] = "does-not-exist"
    response = post("/audit/v1/checkout", unknown_variant)
    assert (response.status_code, response.json()["error"]["code"]) == (404, "VARIANT_NOT_FOUND")
    invalid_discount = post("/audit/v1/checkout", order("invalid-discount", discount="BOGUS"))
    assert (invalid_discount.status_code, invalid_discount.json()["error"]["code"]) == (400, "INVALID_DISCOUNT_CODE")
