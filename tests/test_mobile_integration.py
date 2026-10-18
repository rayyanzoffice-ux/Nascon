import base64
import json

import pytest
from fastapi import Request

from backend.core import APIError
from backend.mobile_api import cancel_match_apply, mobile_checkout, mobile_receipt, mobile_offline_sync, me
from backend.rbac import mobile_token
from backend.scoring import new_match, projection
from backend.seed import baseline


def run(coroutine):
    # These route functions only await an in-memory request body. Avoid a
    # Windows event loop, which needs a socket pair unavailable in CI sandboxes.
    with pytest.raises(StopIteration) as finished:
        coroutine.send(None)
    return finished.value.value


def request(role, method="GET", payload=None, email=None):
    email=email or f"{role}@nascon.test"
    token=mobile_token(role,email)
    raw=json.dumps(payload or {}).encode()
    async def receive():
        return {"type":"http.request","body":raw,"more_body":False}
    return Request({"type":"http","method":method,"path":"/mobile/v1/test","headers":[(b"authorization",f"Bearer {token}".encode())]},receive)


def order():
    return {"order_id":"mobile-order-1","customer_id":"player@nascon.test","items":[{"variant_id":"var-jersey-001-M","quantity":1}],"payment":{"token":"tok_success"}}


def test_mobile_profile_has_only_its_own_role():
    for role in ("super_admin","league_organizer","club_manager","player","viewer"):
        profile=me(request(role))
        assert profile["roles"]==[role]
        assert profile["role"]==role


def test_mobile_checkout_requires_player_and_owns_receipt(monkeypatch):
    from backend import mobile_api
    state=baseline()
    monkeypatch.setenv("DAY1_SALT","test-salt")
    monkeypatch.setattr(mobile_api,"mutate",lambda fn:fn(state))
    monkeypatch.setattr(mobile_api,"read",lambda fn:fn(state))
    monkeypatch.setattr(mobile_api,"publish_order",lambda oid:None)
    for role in ("viewer","league_organizer","club_manager","super_admin"):
        with pytest.raises(APIError) as exc:
            run(mobile_checkout(request(role,"POST",order())))
        assert exc.value.status==403
    response=run(mobile_checkout(request("player","POST",order())))
    assert response.status_code==201
    assert state["inventory"]["var-jersey-001-M"]["stock"]==0
    pdf=mobile_receipt(request("player"),"mobile-order-1")
    assert pdf.media_type=="application/pdf"
    assert pdf.body.startswith(b"%PDF")
    assert pdf.body==base64.b64decode(state["orders"]["mobile-order-1"]["response"]["receipt"]["pdf_base64"])
    with pytest.raises(APIError) as exc:
        mobile_receipt(request("player",email="another@nascon.test"),"mobile-order-1")
    assert exc.value.status==404


def test_organizer_cancellation_preserves_match_history():
    state=baseline()
    state["matches"]["match-1"]=new_match("match-1","football","a","b","league-alpha-1")
    organizer={"role":"league_organizer","tenant_id":"tenant-alpha","sub":"organizer@nascon.test"}
    assert cancel_match_apply(state,"match-1",organizer,"Weather")["status"]=="cancelled"
    assert projection(state["matches"]["match-1"],state["sports"])["status"]=="cancelled"
    assert state["matches"]["match-1"]["events"]==[]
    with pytest.raises(APIError) as exc:
        cancel_match_apply(state,"match-1",{"role":"club_manager","tenant_id":"tenant-alpha","sub":"manager@nascon.test"},"No")
    assert exc.value.status==403


def test_mobile_offline_sync_enforces_action_role(monkeypatch):
    from backend import mobile_api
    monkeypatch.setattr(mobile_api,"mutate",lambda fn:pytest.fail("Forbidden action reached state mutation"))
    data={"device_id":"device-1","actions":[{"type":"score_event"}]}
    with pytest.raises(APIError) as exc:
        run(mobile_offline_sync(request("club_manager","POST",data)))
    assert exc.value.status==403
