"""Control live MediaMTX publishers when their key is rotated or revoked."""

import logging
import os

import httpx

LOG = logging.getLogger(__name__)
MEDIA_API = os.environ.get("MEDIAMTX_API_URL", "http://mediamtx:9997")


def disconnect_key(key: str) -> None:
    """Kick matching RTMP/WebRTC publishers; auth rejects any reconnect."""
    path = f"live/{key}"
    try:
        with httpx.Client(timeout=0.6) as client:
            for kind in ("rtmpconns", "webrtcsessions"):
                result = client.get(f"{MEDIA_API}/v3/{kind}/list")
                result.raise_for_status()
                for item in result.json().get("items", []):
                    if item.get("path") == path and item.get("state") in ("publish", "publishing"):
                        response = client.post(f"{MEDIA_API}/v3/{kind}/kick/{item['id']}")
                        response.raise_for_status()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # The API remains usable when media is intentionally offline for unit tests.
        LOG.warning("MediaMTX disconnect for %s failed: %s", path, exc)
