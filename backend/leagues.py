from fastapi import APIRouter, Request
from .app import body
from .core import bad, fail, identifier, integer, mutate, validate_order
from .scoring import new_match
router=APIRouter()

@router.post("/audit/v1/leagues",status_code=201)
async def create_league(req:Request):
    d=await body(req)
    lid=d.get("league_id");sport=d.get("sport_id");teams=d.get("teams");fx=d.get("fixtures")
    pts=d.get("points",{"win":3,"draw":1,"loss":0});q=d.get("qualification")
    if not identifier(lid) or not identifier(sport) or not isinstance(teams,list) or not 2<=len(teams)<=40 or any(not identifier(t) for t in teams) or len(set(teams))!=len(teams):bad("league_id","sport_id","teams")
    if not isinstance(fx,list) or any(not isinstance(f,dict) or not identifier(f.get("match_id")) or f.get("home") not in teams or f.get("away") not in teams or f["home"]==f["away"] for f in fx):bad("fixtures")
    if len(set(f["match_id"] for f in fx))!=len(fx):bad("fixtures")
    if not isinstance(q,dict) or not integer(q.get("spots")) or not 1<=q["spots"]<=len(teams):bad("qualification")
    if not isinstance(pts,dict) or any(not integer(pts.get(k)) for k in ("win","draw","loss")):bad("points")
    if "lots_seed" in d and not integer(d["lots_seed"]):bad("lots_seed")
    def change(s):
        if sport not in s["sports"]:fail(404,"SPORT_NOT_FOUND")
        if lid in s["leagues"]:fail(409,"LEAGUE_EXISTS")
        if any(f["match_id"] in s["matches"] for f in fx):fail(409,"MATCH_EXISTS")
        order=validate_order(d.get("tie_break_order"),s["sports"][sport]["tie_break_order"])
        s["leagues"][lid]={"league_id":lid,"sport_id":sport,"teams":teams,"fixtures":fx,"points":pts,"qualification":q,"tie_break_order":order,"lots_seed":d.get("lots_seed",s["seed"])}
        for f in fx:s["matches"][f["match_id"]]=new_match(f["match_id"],sport,f["home"],f["away"],lid)
        return {"league_id":lid,"status":"created","team_count":len(teams),"fixture_count":len(fx)}
    return mutate(change)
