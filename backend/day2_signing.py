"""Streaming adapter for Chat 01's shared Day 2 signing interface."""

import hashlib
import hmac
import os

from . import core


def sign_day2(entity_id: str, payload: dict) -> str:
    if hasattr(core, "sign_day2"):
        return core.sign_day2(entity_id, payload)
    # Compatibility while this isolated branch still starts from Day 1 main.
    salt = os.environ.get("DAY2_SALT")
    if not salt:
        raise RuntimeError("DAY2_SALT is required for signed Day 2 responses")
    message = (entity_id + "|" + core.canonical(payload)).encode("utf-8")
    return hmac.new(salt.encode("utf-8"), message, hashlib.sha256).hexdigest()
