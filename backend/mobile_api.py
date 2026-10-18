import base64
from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse
from .app import body
from .core import bad, fail, read, mutate, identifier, utcnow
from .rbac import mobile_token, require_mobile_role
from .scoring import projection
from .store import checkout_apply, publish_order
from .offline import sync_apply

router=APIRouter(prefix="/mobile/v1")
ROLES={"admin":"super_admin","organizer":"league_organizer","manager":"club_manager","player":"player","viewer":"viewer"}

@router.post("/login")
async def login(req:Request):
    d=await body(req)
    email=d.get("email","");pwd=d.get("password")
    prefix=email.split("@")[0] if isinstance(email,str) else ""
    if email!=prefix+"@nascon.test" or prefix not in ROLES or pwd!="Nascon@26":fail(401,"UNAUTHENTICATED")
    return {"token":mobile_token(ROLES[prefix],email),"role":ROLES[prefix],"email":email,"tenant_id":"tenant-alpha","display_name":prefix.capitalize()}

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
def me(req:Request):
    account=require_mobile_role(req,*ROLES.values())
    return {"role":account["role"],"roles":[account["role"]],"email":account["sub"],"tenant_id":account["tenant_id"]}


@router.post("/checkout")
async def mobile_checkout(req:Request):
    account=require_mobile_role(req,"player")
    data=await body(req)
    if data.get("customer_id")!=account["sub"]:fail(403,"FORBIDDEN")
    code,result=mutate(lambda state:checkout_apply(state,data))
    if code==201:publish_order(result["order_id"])
    return JSONResponse(status_code=code,content=result)


@router.get("/receipts/{order_id}.pdf")
def mobile_receipt(req:Request,order_id:str):
    if not identifier(order_id):bad("order_id")
    account=require_mobile_role(req,"player")
    def find(state):
        order=state["orders"].get(order_id)
        if order is None or order["request"]["customer_id"]!=account["sub"]:fail(404,"ORDER_NOT_FOUND")
        return order["response"]["receipt"]["pdf_base64"]
    pdf=base64.b64decode(read(find))
    return Response(pdf,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{order_id}.pdf"'})


def cancel_match_apply(state, match_id, account, reason):
    if account["role"] not in ("league_organizer","super_admin"):fail(403,"FORBIDDEN")
    match=state["matches"].get(match_id)
    if match is None:fail(404,"MATCH_NOT_FOUND")
    league_id=match.get("league_id")
    if account["role"]!="super_admin" and state["rbac_leagues"].get(league_id)!=account["tenant_id"]:fail(403,"FORBIDDEN")
    status=projection(match,state["sports"])["status"]
    if status=="cancelled":return {"match_id":match_id,"status":"cancelled"}
    if status=="completed":fail(409,"ILLEGAL_TRANSITION")
    match["cancellation"]={"reason":reason,"by":account["sub"],"at":utcnow()}
    return {"match_id":match_id,"status":"cancelled"}


@router.post("/matches/{match_id}/cancel")
async def cancel_match(req:Request,match_id:str):
    account=require_mobile_role(req,"league_organizer","super_admin")
    if not identifier(match_id):bad("match_id")
    data=await body(req,True)
    reason=data.get("reason","Cancelled by organizer")
    if not isinstance(reason,str) or not 1<=len(reason)<=200:bad("reason")
    return mutate(lambda state:cancel_match_apply(state,match_id,account,reason))


@router.delete("/matches/{match_id}")
def delete_match(req:Request,match_id:str):
    account=require_mobile_role(req,"league_organizer","super_admin")
    if not identifier(match_id):bad("match_id")
    return mutate(lambda state:cancel_match_apply(state,match_id,account,"Deleted by organizer"))


@router.post("/offline-sync")
async def mobile_offline_sync(req:Request):
    account=require_mobile_role(req,"league_organizer","club_manager","super_admin")
    data=await body(req)
    actions=data.get("actions")
    if isinstance(actions,list):
        allowed={"score_event"} if account["role"]=="league_organizer" else {"roster_transfer"} if account["role"]=="club_manager" else {"score_event","roster_transfer"}
        if any(isinstance(action,dict) and action.get("type") not in allowed for action in actions):fail(403,"FORBIDDEN")
    return mutate(lambda state:sync_apply(state,data))

@router.post("/demo-setup")
def demo_setup():
    from .scoring import new_match, event_apply
    from .roster import setup_apply
    def seed(s):
        if "demo-league" not in s["leagues"]:
            s["rbac_leagues"]["demo-league"]="tenant-alpha"
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
