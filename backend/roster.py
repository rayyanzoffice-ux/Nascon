from datetime import date,datetime,timedelta,timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .core import bad, fail, identifier, positive_int, integer, mutate, read, utcnow
from .app import body
router=APIRouter()
ROLES={"captain","vice_captain","starter","substitute"}

def parsed_date(s):
    if not isinstance(s,str):return None
    try:
        x=date.fromisoformat(s)
        if x.isoformat()!=s:return None
        return x
    except ValueError:return None

def setup_apply(state,d):
    lg=d.get("league");squads=d.get("squads");players=d.get("players")
    if not isinstance(lg,dict) or not isinstance(squads,list) or not isinstance(players,list):bad("league","squads","players")
    lid=lg.get("league_id");tenant=lg.get("tenant_id");sport=lg.get("sport_id");window=lg.get("transfer_window")
    if not identifier(lid) or not identifier(tenant) or not identifier(sport) or not isinstance(window,dict) or parsed_date(window.get("open")) is None or parsed_date(window.get("close")) is None or window["open"]>window["close"]:bad("league")
    if sport not in state["sports"]:fail(404,"SPORT_NOT_FOUND")
    if tenant not in state["tenants"]:bad("league")
    conf=state["sports"][sport]["roster"]
    max_size=lg.get("max_squad_size",conf["max_squad_size"]);required=lg.get("required_positions",conf["required_positions"])
    if not positive_int(max_size) or not isinstance(required,dict) or any(not isinstance(k,str) or not integer(v) or v<0 for k,v in required.items()):bad("league")
    sq={}
    for x in squads:
        if not isinstance(x,dict) or not identifier(x.get("squad_id")) or not identifier(x.get("club_id")) or not identifier(x.get("tenant_id")) or not isinstance(x.get("name"),str):bad("squads")
        if x["squad_id"] in sq:bad("squads")
        sq[x["squad_id"]]=x
    # Foreign-tenant squads are permitted in setup so transfer can return the
    # contract's CROSS_TENANT_TRANSFER error at the prescribed rule step.
    counts={sid:0 for sid in sq}
    seen_players=set()
    for p in players:
        if not isinstance(p,dict) or not identifier(p.get("player_id")) or not isinstance(p.get("name"),str) or not isinstance(p.get("position"),str) or p.get("squad_id") not in sq or p.get("role") not in ROLES:bad("players")
        if p["player_id"] in state["players"] and state["players"][p["player_id"]]["league_id"]!=lid:bad("players")
        if p["player_id"] in seen_players:bad("players")
        seen_players.add(p["player_id"])
        counts[p["squad_id"]]+=1
    live=d.get("matches_in_progress",[])
    if not isinstance(live,list) or any(not isinstance(m,dict) or not identifier(m.get("match_id")) or m.get("home_squad_id") not in sq or m.get("away_squad_id") not in sq or m["home_squad_id"]==m["away_squad_id"] for m in live):bad("matches_in_progress")
    if any(n>max_size for n in counts.values()):bad("players")
    for pid,v in list(state["players"].items()):
        if v["league_id"]==lid:state["players"].pop(pid)
    state["rosters"][lid]={"league":lg,"squads":sq,"max_size":max_size,"required_positions":required,"matches_in_progress":live}
    for p in players:
        state["players"][p["player_id"]]={"player_id":p["player_id"],"league_id":lid,"name":p["name"],"position":p["position"],"squad_id":p["squad_id"],"role":p["role"],"parent_squad_id":None,"registration_type":"initial","start_date":window["open"],"loan_end_date":None,"history":[],"initial_squad_id":p["squad_id"]}
    state["transfers"]={k:v for k,v in state["transfers"].items() if v["request"]["league_id"]!=lid}
    return {"league_id":lid,"status":"configured","squad_counts":counts}

def registration(player):
    if player["squad_id"] is None:return None
    return {k:player[k] for k in ("player_id","league_id","squad_id","parent_squad_id","registration_type","start_date","loan_end_date","role")}

def audit(player,action,source,dest,when,who,why,effective,state):
    entry={"audit_id":"au-%04d"%(len(player["history"])+1),"action":action,"player_id":player["player_id"],"league_id":player["league_id"],
           "from_squad_id":source,"to_squad_id":dest,"effective_date":effective,"state":state,"who":who,"when":when,"why":why}
    player["history"].append(entry)
    return entry

def maybe_return(player,as_of):
    end=player.get("loan_end_date")
    if player.get("registration_type")!="loan" or not end or as_of<=end:return
    source=player["squad_id"];dest=player["parent_squad_id"]
    d=(date.fromisoformat(end)+timedelta(days=1)).isoformat()
    player.update({"squad_id":dest,"parent_squad_id":None,"registration_type":"loan_return","start_date":d,"loan_end_date":None,"role":"substitute"})
    audit(player,"loan_return",source,dest,utcnow(),"system","Automatic loan return",d,"active")

def transfer_apply(state,d):
    needed=("request_id","league_id","player_id","type","from_squad_id","effective_date","reason","requested_by")
    if any(k not in d for k in needed) or any(not identifier(d.get(k)) for k in ("request_id","league_id","player_id","from_squad_id")) or d.get("type") not in ("transfer","loan","release") or parsed_date(d.get("effective_date")) is None or not isinstance(d.get("reason"),str) or not isinstance(d.get("requested_by"),str):bad(*needed)
    kind=d["type"];to=d.get("to_squad_id");end=d.get("loan_end_date")
    if kind!="release" and not identifier(to):bad("to_squad_id")
    if kind=="release" and to is not None:bad("to_squad_id")
    if kind=="loan" and (parsed_date(end) is None or end<=d["effective_date"]):bad("loan_end_date")
    if kind!="loan" and end is not None:bad("loan_end_date")
    rid=d["request_id"];prior=state["transfers"].get(rid)
    if prior is not None:
        if prior["request"]==d:return 200,prior["response"]
        fail(409,"NOT_IN_SQUAD")
    lid=d["league_id"];r=state["rosters"].get(lid)
    if r is None:fail(404,"LEAGUE_NOT_FOUND")
    p=state["players"].get(d["player_id"])
    if p is None or p["league_id"]!=lid:fail(404,"PLAYER_NOT_FOUND")
    sq=r["squads"];source=d["from_squad_id"]
    if source not in sq or (to is not None and to not in sq):fail(404,"SQUAD_NOT_FOUND")
    tenant=r["league"]["tenant_id"]
    if sq[source]["tenant_id"]!=tenant or (to is not None and sq[to]["tenant_id"]!=tenant):fail(409,"CROSS_TENANT_TRANSFER")
    maybe_return(p,d["effective_date"])
    if p["squad_id"]!=source:fail(409,"NOT_IN_SQUAD")
    window=r["league"]["transfer_window"]
    if kind!="release" and not window["open"]<=d["effective_date"]<=window["close"]:fail(409,"TRANSFER_WINDOW_CLOSED")
    if p["registration_type"]=="loan":fail(409,"PLAYER_ON_LOAN")
    if kind!="release":
        dest_count=sum(x["squad_id"]==to and x["league_id"]==lid for x in state["players"].values())
        if dest_count+1>r["max_size"]:fail(409,"SQUAD_FULL")
    required=r["required_positions"].get(p["position"],0)
    count=sum(x["league_id"]==lid and x["squad_id"]==source and x["position"]==p["position"] for x in state["players"].values())
    if count-1<required:fail(409,"MIN_POSITION_VIOLATION")
    blocking=next((m["match_id"] for m in r.get("matches_in_progress",[]) if source in (m.get("home_squad_id"),m.get("away_squad_id"))),None)
    transition="deferred_until_match_end" if blocking else "active"
    p.update({"squad_id":to,"parent_squad_id":source if kind=="loan" else None,"registration_type":kind,"start_date":d["effective_date"],"loan_end_date":end if kind=="loan" else None,"role":"substitute"})
    entry=audit(p,kind,source,to,utcnow(),d["requested_by"],d["reason"],d["effective_date"],transition)
    response={"request_id":rid,"status":"accepted","state":transition,"blocking_match_id":blocking,"registration":registration(p),"audit_entry":entry}
    state["transfers"][rid]={"request":d,"response":response}
    return 201,response

@router.post("/audit/v1/roster/setup",status_code=201)
async def setup(req:Request):
    d=await body(req)
    return mutate(lambda s:setup_apply(s,d))

@router.post("/audit/v1/roster/transfer")
async def transfer(req:Request):
    d=await body(req)
    code,result=mutate(lambda s:transfer_apply(s,d))
    return JSONResponse(status_code=code,content=result)

@router.get("/audit/v1/roster/history/{player_id}")
def history(player_id:str,as_of:str=None):
    when=as_of or date.today().isoformat()
    if parsed_date(when) is None:bad("as_of")
    def lookup(s):
        p=s["players"].get(player_id)
        if p is None:fail(404,"PLAYER_NOT_FOUND")
        maybe_return(p,when)
        current=p["initial_squad_id"]
        parent=None
        for entry in p["history"]:
            if entry["effective_date"]<=when:
                current=entry["to_squad_id"]
                parent=entry["from_squad_id"] if entry["action"]=="loan" else None
        return {"player_id":player_id,"as_of":when,"league_id":p["league_id"],"current_squad_id":current,"parent_squad_id":parent,"history":p["history"]}
    return mutate(lookup)

