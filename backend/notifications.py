"""Persistent notification outbox, bounded retries, and live subscribers."""

import asyncio
import json
from threading import Lock

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from .core import identifier, mutate, read, utcnow

router = APIRouter()
_connection_lock = Lock()
_active_connections = 0


def active_connections():
    with _connection_lock:
        return _active_connections


def _connection_delta(delta):
    global _active_connections
    with _connection_lock:
        _active_connections += delta


def append_event(state, channel, event_type, payload):
    """Append inside an existing mutation; callers publish only committed changes."""
    serial = state.get("notification_serial", 0) + 1
    state["notification_serial"] = serial
    event = {"id": serial, "channel": channel, "type": event_type,
             "payload": payload, "created_at": utcnow()}
    state.setdefault("notification_events", []).append(event)
    # The outbox is an event window, while the DLQ keeps failed deliveries.
    state["notification_events"] = state["notification_events"][-2000:]
    return event


def publish_event(channel, event_type, payload):
    return mutate(lambda state: append_event(state, channel, event_type, payload))


def enqueue_failed_notification(state, channel, event_type, payload=None, attempts=3):
    serial = state.get("notification_dlq_serial", 0) + 1
    state["notification_dlq_serial"] = serial
    item = {"event_id": "notification-%d" % serial, "channel": channel,
            "type": event_type, "payload": payload or {}, "attempts": attempts,
            "failed_at": utcnow()}
    state.setdefault("notification_dlq", []).append(item)
    return item


async def deliver_with_retry(channel, event_type, payload, deliver, sleep=asyncio.sleep):
    """Try a downstream delivery three times, then commit one durable DLQ row."""
    for attempt in range(1, 4):
        try:
            await deliver(payload)
            return True
        except Exception:
            if attempt < 3:
                await sleep(0.05 * 2 ** (attempt - 1))
    await asyncio.to_thread(mutate, lambda state: enqueue_failed_notification(
        state, channel, event_type, payload, attempts=3))
    return False


def _events_since(state, channel, cursor):
    return [event for event in state.get("notification_events", [])
            if event["id"] > cursor and event["channel"] == channel]


def _match_snapshot(state, match_id):
    match = state.get("matches", {}).get(match_id)
    if match is None:
        return None
    from .scoring import projection
    result = projection(match, state["sports"])
    return {"match_id": match_id, "status": result["status"],
            "home": result["home"], "away": result["away"]}


async def _stream(channel, request=None, socket=None, match_id=None):
    cursor = 0
    last_snapshot = None
    while True:
        if request is not None and await request.is_disconnected():
            break
        events, snapshot = await asyncio.to_thread(read, lambda state: (
            _events_since(state, channel, cursor),
            _match_snapshot(state, match_id) if match_id else None))
        for event in events:
            cursor = max(cursor, event["id"])
            if socket is not None:
                await socket.send_json(event)
            else:
                yield "id: %s\nevent: %s\ndata: %s\n\n" % (
                    event["id"], event["type"], json.dumps(event, separators=(",", ":")))
        if snapshot is not None and snapshot != last_snapshot:
            last_snapshot = snapshot
            event = {"type": "score_update", "channel": channel, "payload": snapshot}
            if socket is not None:
                await socket.send_json(event)
            else:
                yield "event: score_update\ndata: %s\n\n" % json.dumps(event, separators=(",", ":"))
        await asyncio.sleep(0.1)


async def _websocket(socket, channel, match_id=None):
    await socket.accept()
    _connection_delta(1)
    try:
        async for _ in _stream(channel, socket=socket, match_id=match_id):
            pass
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        _connection_delta(-1)


@router.websocket("/ws/matches/{match_id}")
async def match_websocket(socket: WebSocket, match_id: str):
    if not identifier(match_id):
        await socket.close(code=1008)
        return
    await _websocket(socket, "match:" + match_id, match_id)


@router.get("/api/v1/matches/{match_id}/stream")
async def match_sse(req: Request, match_id: str):
    if not identifier(match_id):
        from .core import bad
        bad("match_id")
    return StreamingResponse(_stream("match:" + match_id, request=req, match_id=match_id),
                             media_type="text/event-stream")


@router.websocket("/ws/notifications/{channel}")
async def notification_websocket(socket: WebSocket, channel: str):
    if not identifier(channel):
        await socket.close(code=1008)
        return
    await _websocket(socket, channel)


@router.get("/api/v1/notifications/{channel}/stream")
async def notification_sse(req: Request, channel: str):
    if not identifier(channel):
        from .core import bad
        bad("channel")
    return StreamingResponse(_stream(channel, request=req), media_type="text/event-stream")
