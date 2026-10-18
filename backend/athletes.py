"""Public athlete identity and idempotent, row-locked follower state."""

from fastapi import APIRouter, Request

from .app import body
from .core import bad, fail, mutate, read
from .streaming import player_exists
from .scoring import projection

router = APIRouter()


def profile(state, player_id):
    if not player_exists(state, player_id):
        fail(404, "PLAYER_NOT_FOUND")
    player = state.get("players", {}).get(player_id, {})
    club_id = state.get("rbac_players", {}).get(player_id)
    matches = []
    upcoming = []
    for match in state.get("matches", {}).values():
        events = match.get("events", [])
        club_match = club_id in (match.get("home"), match.get("away"))
        mentioned = any(isinstance(event, dict) and event.get("payload", {}).get("player_id") == player_id for event in events)
        status = projection(match, state["sports"])["status"]
        if (club_match and status == "completed") or mentioned:
            matches.append({"match_id": match.get("match_id"), "sport_id": match.get("sport_id"),
                            "event_count": len(events), "status": status})
        if club_match and status == "upcoming":
            upcoming.append({"match_id": match.get("match_id"), "sport_id": match.get("sport_id")})
    follows = state.get("athlete_follows", {})
    vods = [v for v in state.get("vod_index", {}).values() if v.get("player_id") == player_id]
    return {"player_id": player_id, "display_name": player.get("name", player_id),
            "club_id": club_id, "career_matches": matches, "upcoming_fixtures": upcoming,
            "vod_archive": sorted(vods, key=lambda v: v.get("started_at", ""), reverse=True),
            "follower_count": sum(1 for edge in follows.values() if edge["athlete_id"] == player_id)}


@router.get("/api/v1/athletes/{player_id}")
def athlete_profile(player_id: str):
    return read(lambda state: profile(state, player_id))


def follow_apply(state, athlete_id, follower_id, following):
    if not player_exists(state, athlete_id):
        fail(404, "PLAYER_NOT_FOUND")
    if not isinstance(follower_id, str) or not follower_id or type(following) is not bool:
        bad("follower_id", "following")
    if follower_id == athlete_id:
        bad("follower_id")
    edges = state.setdefault("athlete_follows", {})
    edge_id = f"{follower_id}|{athlete_id}"
    if following:
        edges[edge_id] = {"follower_id": follower_id, "athlete_id": athlete_id}
    else:
        edges.pop(edge_id, None)
    return {"athlete_id": athlete_id, "follower_id": follower_id, "following": following,
            "follower_count": sum(1 for edge in edges.values() if edge["athlete_id"] == athlete_id)}


@router.post("/api/v1/athletes/{player_id}/follow")
async def follow(req: Request, player_id: str):
    data = await body(req)
    return mutate(lambda state: follow_apply(state, player_id, data.get("follower_id"), data.get("following")))
