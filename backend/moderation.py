"""Synchronous chat filtering and the deterministic Day 2 audit probe."""

import asyncio
import hashlib
import hmac
import os
import re
import time
import unicodedata

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from .app import body
from .core import bad, canonical, identifier, mutate
from .notifications import enqueue_failed_notification

router = APIRouter()

PROFANITY = ("idiotspam", "badword", "asshole", "bitch", "sicam", "scam", "porn", "fuck", "shit")
SUBSTITUTIONS = str.maketrans({"@": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s"})
SEPARATORS = frozenset("_.*-")
ZERO_WIDTH = frozenset("\u200b\u200c\u200d\ufeff\u2060")
FLOOD = re.compile(r"(.)\1{3,}|[!?]{3,}", re.IGNORECASE | re.DOTALL)


def _normalized_with_positions(value):
    normalized, positions = [], []
    for index, char in enumerate(value):
        if char in ZERO_WIDTH or char in SEPARATORS:
            continue
        folded = unicodedata.normalize("NFKC", char).lower().translate(SUBSTITUTIONS)
        for letter in folded:
            if letter.isalnum():
                normalized.append(letter)
                positions.append(index)
            elif not normalized or normalized[-1] != "|":
                normalized.append("|")
                positions.append(index)
    return "".join(normalized), positions


def mask_profanity(value):
    normalized, positions = _normalized_with_positions(value)
    matches = []
    for token in PROFANITY:
        for match in re.finditer(re.escape(token), normalized):
            before = normalized[match.start() - 1] if match.start() else ""
            after = normalized[match.end()] if match.end() < len(normalized) else ""
            if (before and before.isalnum()) or (after and after.isalnum()):
                continue
            matches.append((positions[match.start()], positions[match.end() - 1] + 1))
    if not matches:
        return value, False
    selected = []
    for start, end in sorted(matches):
        if selected and start < selected[-1][1]:
            if end > selected[-1][1]:
                selected[-1] = (selected[-1][0], end)
        else:
            selected.append((start, end))
    for start, end in reversed(selected):
        value = value[:start] + "***" + value[end:]
    return value, True


def sign_moderation(room_id, flagged_count, kicked_users, queue_depth):
    payload = {"chat_room_id": room_id, "flagged_count": flagged_count,
               "kicked_users": kicked_users, "queue_depth": queue_depth}
    message = room_id + "|" + canonical(payload)
    return hmac.new(os.environ.get("DAY2_SALT", "").encode("utf-8"),
                    message.encode("utf-8"), hashlib.sha256).hexdigest()


def _validate(data):
    fields = []
    if not identifier(data.get("chat_room_id")):
        fields.append("chat_room_id")
    messages = data.get("incoming_messages")
    if not isinstance(messages, list):
        fields.append("incoming_messages")
    else:
        for message in messages:
            if (not isinstance(message, dict) or
                not identifier(message.get("message_id")) or
                not identifier(message.get("sender")) or
                not isinstance(message.get("text"), str)):
                fields.append("incoming_messages")
                break
    if "check_dlq" in data and type(data["check_dlq"]) is not bool:
        fields.append("check_dlq")
    count = data.get("simulate_failed_notifications", 0)
    if type(count) is not int or count < 0 or count > 1000:
        fields.append("simulate_failed_notifications")
    if fields:
        bad(*fields)


def moderate(state, data, now=None):
    _validate(data)
    now = time.time() if now is None else now
    room_id = data["chat_room_id"]
    rooms = state.setdefault("moderation_rooms", {})
    room = rooms.setdefault(room_id, {"kicked_users": [], "muted_users": [], "sender_times": {}, "seen": {}})
    kicked, muted = room["kicked_users"], room["muted_users"]
    filtered, flagged_count = [], 0
    for message in data["incoming_messages"]:
        sender, original = message["sender"], message["text"]
        seen_key = message["message_id"]
        if seen_key in room["seen"]:
            prior = room["seen"][seen_key]
            if prior is not None:
                filtered.append(prior)
                flagged_count += int(prior["flagged"])
            continue
        times = room["sender_times"].setdefault(sender, [])
        times[:] = [entry for entry in times if entry > now - 2]
        times.append(now)
        repeated = bool(FLOOD.search(original))
        if repeated or len(times) > 3:
            if sender not in muted:
                muted.append(sender)
            if len(times) > 3 and sender not in kicked:
                kicked.append(sender)
            room["seen"][seen_key] = None
            flagged_count += 1
            continue
        masked, profane = mask_profanity(original)
        output = {"message_id": seen_key, "sender": sender, "text": masked,
                  "flagged": profane, "reason": "profanity_leetspeak" if profane else None}
        if profane:
            flagged_count += 1
            if sender not in kicked:
                kicked.append(sender)
        filtered.append(output)
        room["seen"][seen_key] = output
    # The audit probe models failed deliveries after all three bounded attempts.
    for _ in range(data.get("simulate_failed_notifications", 0)):
        enqueue_failed_notification(state, room_id, "moderation.notification")
    dlq = state.setdefault("notification_dlq", [])
    response = {"chat_room_id": room_id, "filtered_messages": filtered,
                "kicked_users": list(kicked), "muted_users": list(muted),
                "dlq_status": {"queue_depth": len(dlq), "undelivered_events": list(dlq)}}
    response["signature"] = sign_moderation(room_id, flagged_count, response["kicked_users"], len(dlq))
    return response


@router.post("/audit/v1/moderation/test")
async def moderation_test(req: Request):
    data = await body(req)
    _validate(data)
    # PostgreSQL is synchronous. Running this transaction on the event loop
    # stalls every QR and score response while chat writes wait for the shared
    # state row lock under load.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Some contract unit tests drive this coroutine directly without an
        # event loop; preserve that harness while the ASGI path uses a worker.
        return mutate(lambda state: moderate(state, data))
    return await run_in_threadpool(mutate, lambda state: moderate(state, data))

