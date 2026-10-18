from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_guest_pages_serve_required_selectors():
    response = client.get("/web/matches/demo-match")
    assert response.status_code == 200
    for selector in (
        "guest-player-shell", "guest-player-video", "guest-scoreboard",
        "guest-score-home", "guest-score-away", "guest-cart-items",
        "guest-cart", "guest-chat", "guest-auth-modal",
    ):
        assert f'data-testid="{selector}"' in response.text


def test_guest_page_routes_are_deep_linkable():
    for path in ("/web/", "/web/costream/session-1", "/web/players/player-1", "/web/clubs/club-1"):
        assert client.get(path).status_code == 200
