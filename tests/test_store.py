import base64
from backend.store import checkout_apply
from backend.seed import baseline

def test_paid_receipt_and_stock(monkeypatch):
    monkeypatch.setenv("DAY1_SALT","demo-salt")
    state=baseline()
    d={"order_id":"order-1","customer_id":"buyer","items":[{"variant_id":"var-jersey-001-M","quantity":1}],"discount_code":"WELCOME10","payment":{"token":"tok_success"}}
    code,resp=checkout_apply(state,d)
    assert code==201
    assert resp["total_minor"]==405000
    assert base64.b64decode(resp["receipt"]["pdf_base64"]).startswith(b"%PDF")
    assert state["inventory"]["var-jersey-001-M"]["stock"]==0
    assert checkout_apply(state,d)[0]==200

def test_payment_failure_leaves_stock():
    from backend.core import APIError
    state=baseline()
    d={"order_id":"o2","customer_id":"buyer","items":[{"variant_id":"var-jersey-001-M","quantity":1}],"payment":{"token":"tok_declined"}}
    try:checkout_apply(state,d)
    except APIError as e:assert e.code=="PAYMENT_DECLINED"
    assert state["inventory"]["var-jersey-001-M"]["stock"]==1
