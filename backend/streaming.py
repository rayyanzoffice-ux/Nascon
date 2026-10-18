"""Stream key lifecycle, MediaMTX authorization, and streaming metadata."""

import re
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .app import body
from .core import bad, fail, mutate, read
from .day2_signing import sign_day2
from .media_control import disconnect_key

router = APIRouter()
KEY = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def player_exists(state, player_id):
    return player_id in state.get("rbac_players", {}) or player_id in state.get("players", {})


def _new_key(state):
    while True:
        key = "sk_live_" + secrets.token_hex(8)
        if key not in state.setdefault("stream_keys", {}):
            return key


def stream_key_apply(state, data):
    action = data.get("action")
    player_id = data.get("player_id")
    label = data.get("label", "default")
    override = data.get("stream_key_override")
    if action not in ("generate", "rotate", "revoke") or not isinstance(player_id, str) or not player_id:
        bad("action", "player_id")
    if not isinstance(label, str) or not 1 <= len(label) <= 64:
        bad("label")
    if override is not None and (not isinstance(override, str) or not KEY.fullmatch(override)):
        bad("stream_key_override")
    if not player_exists(state, player_id):
        fail(404, "PLAYER_NOT_FOUND")
    keys = state.setdefault("stream_keys", {})
    active = state.setdefault("player_stream_keys", {})
    previous = active.get(player_id)
    if action == "revoke":
        if previous is None:
            fail(404, "STREAM_NOT_FOUND")
        record = keys[previous]
        record["status"] = "revoked"
        active.pop(player_id, None)
        key = previous
        label = record["label"]
        status = "revoked"
    else:
        key = override or _new_key(state)
        if key in keys and keys[key]["player_id"] != player_id:
            fail(409, "STREAM_KEY_CONFLICT")
        if previous and previous != key:
            keys[previous]["status"] = "revoked"
        keys[key] = {"player_id": player_id, "label": label, "status": "active"}
        active[player_id] = key
        status = "active"
    sig_payload = {"action": action, "player_id": player_id, "status": status, "stream_key": key}
    result = {"player_id": player_id, "label": label, "stream_key": key, "status": status,
              "ingest_endpoints": None, "playback_url": None,
              "signature": sign_day2(key, sig_payload)}
    if status == "active":
        result["ingest_endpoints"] = {
            "rtmp": f"rtmp://localhost:1935/live/{key}",
            "webrtc": f"http://localhost:8889/live/{key}/whip",
        }
        result["playback_url"] = f"http://localhost:8888/live/{key}/index.m3u8"
    return result, [old for old in (previous,) if old and (action == "revoke" or old != key)]


@router.post("/audit/v1/stream/key")
async def stream_key(req: Request):
    data = await body(req)
    result, stale = mutate(lambda state: stream_key_apply(state, data))
    for key in stale:
        disconnect_key(key)
    return JSONResponse(status_code=201 if data["action"] == "generate" else 200, content=result)


def authorize_media(state, data):
    path = data.get("path", "")
    action = data.get("action")
    if action in ("api", "metrics"):
        return data.get("ip") in ("127.0.0.1", "::1")
    if not isinstance(path, str):
        return False
    if path.startswith("live/"):
        key = path[5:]
        record = state.get("stream_keys", {}).get(key)
        if action == "publish":
            if record is None:
                return False
            if record["status"] == "revoked":
                fail(409, "KEY_REVOKED")
            return state.get("player_stream_keys", {}).get(record["player_id"]) == key
        return action in ("read", "playback") and record is not None and record["status"] == "active"
    if path.startswith("costream/"):
        session = state.get("costream_sessions", {}).get(path[9:])
        if action == "publish":
            return session is not None and session["status"] == "active" and data.get("token") == __import__("os").environ.get("MEDIA_INTERNAL_TOKEN") and bool(data.get("token"))
        return action in ("read", "playback") and session is not None and session["status"] == "active"
    return False


@router.post("/internal/mediamtx/auth")
async def mediamtx_auth(req: Request):
    data = await body(req)
    try:
        allowed = read(lambda state: authorize_media(state, data))
    except Exception as exc:
        if getattr(exc, "code", None) == "KEY_REVOKED":
            return JSONResponse(status_code=409, content={"error": {"code": "KEY_REVOKED"}})
        raise
    return JSONResponse(status_code=200 if allowed else 401, content={})


@router.get("/api/v1/stream/keys/{key}/authorize")
def authorize_stream_key(key: str):
    def check(state):
        record = state.get("stream_keys", {}).get(key)
        if record is None:
            fail(404, "STREAM_NOT_FOUND")
        if record["status"] != "active":
            fail(409, "KEY_REVOKED")
        return {"authorized": True, "player_id": record["player_id"]}
    return read(check)
