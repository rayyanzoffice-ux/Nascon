"""Stable QR links resolved against current database state."""

from datetime import datetime, timezone
from io import BytesIO
import hashlib

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
import qrcode
from qrcode.image.svg import SvgPathImage
from reportlab.pdfgen import canvas

from .core import fail, mutate, read, read_fragment
from .day2_signing import sign_day2
from .scoring import projection

router = APIRouter()
BASE_URL = "http://localhost:8080"


def entity_details(state, entity_id):
    if entity_id in state.get("matches", {}):
        match = state["matches"][entity_id]
        status = match.get("status") or projection(match, state["sports"])["status"]
        suffix = {"upcoming": "preview", "in_progress": "live", "completed": "vod"}.get(status)
        if suffix:
            target = f"/web/matches/{entity_id}/{suffix}"
        elif status in ("postponed", "cancelled", "abandoned"):
            target = f"/web/matches/{entity_id}/notice?state={status}"
        else:
            fail(404, "QR_NOT_FOUND")
        return "match", status, target
    if entity_id in state.get("rbac_players", {}) or entity_id in state.get("players", {}):
        return "player", "active", f"/web/players/{entity_id}"
    if entity_id in state.get("clubs", {}):
        return "club", "active", f"/web/clubs/{entity_id}"
    if entity_id in state.get("costream_sessions", {}):
        session = state["costream_sessions"][entity_id]
        return "costream", session.get("status", "active"), f"/web/costream/{entity_id}"
    fail(404, "QR_NOT_FOUND")


def short_code(state, entity_id):
    codes = state.setdefault("qr_codes", {})
    if entity_id in codes:
        return codes[entity_id]
    preferred = "m1-live" if entity_id == "match-m1" else entity_id.lower()
    used = {code for owner, code in codes.items() if owner != entity_id}
    code = preferred
    if code in used:
        code = preferred + "-" + hashlib.sha256(entity_id.encode()).hexdigest()[:8]
    codes[entity_id] = code
    return code


def record_scan(state, entity_id, user_agent):
    data = state.setdefault("qr_telemetry", {}).setdefault(entity_id, {"scan_count": 0, "buckets": {}})
    data["scan_count"] += 1
    device = "mobile" if any(word in user_agent.lower() for word in ("android", "iphone", "ipad", "mobile")) else "desktop"
    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    key = bucket + "|" + device
    data["buckets"][key] = data["buckets"].get(key, 0) + 1
    return data["scan_count"]


def resolve(state, entity_id, *, inspect=False, user_agent=""):
    entity_type, status, target = entity_details(state, entity_id)
    code = short_code(state, entity_id)
    short_url = f"{BASE_URL}/q/{code}"
    scan_count = state.get("qr_telemetry", {}).get(entity_id, {}).get("scan_count", 0)
    if not inspect:
        scan_count = record_scan(state, entity_id, user_agent)
    payload = {"entity_id": entity_id, "short_url": short_url, "target_route": target}
    return {"entity_id": entity_id, "entity_type": entity_type, "entity_status": status,
            "short_url": short_url, "target_route": target, "deep_link_uri": f"nascon://entity/{entity_id}",
            "scan_count": scan_count,
            "export_formats": {fmt: f"{BASE_URL}/audit/v1/qr/{entity_id}/export.{fmt}" for fmt in ("svg", "png", "pdf")},
            "signature": sign_day2(entity_id, payload)}


_QR_INSPECT_FRAGMENT = """
SELECT jsonb_build_object(
  'matches', jsonb_strip_nulls(jsonb_build_object(%s, doc->'matches'->%s)),
  'players', jsonb_strip_nulls(jsonb_build_object(%s, doc->'players'->%s)),
  'rbac_players', jsonb_strip_nulls(jsonb_build_object(%s, doc->'rbac_players'->%s)),
  'clubs', jsonb_strip_nulls(jsonb_build_object(%s, doc->'clubs'->%s)),
  'costream_sessions', jsonb_strip_nulls(jsonb_build_object(%s, doc->'costream_sessions'->%s)),
  'sports', doc->'sports',
  'qr_codes', jsonb_strip_nulls(jsonb_build_object(%s, doc->'qr_codes'->%s)),
  'qr_telemetry', jsonb_strip_nulls(jsonb_build_object(%s, doc->'qr_telemetry'->%s))
) FROM app_state WHERE id=1
"""


def inspect_metadata(entity_id):
    params = (entity_id, entity_id) * 7
    state = read_fragment(_QR_INSPECT_FRAGMENT, params, lambda value: value)
    # An unseen entity needs a durable short-code allocation; existing codes,
    # including all official fixtures, remain entirely read-only.
    if entity_id not in state.get("qr_codes", {}):
        return mutate(lambda full_state: resolve(full_state, entity_id, inspect=True))
    return resolve(state, entity_id, inspect=True)


@router.get("/audit/v1/qr/{entity_id}")
def qr_metadata(req: Request, entity_id: str, inspect: bool = False):
    # Inspect is the signed, read-only audit view.  It must not contend with
    # real scans, which still record telemetry atomically below.
    if inspect:
        return inspect_metadata(entity_id)
    return mutate(lambda state: resolve(state, entity_id, inspect=False, user_agent=req.headers.get("user-agent", "")))


@router.get("/q/{short_code}")
def qr_redirect(req: Request, short_code: str):
    def lookup(state):
        if short_code == "m1-live" and "match-m1" in state.get("matches", {}):
            entity_id = "match-m1"
        else:
            entity_id = next((entity for entity, code in state.get("qr_codes", {}).items() if code == short_code), None)
            if entity_id is None and short_code in state.get("matches", {}) | state.get("clubs", {}) | state.get("rbac_players", {}) | state.get("costream_sessions", {}):
                entity_id = short_code
        if entity_id is None:
            fail(404, "QR_NOT_FOUND")
        return resolve(state, entity_id, user_agent=req.headers.get("user-agent", ""))["target_route"]
    target = mutate(lookup)
    return RedirectResponse(target, status_code=302)


def qr_image():
    return qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)


@router.get("/audit/v1/qr/{entity_id}/export.{fmt}")
def export_qr(entity_id: str, fmt: str):
    if fmt not in ("svg", "png", "pdf"):
        fail(404, "QR_NOT_FOUND")
    metadata = mutate(lambda state: resolve(state, entity_id, inspect=True))
    qr = qr_image()
    qr.add_data(metadata["short_url"])
    qr.make(fit=True)
    if fmt == "svg":
        image = qr.make_image(image_factory=SvgPathImage)
        stream = BytesIO()
        image.save(stream)
        return Response(stream.getvalue(), media_type="image/svg+xml")
    if fmt == "png":
        stream = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(stream, format="PNG")
        return Response(stream.getvalue(), media_type="image/png")
    stream = BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842))
    page.setTitle("NaSCon QR " + entity_id)
    page.setFont("Helvetica-Bold", 22)
    page.drawString(55, 770, "NaSCon 2026")
    page.setFont("Helvetica", 14)
    page.drawString(55, 740, entity_id)
    matrix = qr.get_matrix()
    size = 440 / len(matrix)
    page.setFillColorRGB(0, 0, 0)
    for row, pixels in enumerate(matrix):
        for col, filled in enumerate(pixels):
            if filled:
                page.rect(78 + col * size, 190 + (len(matrix) - row - 1) * size, size, size, fill=1, stroke=0)
    page.setFont("Helvetica", 10)
    page.drawString(55, 155, metadata["short_url"])
    page.showPage()
    page.save()
    return Response(stream.getvalue(), media_type="application/pdf")
