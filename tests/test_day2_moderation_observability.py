import asyncio
import copy
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from backend import moderation, notifications, observability, privacy
from backend.core import APIError, canonical
from backend.seed import baseline


def run_immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("Coroutine unexpectedly yielded")


def memory_store(monkeypatch):
    state = baseline()
    lock = Lock()

    def mutate(fn):
        with lock:
            return fn(state)

    def read(fn):
        with lock:
            return fn(copy.deepcopy(state))

    for module in (moderation, notifications, observability, privacy):
        monkeypatch.setattr(module, "mutate", mutate, raising=False)
        monkeypatch.setattr(module, "read", read, raising=False)
    return state, mutate


def request(room="chat-1", messages=None, failed=0):
    return {"chat_room_id": room, "incoming_messages": messages or [],
            "check_dlq": True, "simulate_failed_notifications": failed}


def test_audit_contract_order_masking_flood_and_signature(monkeypatch):
    state, _ = memory_store(monkeypatch)
    monkeypatch.setenv("DAY2_SALT", "test-day2-salt")
    data = request(messages=[
        {"message_id": "m1", "sender": "clean", "text": "Clean sports commentary"},
        {"message_id": "m2", "sender": "spammer", "text": "Watch b@d_w0rd and p.0.r.n now"},
        {"message_id": "m3", "sender": "flooder", "text": "GOAL! AAAA!!!"},
        {"message_id": "m4", "sender": "spammer", "text": "s!c@m f*u*c*k a$$h0le"}], failed=2)
    result = moderation.moderate(state, data, now=100)
    assert [row["message_id"] for row in result["filtered_messages"]] == ["m1", "m2", "m4"]
    assert result["filtered_messages"][1]["text"] == "Watch *** and *** now"
    assert result["filtered_messages"][2]["text"] == "*** *** ***"
    assert result["filtered_messages"][0]["reason"] is None
    assert result["kicked_users"] == ["spammer"]
    assert result["muted_users"] == ["flooder"]
    assert result["dlq_status"]["queue_depth"] == 2
    assert all(item["attempts"] == 3 for item in result["dlq_status"]["undelivered_events"])
    payload = {"chat_room_id": "chat-1", "flagged_count": 3,
               "kicked_users": ["spammer"], "queue_depth": 2}
    expected = hmac.new(b"test-day2-salt", ("chat-1|" + canonical(payload)).encode(), hashlib.sha256).hexdigest()
    assert result["signature"] == expected


def test_rate_window_and_duplicate_message(monkeypatch):
    state, _ = memory_store(monkeypatch)
    messages = [{"message_id": f"m{i}", "sender": "one", "text": "hello"} for i in range(4)]
    result = moderation.moderate(state, request(messages=messages), now=10)
    assert len(result["filtered_messages"]) == 3
    assert result["muted_users"] == ["one"]
    assert result["kicked_users"] == ["one"]
    again = moderation.moderate(state, request(messages=[messages[0]]), now=10.1)
    assert again["filtered_messages"][0]["text"] == "hello"
    assert len(state["moderation_rooms"]["chat-1"]["sender_times"]["one"]) == 4
    later = moderation.moderate(state, request(messages=[{"message_id": "m5", "sender": "one", "text": "later"}]), now=13)
    assert len(later["filtered_messages"]) == 1


def test_simultaneous_moderators_deduplicate_actions_and_dlq(monkeypatch):
    state, mutate = memory_store(monkeypatch)
    payload = request(messages=[{"message_id": "same", "sender": "user-spammer", "text": "b@d_w0rd"}], failed=1)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: mutate(lambda s: moderation.moderate(s, payload, now=10)), range(10)))
    assert all(row["kicked_users"] == ["user-spammer"] for row in results)
    assert state["moderation_rooms"]["chat-1"]["kicked_users"] == ["user-spammer"]
    assert len(state["notification_dlq"]) == 10
    assert len({row["event_id"] for row in state["notification_dlq"]}) == 10


def test_audit_http_validation_and_metrics(monkeypatch):
    memory_store(monkeypatch)
    try:
        moderation._validate({"chat_room_id": "chat-1"})
    except APIError as exc:
        assert exc.status == 400 and exc.code == "VALIDATION_ERROR"
        assert exc.details["fields"] == ["incoming_messages"]
    else:
        raise AssertionError("Missing messages must fail validation")

    class Request:
        async def body(self):
            return json.dumps(request(messages=[
                {"message_id": "m1", "sender": "u1", "text": "b@d_w0rd"}])).encode()

    result = run_immediate(moderation.moderation_test(Request()))
    assert result["kicked_users"] == ["u1"]
    assert b"nascon_dlq_depth 0" in observability.metrics().body


def test_notification_retry_and_persisted_outbox(monkeypatch):
    state, _ = memory_store(monkeypatch)
    attempts, delays = [], []

    async def to_thread(fn, *args):
        return fn(*args)

    monkeypatch.setattr(notifications.asyncio, "to_thread", to_thread)

    async def failed(payload):
        attempts.append(payload)
        raise OSError("downstream unavailable")

    async def sleep(delay):
        delays.append(delay)

    assert run_immediate(notifications.deliver_with_retry("room", "invite", {"x": 1}, failed, sleep)) is False
    assert len(attempts) == 3 and delays == [0.05, 0.1]
    assert len(state["notification_dlq"]) == 1
    event = notifications.publish_event("room", "order_paid", {"order_id": "o1"})
    assert event["id"] == 1
    assert state["notification_events"][0]["payload"]["order_id"] == "o1"


def test_metrics_are_live_state(monkeypatch):
    state, _ = memory_store(monkeypatch)
    state["stream_keys"] = {"s1": {"status": "active", "bitrate_kbps": 1300},
                            "s2": {"status": "revoked", "bitrate_kbps": 900}}
    state["qr_mappings"] = {"q": {"scan_count": 7}}
    notifications.enqueue_failed_notification(state, "x", "failed")
    response = observability.metrics()
    assert response.headers["content-type"] == "text/plain; version=0.0.4"
    content = response.body.decode()
    for name in ("nascon_active_ws_connections", "nascon_active_streams_total",
                 "nascon_stream_bitrate_kbps", "nascon_dlq_depth", "nascon_qr_scans_total"):
        assert "# TYPE " + name in content
    assert "nascon_active_streams_total 1\n" in content
    assert "nascon_stream_bitrate_kbps 1300\n" in content
    assert "nascon_dlq_depth 1\n" in content
    assert "nascon_qr_scans_total 7\n" in content


def test_privacy_anonymizes_and_revokes_linked_tokens(monkeypatch):
    state, _ = memory_store(monkeypatch)
    state["players"]["player-alpha-1"] = {"player_id": "player-alpha-1", "name": "Alice", "email": "a@example.com"}
    state["guest_tokens"] = {"guest-secret": {"registered_user_id": "player-alpha-1", "token": "bearer-secret"}}
    state["orders"]["o1"] = {"request": {"customer_id": "player-alpha-1", "email": "a@example.com"},
                              "response": {"customer_id": "player-alpha-1", "receipt": {"payload": {"email": "a@example.com"}}}}
    result = privacy.anonymize_user(state, "player-alpha-1")
    assert result == {"user_id": "player-alpha-1", "status": "anonymized", "pii_retained": False, "tokens_wiped": True}
    assert state["players"]["player-alpha-1"]["name"] == "Anonymized User"
    assert state["players"]["player-alpha-1"]["email"] is None
    assert state["orders"]["o1"]["request"]["email"] is None
    assert state["orders"]["o1"]["response"]["receipt"]["payload"]["email"] is None
    assert state["guest_tokens"] == {}
    assert privacy.token_is_revoked(state, "guest-secret")
    assert privacy.token_is_revoked(state, "bearer-secret")
    assert privacy.token_is_revoked(state, "jwt", {"sub": "player-alpha-1"})
