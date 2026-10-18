"""Right-to-erasure state mutation and token revocation boundary."""

import hashlib

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .core import bad, identifier, mutate, read

router = APIRouter()
ANONYMIZED = "Anonymized User"


def _linked(record, user_id):
    return isinstance(record, dict) and any(record.get(key) == user_id for key in (
        "user_id", "player_id", "registered_user_id", "customer_id", "owner_id", "sub"))


def _wipe_pii(record):
    for key in ("name", "display_name", "first_name", "last_name", "email", "phone",
                "address", "ip_address", "user_agent", "device_fingerprint"):
        if key in record:
            record[key] = ANONYMIZED if key in ("name", "display_name") else None


def anonymize_user(state, user_id):
    # Preserve stable IDs and competition history while removing identifying fields.
    player = state.get("players", {}).get(user_id)
    if isinstance(player, dict):
        _wipe_pii(player)
    for key in ("users", "profiles", "viewers", "guests"):
        records = state.get(key, {})
        if isinstance(records, dict):
            record = records.get(user_id)
            if isinstance(record, dict):
                _wipe_pii(record)
            for record in records.values():
                if _linked(record, user_id):
                    _wipe_pii(record)
    for order in state.get("orders", {}).values():
        if not isinstance(order, dict):
            continue
        request = order.get("request", {})
        response = order.get("response", {})
        if _linked(request, user_id) or _linked(response, user_id):
            for record in (request, response):
                if isinstance(record, dict):
                    _wipe_pii(record)
            receipt = response.get("receipt") if isinstance(response, dict) else None
            if isinstance(receipt, dict):
                payload = receipt.get("payload")
                if isinstance(payload, dict):
                    _wipe_pii(payload)
    # Guest/viewer token stores may be installed by the QR branch. Wipe every
    # linked bearer and remember its hash so even a copied token is rejected.
    revoked = state.setdefault("revoked_token_hashes", [])
    for key in ("guest_tokens", "viewer_tokens", "sessions", "auth_tokens"):
        records = state.get(key, {})
        if not isinstance(records, dict):
            continue
        for token, record in list(records.items()):
            if _linked(record, user_id):
                for value in (token, record.get("token"), record.get("guest_token")):
                    if isinstance(value, str):
                        digest = hashlib.sha256(value.encode()).hexdigest()
                        if digest not in revoked:
                            revoked.append(digest)
                del records[token]
    erased = state.setdefault("revoked_users", [])
    if user_id not in erased:
        erased.append(user_id)
    return {"user_id": user_id, "status": "anonymized", "pii_retained": False,
            "tokens_wiped": True}


def token_is_revoked(state, token, claims=None):
    digest = hashlib.sha256(token.encode()).hexdigest()
    if digest in state.get("revoked_token_hashes", []):
        return True
    claims = claims or {}
    subject = claims.get("sub") or claims.get("user_id") or claims.get("player_id")
    return subject in state.get("revoked_users", [])


async def revocation_middleware(request, call_next):
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        claims = {}
        try:
            from .rbac import SECRET
            claims = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})
        except jwt.PyJWTError:
            pass
        if await __import__("asyncio").to_thread(read, lambda state: token_is_revoked(state, token, claims)):
            return JSONResponse(status_code=401, content={"error": {"code": "UNAUTHENTICATED",
                                "message": "Token revoked", "details": {}}})
    return await call_next(request)


@router.delete("/audit/v1/privacy/user/{user_id}")
def erase_user(user_id: str):
    if not identifier(user_id):
        bad("user_id")
    return mutate(lambda state: anonymize_user(state, user_id))
