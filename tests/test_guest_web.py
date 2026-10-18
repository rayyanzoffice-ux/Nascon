from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_guest_pages_serve_required_selectors():
    response = client.get("/web/matches/demo-match")
    assert response.status_code == 200
    for selector in (
        "guest-video-player", "live-score-banner", "pinned-merch-card",
        "add-to-guest-cart-btn", "guest-cart-count", "chat-message-list",
        "chat-input-field", "chat-send-btn", "progressive-auth-modal",
    ):
        assert f'data-testid="{selector}"' in response.text


def test_match_route_extracts_match_identifier_before_live_suffix():
    response = client.get("/web/matches/match-m1/live")
    assert response.status_code == 200
    assert "pathParts[matchIndex+1]" in response.text


def test_guest_page_routes_are_deep_linkable():
    for path in ("/web/", "/web/costream/session-1", "/web/players/player-1", "/web/clubs/club-1"):
        assert client.get(path).status_code == 200
