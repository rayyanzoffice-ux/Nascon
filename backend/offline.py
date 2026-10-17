import copy
from fastapi import APIRouter, Request
from .core import APIError, bad, identifier, integer, mutate
from .app import body
from .scoring import event_apply
from .roster import transfer_apply

router=APIRouter()

def current_version(s,typ,payload):
    if typ=="score_event":
        match=s["matches"].get(payload.get("match_id"))
        if match is None:raise APIError(404,"MATCH_NOT_FOUND")
        return len(match["events"])
    lg=payload.get("league_id");player=s["players"].get(payload.get("player_id"))
    if lg not in s["rosters"]:raise APIError(404,"LEAGUE_NOT_FOUND")
    if player is None:raise APIError(404,"PLAYER_NOT_FOUND")
    return len(player["history"])

def sync_apply(state,envelope):
    device=envelope.get("device_id");actions=envelope.get("actions")
    if not identifier(device) or not isinstance(actions,list) or not 1<=len(actions)<=100:bad("device_id","actions")
    for a in actions:
        if not isinstance(a,dict) or not identifier(a.get("action_id")) or a.get("type") not in ("score_event","roster_transfer") or not isinstance(a.get("queued_at"),str) or not integer(a.get("base_version")) or a["base_version"]<0 or not isinstance(a.get("payload"),dict):bad("actions")
    ordered=sorted(enumerate(actions),key=lambda pair:(pair[1]["queued_at"],pair[0]))
    answers=[None]*len(actions);counts={"applied":0,"rejected":0,"duplicate":0}
    for processed,(i,action) in enumerate(ordered,1):
        ident=device+"|"+action["action_id"];typ=action["type"];payload=action["payload"]
        version=0;signature=None
        status="rejected";resolution="server_wins";err=None
        try:
            version=current_version(state,typ,payload)
            original=state["offline"].get(ident)
            eid=payload.get("event_id")
            existing=state["events_by_id"].get(eid) if typ=="score_event" else None
            duplicate=original is not None or (existing is not None and existing["request"]==payload)
            if duplicate:
                status="duplicate";resolution="skipped_duplicate"
            elif action["base_version"]>version:err="INVALID_BASE_VERSION"
            else:
                temp=copy.deepcopy(state)
                if typ=="score_event":code,response=event_apply(temp,payload)
                else:code,response=transfer_apply(temp,payload)
                if code==200:
                    status="duplicate";resolution="skipped_duplicate"
                else:
                    state.clear();state.update(temp)
                    status="applied";resolution="appended" if action["base_version"]==version else "rebased_append"
                    signature=response.get("signature") if typ=="score_event" else None
                    version=current_version(state,typ,payload)
            state["offline"][ident]={"type":typ,"action_id":action["action_id"]}
        except APIError as exc:
            err=exc.code
        counts[status]+=1
        answers[i]={"action_id":action["action_id"],"status":status,"resolution":resolution,"error_code":err,"processed_order":processed,"server_version":version,"signature":signature}
    return {"device_id":device,"results":answers,"summary":counts}

@router.post("/audit/v1/offline-sync")
async def offline(req:Request):
    data=await body(req)
    return mutate(lambda state:sync_apply(state,data))
