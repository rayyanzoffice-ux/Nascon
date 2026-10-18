"""Shared Phase II HMAC interface for QR, cart, and streaming routes."""

import hashlib
import hmac
import os

from .core import canonical


def sign_day2(entity_id: str, payload: dict) -> str:
    salt = os.environ.get("DAY2_SALT")
    if not salt:
        raise RuntimeError("DAY2_SALT is required for signed Day 2 responses")
    message = (entity_id + "|" + canonical(payload)).encode("utf-8")
    return hmac.new(salt.encode("utf-8"), message, hashlib.sha256).hexdigest()
