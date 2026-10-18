"""Prometheus text exposition over live backend state."""

from fastapi import APIRouter
from fastapi.responses import Response

from .core import read
from .notifications import active_connections

router = APIRouter()


def measurements(state):
    stream_records = state.get("stream_keys") or state.get("streams") or {}
    if isinstance(stream_records, dict):
        stream_records = stream_records.values()
    active = [row for row in stream_records if isinstance(row, dict) and
              row.get("status") in ("active", "live", "streaming")]
    bitrate = sum(max(0, row.get("bitrate_kbps", 0)) for row in active
                  if isinstance(row.get("bitrate_kbps", 0), (int, float)))
    qr_records = state.get("qr_telemetry") or state.get("qr_mappings") or {}
    if isinstance(qr_records, dict):
        qr_records = qr_records.values()
    scans = sum(max(0, row.get("scan_count", 0)) for row in qr_records
                if isinstance(row, dict) and type(row.get("scan_count", 0)) is int)
    return {"nascon_active_ws_connections": active_connections(),
            "nascon_active_streams_total": len(active),
            "nascon_stream_bitrate_kbps": bitrate,
            "nascon_dlq_depth": len(state.get("notification_dlq", [])),
            "nascon_qr_scans_total": scans}


@router.get("/metrics", include_in_schema=False)
def metrics():
    values = read(measurements)
    descriptions = {
        "nascon_active_ws_connections": ("gauge", "Current WebSocket connections"),
        "nascon_active_streams_total": ("gauge", "Current active streams"),
        "nascon_stream_bitrate_kbps": ("gauge", "Current stream bitrate in kilobits per second"),
        "nascon_dlq_depth": ("gauge", "Undelivered notification events"),
        "nascon_qr_scans_total": ("counter", "QR code scans recorded")}
    lines = []
    for name, value in values.items():
        kind, description = descriptions[name]
        lines.extend((f"# HELP {name} {description}", f"# TYPE {name} {kind}",
                      f"{name} {value}"))
    return Response("\n".join(lines) + "\n", headers={"Content-Type": "text/plain; version=0.0.4"})
