import hashlib
import hmac
import json
import time

import pytest

from backend import athletes, costream, streaming
from backend.core import APIError
from backend.seed import baseline
from media.compositor import command, desired
from media.vod_indexer import index_record


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setenv("DAY2_SALT", "T01D27ad7ffff12e")
    value = baseline()
    value["rbac_players"]["player-beta-2"] = "club-beta-1"
    return value


def expected_signature(entity_id, payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(b"T01D27ad7ffff12e", f"{entity_id}|{canonical}".encode(), hashlib.sha256).hexdigest()


def test_key_lifecycle_contract_and_media_revocation(state):
    key1 = "sk_live_9f83a1b2c3d4e5f6"
    result, stale = streaming.stream_key_apply(state, {"action": "generate", "player_id": "player-alpha-1", "stream_key_override": key1})
    assert stale == []
    assert result["status"] == "active"
    assert result["ingest_endpoints"]["rtmp"].endswith(key1)
    assert result["signature"] == expected_signature(key1, {"action": "generate", "player_id": "player-alpha-1", "status": "active", "stream_key": key1})
    key2 = "sk_live_1234567890abcdef"
    _, stale = streaming.stream_key_apply(state, {"action": "rotate", "player_id": "player-alpha-1", "stream_key_override": key2})
    assert stale == [key1]
    with pytest.raises(APIError) as error:
        streaming.authorize_media(state, {"action": "publish", "path": "live/" + key1})
    assert error.value.code == "KEY_REVOKED"
    assert streaming.authorize_media(state, {"action": "publish", "path": "live/" + key2})
    result, stale = streaming.stream_key_apply(state, {"action": "revoke", "player_id": "player-alpha-1"})
    assert stale == [key2]
    assert result["ingest_endpoints"] is None
    assert result["playback_url"] is None
    with pytest.raises(APIError) as error:
        streaming.authorize_media(state, {"action": "publish", "path": "live/" + key2})
    assert error.value.code == "KEY_REVOKED"
    with pytest.raises(APIError) as error:
        streaming.stream_key_apply(state, {"action": "revoke", "player_id": "player-alpha-1"})
    assert error.value.code == "STREAM_NOT_FOUND"


def test_key_validation_and_missing_player(state):
    with pytest.raises(APIError) as error:
        streaming.stream_key_apply(state, {"action": "bogus", "player_id": "player-alpha-1"})
    assert error.value.status == 400
    with pytest.raises(APIError) as error:
        streaming.stream_key_apply(state, {"action": "generate", "player_id": "missing"})
    assert error.value.status == 404 and error.value.code == "PLAYER_NOT_FOUND"


def test_costream_handoff_idempotency_and_signature(state):
    payload = {"session_id": "cs-session-101", "host_player_id": "player-alpha-1",
               "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2"],
               "layout": "grid_4", "simulate_host_drop": True}
    result, created = costream.session_apply(state, payload)
    assert created
    assert result["active_host"] == "player-alpha-2"
    assert result["participant_count"] == 3
    assert result["chat_room_id"] == "chat-cs-session-101"
    assert result["composite_playback_url"].endswith("/costream/cs-session-101/index.m3u8")
    signed = {k: result[k] for k in ("active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status")}
    assert result["signature"] == expected_signature("cs-session-101", signed)
    assert costream.session_apply(state, payload)[1] is False
    with pytest.raises(APIError) as error:
        costream.session_apply(state, {**payload, "layout": "spotlight"})
    assert error.value.status == 409


def test_costream_validation_order_and_sole_host(state):
    data = {"session_id": "cs-session-solo", "host_player_id": "player-alpha-1",
            "participants": ["player-alpha-1"], "layout": "solo", "simulate_host_drop": True}
    result, created = costream.session_apply(state, data)
    assert created and result["status"] == "terminated" and result["active_host"] is None
    with pytest.raises(APIError) as error:
        costream.session_apply(state, {**data, "participants": ["player-alpha-1", "missing"]})
    assert error.value.code == "PLAYER_NOT_FOUND"
    with pytest.raises(APIError) as error:
        costream.session_apply(state, {**data, "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2", "player-alpha-3"]})
    assert error.value.code == "PLAYER_NOT_FOUND"
    state["rbac_players"]["player-alpha-3"] = "club-alpha-1"
    with pytest.raises(APIError) as error:
        costream.session_apply(state, {**data, "participants": ["player-alpha-1", "player-alpha-2", "player-beta-1", "player-beta-2", "player-alpha-3"]})
    assert error.value.code == "COSTREAM_SESSION_FULL"
    with pytest.raises(APIError) as error:
        costream.session_apply(state, {**data, "simulate_host_drop": False, "participants": ["player-alpha-1", "player-alpha-2"]})
    assert error.value.code == "UNSUPPORTED_LAYOUT"


def test_follow_idempotency_and_recording_index(state):
    first = athletes.follow_apply(state, "player-alpha-1", "viewer-1", True)
    second = athletes.follow_apply(state, "player-alpha-1", "viewer-1", True)
    assert first["follower_count"] == second["follower_count"] == 1
    assert athletes.follow_apply(state, "player-alpha-1", "viewer-1", False)["follower_count"] == 0
    streaming.stream_key_apply(state, {"action": "generate", "player_id": "player-alpha-1", "stream_key_override": "sk_live_101"})
    indexed = index_record(state, "live/sk_live_101/part.mp4", "live/sk_live_101/part.mp4", 1024)
    assert indexed["player_id"] == "player-alpha-1"
    assert athletes.profile(state, "player-alpha-1")["vod_archive"][0]["vod_id"] == indexed["vod_id"]


def test_live_host_disconnect_keeps_chat_identity_and_cleans_last_host(state):
    request = {"session_id": "cs-session-live", "host_player_id": "player-alpha-1",
               "participants": ["player-alpha-1", "player-alpha-2"], "layout": "grid_2"}
    costream.session_apply(state, request)
    session = state["costream_sessions"]["cs-session-live"]
    session["chat_seq"] = 7
    result = costream.host_disconnect_apply(state, "cs-session-live", "player-alpha-1")
    assert result["active_host"] == "player-alpha-2"
    assert result["participant_count"] == 1
    assert result["chat_room_id"] == "chat-cs-session-live"
    assert session["chat_seq"] == 7
    result = costream.host_disconnect_apply(state, "cs-session-live", "player-alpha-2")
    assert result["status"] == "terminated"
    assert result["composite_playback_url"] is None


def test_overlay_reads_current_score_without_media_restart(state):
    request = {"session_id": "cs-session-overlay", "host_player_id": "player-alpha-1",
               "participants": ["player-alpha-1"], "layout": "solo"}
    costream.session_apply(state, request)
    session = state["costream_sessions"]["cs-session-overlay"]
    session["overlay"] = {"match_id": "match-test", "pinned_variant_ids": ["var-jersey-001-M"], "club_badges": {}}
    state["matches"]["match-test"] = {"match_id": "match-test", "sport_id": "football", "league_id": None,
                                     "home": "club-alpha-1", "away": "club-alpha-2", "events": []}
    first = costream.overlay_snapshot(state, "cs-session-overlay")
    state["matches"]["match-test"]["events"].append({"event_id": "start", "type": "match_start", "payload": {}, "signature": "x"})
    second = costream.overlay_snapshot(state, "cs-session-overlay")
    assert first["overlay"]["score"]["status"] == "upcoming"
    assert second["overlay"]["score"]["status"] == "in_progress"
    assert first["overlay"]["pinned_merchandise"][0]["stock"] == 1


def test_compositor_builds_real_ffmpeg_pipeline(monkeypatch):
    monkeypatch.setenv("MEDIA_INTERNAL_TOKEN", "test-private-token")
    args = command("cs-session-101", ["sk_live_101", "sk_live_102"], "grid_2")
    assert "ffmpeg" == args[0]
    assert any("hstack=inputs=2[v]" in arg for arg in args)
    assert "rtmp://mediamtx:1935/costream/cs-session-101?token=" in args[-1]


def test_host_moderation_changes_media_mix_and_invite_is_signed(state):
    request = {"session_id": "cs-session-moderation", "host_player_id": "player-alpha-1",
               "participants": ["player-alpha-1", "player-alpha-2"], "layout": "grid_2"}
    costream.session_apply(state, request)
    streaming.stream_key_apply(state, {"action": "generate", "player_id": "player-alpha-1", "stream_key_override": "sk_live_101"})
    streaming.stream_key_apply(state, {"action": "generate", "player_id": "player-alpha-2", "stream_key_override": "sk_live_102"})
    invite = costream.invite_token(state, "cs-session-moderation", "player-alpha-1", "player-alpha-2", 12345)
    assert "." in invite["invite_token"]
    assert len(invite["invite_token"].split(".")[1]) == 64
    costream.moderate_apply(state, "cs-session-moderation", "player-alpha-1", "mute", "player-alpha-1")
    assert desired(state)["cs-session-moderation"][2] == 1
    costream.moderate_apply(state, "cs-session-moderation", "player-alpha-1", "spotlight", "player-alpha-2")
    assert desired(state)["cs-session-moderation"][0][0] == "sk_live_102"
    costream.moderate_apply(state, "cs-session-moderation", "player-alpha-1", "kick", "player-alpha-2")
    assert state["costream_sessions"]["cs-session-moderation"]["participants"] == ["player-alpha-1"]
    invite = costream.invite_token(state, "cs-session-moderation", "player-alpha-1", "player-alpha-2", int(time.time()) + 60)
    joined = costream.join_apply(state, "cs-session-moderation", invite["invite_token"])
    assert joined["participant_count"] == 2
    assert costream.join_apply(state, "cs-session-moderation", invite["invite_token"])["participant_count"] == 2
