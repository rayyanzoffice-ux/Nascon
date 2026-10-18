"""Co-stream session state and deterministic audience metadata."""

import time
import asyncio
import json
import base64
import hmac
import binascii

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from .app import body
from .core import bad, fail, mutate, read, identifier
from .day2_signing import sign_day2
from .streaming import player_exists
from .scoring import projection

router = APIRouter()
LAYOUTS = {"solo": 1, "grid_2": 2, "grid_4": 4, "spotlight": 4}


def session_apply(state, data):
    session_id = data.get("session_id")
    host = data.get("host_player_id")
    participants = data.get("participants")
    layout = data.get("layout", "grid_4")
    dropped = data.get("simulate_host_drop", False)
    if (not identifier(session_id)
        or not isinstance(host, str) or not isinstance(participants, list) or not participants
        or any(not isinstance(p, str) or not p for p in participants)
        or len(set(participants)) != len(participants) or type(dropped) is not bool
        or not isinstance(layout, str) or layout not in LAYOUTS):
        bad("session_id", "host_player_id", "participants", "layout", "simulate_host_drop")
    if any(not player_exists(state, p) for p in [*participants, host]):
        fail(404, "PLAYER_NOT_FOUND")
    if host not in participants:
        bad("host_player_id")
    if len(participants) > 4:
        fail(409, "COSTREAM_SESSION_FULL")
    effective = [p for p in participants if p != host] if dropped else list(participants)
    if len(effective) > LAYOUTS[layout]:
        fail(400, "UNSUPPORTED_LAYOUT")
    request = {"session_id": session_id, "host_player_id": host,
               "participants": list(participants), "layout": layout, "simulate_host_drop": dropped}
    sessions = state.setdefault("costream_sessions", {})
    prior = sessions.get(session_id)
    if prior is not None:
        if prior["request"] != request:
            fail(409, "COSTREAM_SESSION_CONFLICT")
        return prior["response"], False
    active_host = effective[0] if dropped and effective else host if effective else None
    status = "active" if effective else "terminated"
    sig_payload = {"active_host": active_host, "handoff_occurred": dropped and bool(effective),
                   "layout": layout, "participant_count": len(effective),
                   "session_id": session_id, "status": status}
    response = {"session_id": session_id, "status": status, "active_host": active_host,
                "handoff_occurred": sig_payload["handoff_occurred"],
                "participant_count": len(effective), "active_participants": effective,
                "layout": layout,
                "composite_playback_url": f"http://localhost:8888/costream/{session_id}/index.m3u8" if effective else None,
                "chat_room_id": f"chat-{session_id}",
                "signature": sign_day2(session_id, sig_payload)}
    sessions[session_id] = {"request": request, "response": response, "status": status,
                            "participants": effective, "host": active_host,
                            "layout": layout, "chat_seq": 0, "chat": [], "overlay_seq": 0,
                            "overlay": {}, "muted": [], "spotlight": None, "created_at": time.time()}
    return response, True


@router.post("/audit/v1/costream/session")
async def costream_session(req: Request):
    # Parse before entering the synchronous, row-locked state transaction.
    data = await body(req)
    response, created = mutate(lambda state: session_apply(state, data))
    return JSONResponse(status_code=201 if created else 200, content=response)


def host_disconnect_apply(state, session_id, player_id):
    session = state.get("costream_sessions", {}).get(session_id)
    if session is None:
        fail(404, "COSTREAM_SESSION_NOT_FOUND")
    if player_id not in session["participants"]:
        return session["response"]
    was_host = session["host"] == player_id
    session["participants"] = [p for p in session["participants"] if p != player_id]
    if was_host:
        session["host"] = session["participants"][0] if session["participants"] else None
    session["status"] = "active" if session["participants"] else "terminated"
    response = session["response"]
    response.update(active_host=session["host"], participant_count=len(session["participants"]),
                    active_participants=list(session["participants"]), status=session["status"],
                    handoff_occurred=was_host and bool(session["participants"]),
                    composite_playback_url=f"http://localhost:8888/costream/{session_id}/index.m3u8" if session["participants"] else None)
    signed = {k: response[k] for k in ("active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status")}
    response["signature"] = sign_day2(session_id, signed)
    return response


@router.post("/api/v1/costream/{session_id}/disconnect")
async def disconnect(req: Request, session_id: str):
    data = await body(req)
    player_id = data.get("player_id")
    if not isinstance(player_id, str):
        bad("player_id")
    return mutate(lambda state: host_disconnect_apply(state, session_id, player_id))


@router.post("/api/v1/costream/{session_id}/chat")
async def post_chat(req: Request, session_id: str):
    data = await body(req)
    user_id, message = data.get("user_id"), data.get("message")
    if not isinstance(user_id, str) or not isinstance(message, str) or not 1 <= len(message) <= 1000:
        bad("user_id", "message")
    def append(state):
        session = state.get("costream_sessions", {}).get(session_id)
        if session is None or session["status"] != "active":
            fail(404, "COSTREAM_SESSION_NOT_FOUND")
        from .moderation import moderate
        moderation = moderate(state, {"chat_room_id": f"chat-{session_id}",
                                      "incoming_messages": [{"message_id": f"chat-{session['chat_seq'] + 1}", "sender": user_id, "text": message}],
                                      "check_dlq": False, "simulate_failed_notifications": 0})
        if not moderation["filtered_messages"]:
            return {"blocked": True, "sequence": session["chat_seq"], "user_id": user_id, "message": ""}
        message = moderation["filtered_messages"][0]["text"]
        session["chat_seq"] += 1
        item = {"sequence": session["chat_seq"], "user_id": user_id, "message": message,
                "timestamp_ms": int(time.time() * 1000)}
        session["chat"].append(item)
        return item
    return mutate(append)


@router.get("/api/v1/costream/{session_id}/chat")
def get_chat(session_id: str, after: int = 0):
    def retrieve(state):
        session = state.get("costream_sessions", {}).get(session_id)
        if session is None:
            fail(404, "COSTREAM_SESSION_NOT_FOUND")
        return {"chat_room_id": f"chat-{session_id}", "messages": [x for x in session["chat"] if x["sequence"] > after]}
    return read(retrieve)


@router.websocket("/api/v1/costream/{session_id}/presence/{player_id}")
async def presence(websocket: WebSocket, session_id: str, player_id: str):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        mutate(lambda state: host_disconnect_apply(state, session_id, player_id))


def overlay_snapshot(state, session_id):
    session = state.get("costream_sessions", {}).get(session_id)
    if session is None:
        fail(404, "COSTREAM_SESSION_NOT_FOUND")
    overlay = dict(session["overlay"])
    match_id = overlay.get("match_id")
    if match_id in state.get("matches", {}):
        score = projection(state["matches"][match_id], state["sports"])
        overlay["score"] = {"home": score["home"], "away": score["away"],
                            "status": score["status"], "version": score["version"]}
    overlay["pinned_merchandise"] = [
        {"variant_id": item, "stock": state.get("inventory", {}).get(item, {}).get("stock")}
        for item in overlay.get("pinned_variant_ids", [])]
    return {"session_id": session_id, "sequence": session["overlay_seq"], "overlay": overlay,
            "chat_room_id": f"chat-{session_id}"}


def invite_token(state, session_id, host_id, invited_id, expires_at):
    session = state.get("costream_sessions", {}).get(session_id)
    if session is None or session["status"] != "active":
        fail(404, "COSTREAM_SESSION_NOT_FOUND")
    if session["host"] != host_id or not player_exists(state, invited_id):
        fail(403, "FORBIDDEN")
    payload = {"session_id": session_id, "player_id": invited_id, "expires_at": expires_at}
    packed = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return {"invite_token": packed + "." + sign_day2(session_id, payload), "expires_at": expires_at}


def join_apply(state, session_id, token):
    if not isinstance(token, str) or "." not in token:
        bad("invite_token")
    packed, signature = token.rsplit(".", 1)
    try:
        payload = json.loads(base64.urlsafe_b64decode(packed + "=" * (-len(packed) % 4)))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        bad("invite_token")
    if not isinstance(payload, dict) or payload.get("session_id") != session_id or not isinstance(payload.get("player_id"), str) or type(payload.get("expires_at")) is not int:
        bad("invite_token")
    if not hmac.compare_digest(signature, sign_day2(session_id, payload)) or payload["expires_at"] < int(time.time()):
        fail(403, "INVALID_INVITE")
    session = state.get("costream_sessions", {}).get(session_id)
    if session is None or session["status"] != "active":
        fail(404, "COSTREAM_SESSION_NOT_FOUND")
    player_id = payload["player_id"]
    if not player_exists(state, player_id):
        fail(404, "PLAYER_NOT_FOUND")
    if player_id not in session["participants"]:
        if len(session["participants"]) >= 4:
            fail(409, "COSTREAM_SESSION_FULL")
        if len(session["participants"]) >= LAYOUTS[session["layout"]]:
            fail(400, "UNSUPPORTED_LAYOUT")
        session["participants"].append(player_id)
        response = session["response"]
        response["active_participants"] = list(session["participants"])
        response["participant_count"] = len(session["participants"])
        signed = {k: response[k] for k in ("active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status")}
        response["signature"] = sign_day2(session_id, signed)
    return {"session_id": session_id, "player_id": player_id, "participant_count": len(session["participants"]),
            "composite_playback_url": session["response"]["composite_playback_url"]}


@router.post("/api/v1/costream/{session_id}/invite")
async def invite(req: Request, session_id: str):
    data = await body(req)
    host, invited = data.get("host_player_id"), data.get("player_id")
    if not isinstance(host, str) or not isinstance(invited, str):
        bad("host_player_id", "player_id")
    expires_at = int(time.time()) + 600
    return read(lambda state: invite_token(state, session_id, host, invited, expires_at))


@router.post("/api/v1/costream/{session_id}/join")
async def join(req: Request, session_id: str):
    data = await body(req)
    return mutate(lambda state: join_apply(state, session_id, data.get("invite_token")))


def moderate_apply(state, session_id, host_id, action, target):
    session = state.get("costream_sessions", {}).get(session_id)
    if session is None or session["status"] != "active":
        fail(404, "COSTREAM_SESSION_NOT_FOUND")
    if host_id != session["host"]:
        fail(403, "FORBIDDEN")
    if action not in ("mute", "unmute", "spotlight", "kick") or target not in session["participants"]:
        bad("action", "player_id")
    if action == "kick":
        host_disconnect_apply(state, session_id, target)
    elif action == "spotlight":
        session["spotlight"] = target
        session["layout"] = "spotlight"
        session["response"]["layout"] = "spotlight"
    elif action == "mute":
        session["muted"] = sorted(set(session["muted"]) | {target})
    else:
        session["muted"] = [p for p in session["muted"] if p != target]
    response = session["response"]
    signed = {k: response[k] for k in ("active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status")}
    response["signature"] = sign_day2(session_id, signed)
    session["overlay_seq"] += 1
    return {"session_id": session_id, "action": action, "player_id": target,
            "active_host": session["host"], "muted_participants": session["muted"],
            "spotlight_player_id": session["spotlight"], "status": session["status"]}


@router.post("/api/v1/costream/{session_id}/moderate")
async def moderate(req: Request, session_id: str):
    data = await body(req)
    return mutate(lambda state: moderate_apply(state, session_id, data.get("host_player_id"),
                                                data.get("action"), data.get("player_id")))


@router.post("/api/v1/costream/{session_id}/overlay")
async def update_overlay(req: Request, session_id: str):
    data = await body(req)
    if not isinstance(data.get("match_id"), str) or not isinstance(data.get("club_badges", {}), dict) or not isinstance(data.get("pinned_variant_ids", []), list):
        bad("match_id", "club_badges", "pinned_variant_ids")
    def change(state):
        session = state.get("costream_sessions", {}).get(session_id)
        if session is None:
            fail(404, "COSTREAM_SESSION_NOT_FOUND")
        session["overlay"] = {"match_id": data["match_id"], "club_badges": data.get("club_badges", {}),
                              "pinned_variant_ids": data.get("pinned_variant_ids", [])}
        session["overlay_seq"] += 1
        return overlay_snapshot(state, session_id)
    return mutate(change)


@router.get("/api/v1/costream/{session_id}/events")
async def events(session_id: str, after_chat: int = 0, after_overlay: int = 0):
    async def generate():
        chat_cursor, overlay_cursor = after_chat, after_overlay
        while True:
            snapshot = read(lambda state: (
                state.get("costream_sessions", {}).get(session_id, {}).get("chat", []),
                overlay_snapshot(state, session_id)))
            messages, overlay = snapshot
            for message in messages:
                if message["sequence"] > chat_cursor:
                    chat_cursor = message["sequence"]
                    yield f"event: chat\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
            if overlay["sequence"] > overlay_cursor:
                overlay_cursor = overlay["sequence"]
                yield f"event: overlay\ndata: {json.dumps(overlay, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.2)
    return StreamingResponse(generate(), media_type="text/event-stream")
