"""Anonymous viewer credentials and atomic guest cart migration."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Request

from .app import body
from .core import APIError, bad, fail, identifier, mutate, positive_int, read
from .day2_signing import sign_day2

router = APIRouter()
TOKEN_LIFETIME = timedelta(hours=2)


def is_guest_token(value):
    return isinstance(value, str) and value.startswith("guest_")


def reject_guest_write(token):
    if is_guest_token(token):
        fail(403, "GUEST_WRITE_FORBIDDEN")


def bearer_token(req):
    authorization = req.headers.get("authorization", "")
    return authorization[7:] if authorization.startswith("Bearer ") else None


def guest_record(state, token):
    record = state.get("guest_tokens", {}).get(token)
    if not record:
        fail(401, "UNAUTHENTICATED")
    if datetime.fromisoformat(record["expires_at"]) <= datetime.now(timezone.utc):
        fail(401, "UNAUTHENTICATED")
    return record


@router.post("/api/v1/guest/token")
def issue_token():
    def issue(state):
        token = "guest_anon_tok_" + secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + TOKEN_LIFETIME
        state.setdefault("guest_tokens", {})[token] = {"expires_at": expires.isoformat(), "scope": ["playback:read", "score:read", "cart:stage"]}
        return {"guest_token": token, "expires_at": expires.isoformat(), "scope": ["playback:read", "score:read", "cart:stage"]}
    return mutate(issue)


@router.get("/api/v1/guest/playback/{entity_id}")
def guest_playback(req: Request, entity_id: str):
    token = bearer_token(req)
    def load(state):
        guest_record(state, token)
        if entity_id not in state.get("matches", {}) and entity_id not in state.get("costream_sessions", {}):
            fail(404, "STREAM_NOT_FOUND")
        return {"entity_id": entity_id, "authorized": True, "scope": "playback:read"}
    return read(load)


@router.post("/api/v1/chat")
def guest_chat_write(req: Request):
    reject_guest_write(bearer_token(req))
    fail(403, "GUEST_WRITE_FORBIDDEN")


def validate_merge(data):
    fields = []
    token = data.get("guest_token")
    user = data.get("registered_user_id")
    items = data.get("guest_cart")
    verify = data.get("test_write_block", True)
    if not isinstance(token, str) or not token.startswith("guest_") or len(token) > 128:
        fields.append("guest_token")
    if not identifier(user):
        fields.append("registered_user_id")
    if not isinstance(items, list) or not 1 <= len(items) <= 10 or any(
        not isinstance(item, dict) or not identifier(item.get("variant_id")) or not positive_int(item.get("quantity"))
        for item in items if isinstance(items, list)
    ):
        fields.append("guest_cart")
    if type(verify) is not bool:
        fields.append("test_write_block")
    if fields:
        bad(*fields)
    return token, user, items, verify


def cart_response(user, cart):
    items = [{"variant_id": variant_id, **entry} for variant_id, entry in sorted(cart.items())]
    return {"user_id": user, "currency": "PKR", "total_items": sum(item["quantity"] for item in items),
            "subtotal_minor": sum(item["quantity"] * item["unit_price_minor"] for item in items), "items": items}


def merge_apply(state, data):
    token, user, items, verify = validate_merge(data)
    quantities = Counter()
    for item in items:
        quantities[item["variant_id"]] += item["quantity"]
    fingerprint = {"registered_user_id": user, "guest_cart": deepcopy(items)}
    prior = state.setdefault("guest_merges", {}).get(token)
    if prior:
        if prior["fingerprint"] != fingerprint:
            fail(409, "GUEST_TOKEN_ALREADY_MERGED")
        return prior["response"]
    if user not in state.get("rbac_players", {}) and user not in state.get("players", {}):
        fail(404, "PLAYER_NOT_FOUND")
    inventory = state["inventory"]
    for variant_id in quantities:
        if variant_id not in inventory:
            fail(404, "VARIANT_NOT_FOUND", variant_id=variant_id)
    cart = state.setdefault("active_carts", {}).setdefault(user, {})
    for variant_id, quantity in quantities.items():
        variant = inventory[variant_id]
        existing = cart.get(variant_id, {}).get("quantity", 0)
        if existing + quantity > variant["stock"] or quantity > variant["stock"] - variant.get("reserved", 0):
            fail(409, "OUT_OF_STOCK", variant_id=variant_id)
    # Authenticate only after deterministic entity and stock validation. This
    # preserves the documented error ordering while rejecting forged tokens.
    guest_record(state, token)
    verified = False
    rejection_code = 0
    if verify:
        try:
            reject_guest_write(token)
        except APIError as exc:
            verified = exc.status == 403 and exc.code == "GUEST_WRITE_FORBIDDEN"
            rejection_code = exc.status
        if not verified:
            raise RuntimeError("Guest write guard did not reject the probe")
    for variant_id, quantity in quantities.items():
        variant = inventory[variant_id]
        entry = cart.setdefault(variant_id, {"quantity": 0, "unit_price_minor": variant["price_minor"]})
        entry["quantity"] += quantity
        variant["reserved"] = variant.get("reserved", 0) + quantity
    active_cart = cart_response(user, cart)
    payload = {"cart_merged": True, "guest_token": token, "registered_user_id": user,
               "total_items": active_cart["total_items"], "write_rejection_code": rejection_code}
    response = {"guest_token": token, "write_block_verified": verified, "write_rejection_code": rejection_code,
                "cart_merged": True, "active_cart": active_cart, "signature": sign_day2(token, payload)}
    state["guest_merges"][token] = {"fingerprint": fingerprint, "response": response}
    state.get("guest_tokens", {}).pop(token, None)
    return response


@router.post("/audit/v1/guest/cart-merge")
async def cart_merge(req: Request):
    reject_guest_write(bearer_token(req))
    data = await body(req)
    return mutate(lambda state: merge_apply(state, data))
