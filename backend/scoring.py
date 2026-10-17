from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .core import bad, fail, identifier, integer, read, mutate, sign
from .app import body

router=APIRouter()

def new_match(mid,sport,home,away,league=None):
    return {"match_id":mid,"sport_id":sport,"league_id":league,"home":home,"away":away,"events":[]}

def projection(match,sports):
    sport=sports[match["sport_id"]]
    model=sport["scoring_model"]
    teams=[match["home"],match["away"]]
    values={t:{"team_id":t,"score":0,"wickets":0 if model=="innings" else None,"balls":0 if model=="innings" else None,"overs":"0.0" if model=="innings" else None,"fair_play":0} for t in teams}
    reversed_by={e["payload"]["compensates"]:e["event_id"] for e in match["events"] if e["type"]=="compensation"}
    status="upcoming";tie=None
    for e in match["events"]:
        kind=e["type"];p=e["payload"]
        if kind=="match_start":status="in_progress"
        if kind=="match_end":status="completed"
        if e["event_id"] in reversed_by or kind=="compensation":continue
        t=p.get("team_id")
        if kind=="score":
            tpl=sport["scoring_events"][p["event_type"]]
            v=values[t]
            if model=="event":v["score"]+=tpl["points"]
            elif model=="round":v["score"]+=tpl["rounds"]
            else:
                v["score"]+=tpl["runs"]
                v["wickets"]+=int(tpl["wicket"])
                v["balls"]+=int(tpl["legal_ball"])
        elif kind=="discipline":values[t]["fair_play"]+=p["points"]
        elif kind=="tiebreak_winner":tie=t
    if model=="innings":
        bpo=sport["periods"]["balls_per_over"]
        for v in values.values():v["overs"]=str(v["balls"]//bpo)+"."+str(v["balls"]%bpo)
    a,b=values[teams[0]],values[teams[1]]
    winner=teams[0] if a["score"]>b["score"] else teams[1] if b["score"]>a["score"] else tie
    outcome="pending"
    if status=="completed":
        outcome=("home_win" if winner==teams[0] else "away_win" if winner==teams[1] else "draw" if sport["draw_allowed"] else "undecided")
    events=[{"sequence":i,"event_id":e["event_id"],"type":e["type"],"payload":e["payload"],"signature":e["signature"],"compensated":e["event_id"] in reversed_by,"compensated_by":reversed_by.get(e["event_id"])} for i,e in enumerate(match["events"],1)]
    return {"match_id":match["match_id"],"sport_id":match["sport_id"],"league_id":match["league_id"],"status":status,"outcome":outcome,"winner_team_id":winner if status=="completed" else None,"tiebreak_winner_team_id":tie,"home":a,"away":b,"version":len(events),"events":events}

def validate_event_request(data):
    if not isinstance(data,dict):bad("body")
    eid=data.get("event_id");mid=data.get("match_id");kind=data.get("type");payload=data.get("payload")
    if not identifier(eid) or not identifier(mid) or not isinstance(payload,dict):bad("event_id","match_id","payload")
    fields={"match_init":["sport_id","home_team_id","away_team_id"],"match_start":[],"score":["team_id","event_type"],"discipline":["team_id","points"],"tiebreak_winner":["team_id"],"match_end":[],"compensation":["compensates","reason"]}
    if not isinstance(kind,str) or kind not in fields or any(k not in payload for k in fields[kind]):bad("type","payload")
    # Validate the complete event schema before looking up any referenced ID.
    if kind=="match_init":
        if (any(not identifier(payload[k]) for k in fields[kind])
                or payload["home_team_id"]==payload["away_team_id"]
                or ("league_id" in payload and not identifier(payload["league_id"]))):bad("payload")
    elif kind=="score":
        if not identifier(payload["team_id"]) or not isinstance(payload["event_type"],str):bad("payload")
    elif kind=="discipline":
        if not identifier(payload["team_id"]) or not integer(payload["points"]):bad("payload")
    elif kind=="tiebreak_winner":
        if not identifier(payload["team_id"]):bad("payload")
    elif kind=="compensation":
        if not identifier(payload["compensates"]) or not isinstance(payload["reason"],str):bad("payload")
    return eid,mid,kind,payload

def event_apply(state,data):
    eid,mid,kind,payload=validate_event_request(data)
    old=state["events_by_id"].get(eid)
    if old is not None:
        if old["request"]==data:return 200,old["response"]
        fail(409,"DUPLICATE_EVENT_ID")
    m=state["matches"].get(mid)
    if kind=="match_init":
        if payload["sport_id"] not in state["sports"]:fail(404,"SPORT_NOT_FOUND")
        if m:fail(409,"MATCH_EXISTS")
        m=new_match(mid,payload["sport_id"],payload["home_team_id"],payload["away_team_id"],payload.get("league_id"))
        state["matches"][mid]=m
    elif m is None:fail(404,"MATCH_NOT_FOUND")
    proj=projection(m,state["sports"]);status=proj["status"]
    if kind=="match_start" and status!="upcoming":fail(409,"ILLEGAL_TRANSITION")
    if kind in ("score","discipline","tiebreak_winner") and status!="in_progress":fail(409,"MATCH_NOT_IN_PROGRESS")
    if kind in ("score","discipline","tiebreak_winner"):
        if payload.get("team_id") not in (m["home"],m["away"]):bad("payload")
    if kind=="score":
        sport=state["sports"][m["sport_id"]]
        if payload.get("event_type") not in sport["scoring_events"]:fail(400,"UNKNOWN_EVENT_TYPE")
        v=proj["home"] if payload["team_id"]==m["home"] else proj["away"]
        if sport["scoring_model"]=="innings":
            conf=sport["periods"]
            if v["balls"]>=conf["innings_per_team"]*conf["overs_per_innings"]*conf["balls_per_over"] or v["wickets"]>=conf["innings_per_team"]*conf["wickets_per_innings"]:fail(409,"INNINGS_COMPLETE")
        if sport["scoring_model"]=="round":
            threshold=(sport["periods"]["best_of"]+1)//2
            if proj["home"]["score"]>=threshold or proj["away"]["score"]>=threshold:fail(409,"SERIES_ALREADY_DECIDED")
    if kind=="match_end":
        if status!="in_progress":fail(409,"ILLEGAL_TRANSITION")
        if proj["home"]["score"]==proj["away"]["score"] and not state["sports"][m["sport_id"]]["draw_allowed"] and not proj["tiebreak_winner_team_id"]:fail(409,"TIE_NOT_ALLOWED")
    if kind=="tiebreak_winner" and payload["team_id"] not in (m["home"],m["away"]):bad("payload")
    if kind=="compensation":
        target=state["events_by_id"].get(payload.get("compensates"))
        if target is None:fail(404,"EVENT_NOT_FOUND")
        if target["request"]["match_id"]!=mid or target["request"]["type"] not in ("score","discipline","tiebreak_winner") or any(e["type"]=="compensation" and e["payload"]["compensates"]==payload["compensates"] for e in m["events"]):fail(409,"INVALID_COMPENSATION")
    seq=len(m["events"])+1
    signature=sign(eid,payload)
    result={"event_id":eid,"match_id":mid,"type":kind,"sequence":seq,"match_version":seq,"signature":signature}
    m["events"].append({"event_id":eid,"type":kind,"payload":payload,"signature":signature})
    state["events_by_id"][eid]={"request":data,"response":result}
    return 201,result

@router.post("/audit/v1/events")
async def events(req:Request):
    d=await body(req)
    status,result=mutate(lambda s:event_apply(s,d))
    return JSONResponse(status_code=status,content=result)

@router.get("/audit/v1/score/{match_id}")
def score(match_id:str):
    def get(s):
        m=s["matches"].get(match_id)
        if m is None:fail(404,"MATCH_NOT_FOUND")
        return projection(m,s["sports"])
    return read(get)

