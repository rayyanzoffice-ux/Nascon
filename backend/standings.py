import hashlib
from collections import defaultdict
from fastapi import APIRouter
from .core import read, fail
from .scoring import projection

router=APIRouter()

def nrr(team, results, sport):
    bpo=sport["periods"]["balls_per_over"]
    full=sport["periods"]["overs_per_innings"]*sport["periods"]["innings_per_team"]
    maxw=sport["periods"]["wickets_per_innings"]*sport["periods"]["innings_per_team"]
    runs_for=runs_against=balls_for=balls_against=0
    for match in results:
        a,b=match["home"],match["away"]
        if team not in (a["team_id"],b["team_id"]):continue
        own,opp=(a,b) if a["team_id"]==team else (b,a)
        runs_for+=own["score"];runs_against+=opp["score"]
        balls_for+=full*bpo if own["wickets"]>=maxw else own["balls"]
        balls_against+=full*bpo if opp["wickets"]>=maxw else opp["balls"]
    return round((runs_for*bpo/balls_for if balls_for else 0)-(runs_against*bpo/balls_against if balls_against else 0),3)

def build(state,league_id):
    lg=state["leagues"].get(league_id)
    if lg is None:fail(404,"LEAGUE_NOT_FOUND")
    teams=lg["teams"];sport=state["sports"][lg["sport_id"]];points=lg["points"];spots=lg["qualification"]["spots"]
    matches=[projection(state["matches"][f["match_id"]],state["sports"]) for f in lg["fixtures"]]
    played=[m for m in matches if m["status"]=="completed" and m["outcome"]!="undecided"]
    remaining={t:0 for t in teams}
    for m in matches:
        if m not in played:
            remaining[m["home"]["team_id"]]+=1;remaining[m["away"]["team_id"]]+=1
    rows={t:{"rank":0,"team_id":t,"played":0,"won":0,"drawn":0,"lost":0,"scored":0,"conceded":0,"diff":0,"points":0,"fair_play":0,"status":"still_possible","resolved_by":None} for t in teams}
    h2h={a:{b:{"played":0,"points":0,"scored":0,"conceded":0} for b in teams if b!=a} for a in teams}
    def result_points(m,t):
        winner=m["winner_team_id"]
        return points["draw"] if winner is None else points["win"] if winner==t else points["loss"]
    for m in played:
        h,a=m["home"],m["away"]
        for own,other in ((h,a),(a,h)):
            t=own["team_id"];b=other["team_id"];r=rows[t]
            r["played"]+=1
            if m["winner_team_id"] is None:r["drawn"]+=1
            elif m["winner_team_id"]==t:r["won"]+=1
            else:r["lost"]+=1
            r["points"]+=result_points(m,t)
            r["scored"]+=own["score"];r["conceded"]+=other["score"]
            r["fair_play"]+=own["fair_play"]
            hh=h2h[t][b]
            hh["played"]+=1;hh["points"]+=result_points(m,t)
            hh["scored"]+=own["score"];hh["conceded"]+=other["score"]
    for t,r in rows.items():
        r["diff"]=nrr(t,played,sport) if sport["scoring_model"]=="innings" else r["scored"]-r["conceded"]
        upper=sum(1 for other in teams if other!=t and rows[other]["points"]+points["win"]*remaining[other]>=r["points"])
        lower=sum(1 for other in teams if other!=t and rows[other]["points"]>r["points"]+points["win"]*remaining[t])
        r["status"]="clinched" if upper<spots else "eliminated" if lower>=spots else "still_possible"
    criteria=lg["tie_break_order"]
    def mini(group,criterion):
        subset=set(group)
        m=[x for x in played if x["home"]["team_id"] in subset and x["away"]["team_id"] in subset]
        if criterion=="h2h_points":
            return {t:sum(result_points(x,t) for x in m if t in (x["home"]["team_id"],x["away"]["team_id"])) for t in group}
        if criterion=="h2h_diff":
            if sport["scoring_model"]=="innings":return {t:nrr(t,m,sport) for t in group}
            return {t:sum((x["home"]["score"]-x["away"]["score"])*(1 if x["home"]["team_id"]==t else -1) for x in m if t in (x["home"]["team_id"],x["away"]["team_id"])) for t in group}
        if criterion=="overall_diff":return {t:rows[t]["diff"] for t in group}
        if criterion=="scored":return {t:rows[t]["scored"] for t in group}
        if criterion=="fair_play":return {t:rows[t]["fair_play"] for t in group}
        return {t:hashlib.sha256((str(lg["lots_seed"])+"|"+league_id+"|"+t).encode()).hexdigest() for t in group}
    def resolve(group,depth=0):
        if len(group)<=1:return list(group),{}
        for criterion in criteria:
            key=mini(group,criterion)
            unique=sorted(set(key.values()),reverse=(criterion!="draw_lots"))
            if len(unique)==1:continue
            order=[];boundaries={}
            for val in unique:
                subset=[t for t in group if key[t]==val]
                if len(subset)>1:
                    inside,inside_bounds=resolve(subset,depth+1)
                else:inside,inside_bounds=subset,{}
                for i,c in inside_bounds.items():boundaries[len(order)+i]=c
                order.extend(inside)
                if val!=unique[-1]:boundaries[len(order)-1]=criterion
            return order,boundaries
        # All criteria including SHA draw_lots are expected to resolve unique ids.
        return sorted(group),{}
    ordered=[];boundary={}
    for score in sorted({r["points"] for r in rows.values()},reverse=True):
        group=[t for t in teams if rows[t]["points"]==score]
        sub,b=resolve(group)
        for i,c in b.items():boundary[len(ordered)+i]=c
        ordered.extend(sub)
    output=[]
    for i,t in enumerate(ordered):
        r=rows[t];r["rank"]=i+1;r["resolved_by"]=boundary.get(i)
        output.append(r)
    return {"league_id":league_id,"sport_id":lg["sport_id"],"qualification_spots":spots,"table":output,"h2h":h2h}

@router.get("/audit/v1/standings/{league_id}")
def standings(league_id:str):
    return read(lambda state:build(state,league_id))
