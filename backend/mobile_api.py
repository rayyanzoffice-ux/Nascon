from fastapi import APIRouter, Request
from .app import body
from .core import bad, fail, read, mutate
from .rbac import tokens
from .scoring import projection

router=APIRouter(prefix="/mobile/v1")
ROLES={"admin":"super_admin","organizer":"league_organizer","manager":"club_manager","player":"player","viewer":"viewer"}

@router.post("/login")
async def login(req:Request):
    d=await body(req)
    email=d.get("email","");pwd=d.get("password")
    prefix=email.split("@")[0] if isinstance(email,str) else ""
    if email!=prefix+"@nascon.test" or prefix not in ROLES or pwd!="Nascon@26":fail(401,"UNAUTHENTICATED")
    return {"token":tokens()[ROLES[prefix]],"role":ROLES[prefix],"email":email,"tenant_id":"tenant-alpha","display_name":prefix.capitalize()}

@router.get("/fixtures")
def fixtures():
    def take(s):
        rows=[]
        for m in s["matches"].values():
            p=projection(m,s["sports"])
            rows.append({"match_id":m["match_id"],"sport_id":m["sport_id"],"league_id":m["league_id"],"home":m["home"],"away":m["away"],"status":p["status"],"home_score":p["home"]["score"],"away_score":p["away"]["score"],"start_time":"2026-10-17T12:00:00Z"})
        return rows
    return read(take)

@router.get("/leagues")
def leagues():
    return read(lambda s:[{"league_id":l["league_id"],"sport_id":l["sport_id"],"teams":l["teams"]} for l in s["leagues"].values()])

@router.get("/clubs")
def clubs():
    return read(lambda s:[{"club_id":c,"tenant_id":t,"name":c.replace("-"," ").title(),"home_venue":"FAST Islamabad Stadium","staff":[{"role":"Manager","name":"Club Staff"}],"roster":[{"player_id":p["player_id"],"name":p["name"],"position":p["position"]} for p in s["players"].values() if p["squad_id"] in [sid for scenario in s["rosters"].values() for sid, sq in scenario["squads"].items() if sq["club_id"]==c]]} for c,t in s["clubs"].items()])

@router.get("/catalogue")
def catalogue():
    def take(s):
        return [{"product_id":"prod-jersey-001","name":"Official League Jersey","category":"apparel","tenant_id":"tenant-alpha","variants":[{"variant_id":k,"size":k.rsplit("-",1)[-1],"stock":v["stock"],"price_minor":v["price_minor"]} for k,v in s["inventory"].items()]}]
    return read(take)

@router.get("/me")
def me():
    return {"roles":list(ROLES.values()),"tenant_id":"tenant-alpha"}

@router.post("/demo-setup")
def demo_setup():
    from .scoring import new_match, event_apply
    from .roster import setup_apply
    def seed(s):
        if "demo-league" not in s["leagues"]:
            teams=["demo-team-a","demo-team-b","demo-team-c"]
            fx=[{"match_id":"demo-match-1","home":teams[0],"away":teams[1]},{"match_id":"demo-match-2","home":teams[1],"away":teams[2]}]
            s["leagues"]["demo-league"]={"league_id":"demo-league","sport_id":"football","teams":teams,"fixtures":fx,"points":{"win":3,"draw":1,"loss":0},"qualification":{"spots":2},"tie_break_order":s["sports"]["football"]["tie_break_order"],"lots_seed":42}
            for f in fx:s["matches"][f["match_id"]]=new_match(f["match_id"],"football",f["home"],f["away"],"demo-league")
            event_apply(s,{"event_id":"demo-start-1","match_id":"demo-match-1","type":"match_start","payload":{}})
        if "demo-roster" not in s["rosters"]:
            setup_apply(s,{"league":{"league_id":"demo-roster","tenant_id":"tenant-alpha","sport_id":"football","transfer_window":{"open":"2026-10-01","close":"2026-10-31"},"max_squad_size":8,"required_positions":{}},
               "squads":[{"squad_id":"sq-demo-alpha","club_id":"club-alpha-1","tenant_id":"tenant-alpha","name":"Alpha Squad"},{"squad_id":"sq-demo-beta","club_id":"club-alpha-2","tenant_id":"tenant-alpha","name":"Beta Squad"}],
               "players":[{"player_id":"player-demo-1","name":"Ayaan Khan","position":"midfielder","squad_id":"sq-demo-alpha","role":"starter"},{"player_id":"player-demo-2","name":"Zain Ahmed","position":"defender","squad_id":"sq-demo-alpha","role":"captain"}],"matches_in_progress":[]})
        return {"status":"ready","league_id":"demo-league","match_id":"demo-match-1"}
    return mutate(seed)
