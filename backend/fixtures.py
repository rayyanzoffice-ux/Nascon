import math
from collections import defaultdict
from functools import lru_cache
from fastapi import APIRouter, Request
from .core import bad, fail, identifier, positive_int, integer
from .app import body

router = APIRouter()

def seed_order(size):
    if size==2: return [1,2]
    prev=seed_order(size//2)
    return [v for x in prev for v in (x,size+1-x)]

def round_robin(teams, p):
    n=len(teams)
    legs=p.get("legs",1)
    withdrawals=p.get("withdrawals",[])
    policy=p.get("withdrawal_policy","forfeit_remaining")
    if legs not in (1,2) or not isinstance(withdrawals,list) or policy not in ("void_all","forfeit_remaining"): bad("params")
    size=n+(n%2)
    rounds_per_leg=size-1
    total_rounds=rounds_per_leg*legs
    wd={}
    for w in withdrawals:
        if not isinstance(w,dict) or w.get("team_id") not in teams or not integer(w.get("after_round")) or not 0<=w["after_round"]<=total_rounds: bad("withdrawals")
        wd[w["team_id"]]=w["after_round"]
    rotating=teams.copy()+([None] if n%2 else [])
    output=[]
    counts={"total":0,"scheduled":0,"forfeit":0,"voided":0}
    for leg in range(1,legs+1):
        # Second leg repeats first leg with reversed homes, ensuring unique ordered pairs.
        cur=rotating[:]
        for r in range(rounds_per_leg):
            global_r=(leg-1)*rounds_per_leg+r+1
            matches=[];byes=[]
            for i in range(size//2):
                home,away=cur[i],cur[size-1-i]
                if i==0 and r%2: home,away=away,home
                if leg==2:home,away=away,home
                if home is None or away is None:
                    byes.append(home if away is None else away);continue
                withdrawn=[t for t in (home,away) if t in wd and (policy=="void_all" or global_r>wd[t])]
                status="scheduled";winner=None
                if withdrawn:
                    if policy=="void_all" or len(withdrawn)==2: status="voided"
                    else: status="forfeit";winner=away if withdrawn[0]==home else home
                mid="RR-L%d-R%d-M%d"%(leg,global_r,len(matches)+1)
                matches.append({"match_id":mid,"leg":leg,"home":home,"away":away,"status":status,"awarded_to":winner})
                counts[status]+=1;counts["total"]+=1
            output.append({"round":global_r,"matches":matches,"byes":byes})
            cur=[cur[0],cur[-1]]+cur[1:-1]
    return {"format":"round_robin","legs":legs,"team_count":n,"round_count":total_rounds,"rounds":output,"summary":counts}

def swiss(teams,p):
    n=len(teams)
    total=p.get("total_rounds",math.ceil(math.log2(n)))
    rnd=p.get("round",1)
    history=p.get("history",[])
    if not integer(total) or not 1<=total<=n-1 or not integer(rnd) or not 1<=rnd<=total or not isinstance(history,list) or len(history)!=rnd-1:bad("params")
    scores={t:0.0 for t in teams};opponents={t:[] for t in teams};byes=set()
    for expected,h in enumerate(history,1):
        if not isinstance(h,dict) or h.get("round")!=expected or not isinstance(h.get("matches"),list):bad("history")
        used=set()
        bye=h.get("bye")
        if (n%2==1 and bye not in teams) or (n%2==0 and bye is not None):bad("history")
        if bye is not None: used.add(bye);byes.add(bye);scores[bye]+=1.0
        for m in h["matches"]:
            if not isinstance(m,dict) or m.get("home") not in teams or m.get("away") not in teams or m["home"]==m["away"] or m["home"] in used or m["away"] in used or m.get("result") not in ("home","away","draw"):bad("history")
            a,b=m["home"],m["away"];used.update((a,b));opponents[a].append(b);opponents[b].append(a)
            if m["result"]=="draw": scores[a]+=.5;scores[b]+=.5
            else:scores[m[m["result"]]]+=1.0
        if len(used)!=n:bad("history")
    buchholz={t:sum(scores[x] for x in opponents[t]) for t in teams}
    ranked=sorted(teams,key=lambda t:(-scores[t],-buchholz[t],teams.index(t)))
    standings=[{"rank":i+1,"team_id":t,"score":scores[t],"buchholz":buchholz[t]} for i,t in enumerate(ranked)]
    if rnd==1:
        m=n//2
        bye=teams[-1] if n%2 else None
        pairs=[(teams[i],teams[i+m]) for i in range(m)]
    else:
        bye_candidates=[None] if n%2==0 else sorted((t for t in teams if t not in byes),key=lambda t:(scores[t],-teams.index(t)))
        best=None;bye=None
        for candidate in bye_candidates:
            pool=[t for t in ranked if t!=candidate]
            seen={t:set(opponents[t]) for t in pool}
            # Exact minimum total score-group distance, followed by deterministic seed preference.
            # Memoization is fast for regular Swiss groups; rematch constraints prune recursion.
            @lru_cache(None)
            def solve(rest):
                if not rest:return (0,())
                first=rest[0]; opt=None
                # With scores in descending order, adjacent unconstrained pairs
                # give a lower bound on the cost of every valid matching.
                lower_bound=sum(abs(scores[rest[i]]-scores[rest[i+1]]) for i in range(0,len(rest),2))
                candidates=sorted(range(1,len(rest)),key=lambda j:(abs(scores[first]-scores[rest[j]]),j))
                for j in candidates:
                    other=rest[j]
                    if other in seen[first]:continue
                    remaining=rest[1:j]+rest[j+1:]
                    bound=abs(scores[first]-scores[other])+sum(abs(scores[remaining[i]]-scores[remaining[i+1]]) for i in range(0,len(remaining),2))
                    if opt is not None and bound>=opt[0]:continue
                    result=solve(remaining)
                    if result is None:continue
                    value=abs(scores[first]-scores[other])+result[0]
                    proposal=(value,((first,other),)+result[1])
                    if opt is None or proposal[0]<opt[0]:opt=proposal
                    if opt[0]==lower_bound:break
                return opt
            result=solve(tuple(pool))
            if result is not None:best=result[1];bye=candidate;break
        if best is None:fail(409,"NO_VALID_PAIRING",round=rnd)
        pairs=best
    return {"format":"swiss","round":rnd,"total_rounds":total,"pairings":[{"match_id":"SW-R%d-M%d"%(rnd,i+1),"home":a,"away":b} for i,(a,b) in enumerate(pairs)],"bye":bye,"standings":standings}

def make_match(mid, bracket, rnd, idx, home=None, away=None, hs=None,az=None,bye=False, conditional=False):
    x={"match_id":mid,"bracket":bracket,"round":rnd,"index":idx,
       "home":home,"away":away,"home_seed":hs,"away_seed":az,"bye":bye,
       "winner":None,"loser":None,"winner_to":None,"loser_to":None}
    if conditional:x.update({"conditional":True,"required":None})
    return x

def eliminate(teams,p,double=False):
    if double and type(p.get("bracket_reset",False)) is not bool:bad("bracket_reset")
    if not double and type(p.get("third_place_match",False)) is not bool:bad("third_place_match")
    size=1<<(len(teams)-1).bit_length()
    k=int(math.log2(size));order=seed_order(size)
    results=p.get("results",[])
    if not isinstance(results,list):bad("results")
    allm={}; wb=[]; lb=[]
    def add(mid,bracket,r,i,home=None,away=None,hs=None,az=None,bye=False,conditional=False):
        obj=make_match(mid,bracket,r,i,home,away,hs,az,bye,conditional)
        allm[mid]=obj
        return obj
    prefix="WR" if double else "R"
    for r in range(1,k+1):
        matches=[]
        for i in range(1,size//(2**r)+1):
            mid="%s%dM%d"%(prefix,r,i)
            if r==1:
                s1,s2=order[2*i-2],order[2*i-1]
                t1=teams[s1-1] if s1<=len(teams) else None
                t2=teams[s2-1] if s2<=len(teams) else None
                if t1 is None:t1,t2=t2,t1;s1,s2=s2,s1
                matches.append(add(mid,"winners" if double else "main",r,i,t1,t2,s1 if t1 else None,s2 if t2 else None,t2 is None))
            else:matches.append(add(mid,"winners" if double else "main",r,i))
        wb.append({"round":r,"matches":matches})
    gf=[]
    if double:
        for r in range(1,2*(k-1)+1):
            j=(r+1)//2
            count=size//(2**(j+1))
            matches=[add("LR%dM%d"%(r,i),"losers",r,i) for i in range(1,count+1)]
            lb.append({"round":r,"matches":matches})
        gf=[add("GF1","grand_final",1,1)]
        if p.get("bracket_reset",False):gf.append(add("GF2","grand_final",2,1,conditional=True))
    for r,rd in enumerate(wb,1):
        for i,m in enumerate(rd["matches"],1):
            if r<k:
                m["winner_to"]={"match_id":"%s%dM%d"%(prefix,r+1,(i+1)//2),"slot":"home" if i%2 else "away"}
            elif double:m["winner_to"]={"match_id":"GF1","slot":"home"}
            if double:
                if r==1:mid="LR1M%d"%((i+1)//2);slot="home" if i%2 else "away"
                else:mid="LR%dM%d"%(2*r-2,i);slot="away"
                m["loser_to"]={"match_id":mid,"slot":slot}
    if double:
        for r,rd in enumerate(lb,1):
            for i,m in enumerate(rd["matches"],1):
                if r==len(lb):m["winner_to"]={"match_id":"GF1","slot":"away"}
                elif r%2==1:m["winner_to"]={"match_id":"LR%dM%d"%(r+1,i),"slot":"home"}
                else:m["winner_to"]={"match_id":"LR%dM%d"%(r+1,(i+1)//2),"slot":"home" if i%2 else "away"}
        if len(gf)==2:
            gf[0]["winner_to"]={"match_id":"GF2","slot":"home"}
            gf[0]["loser_to"]={"match_id":"GF2","slot":"away"}
    if not double and p.get("third_place_match",False):
        tp=add("TP","third_place",k,1)
        if k>=2:
            for i,sem in enumerate(wb[-2]["matches"]):
                sem["loser_to"]={"match_id":"TP","slot":"home" if i==0 else "away"}
        wb[-1]["matches"].append(tp)
    def route(m,field):
        target=m.get(field)
        if target is None:return False
        value=m["winner" if field=="winner_to" else "loser"]
        if value is None:return False
        dest=allm[target["match_id"]];slot=target["slot"]
        if dest[slot]!=value:dest[slot]=value;return True
        return False
    given={}
    for res in results:
        if not isinstance(res,dict) or res.get("match_id") not in allm or not isinstance(res.get("winner"),str) or res["match_id"] in given:bad("results")
        given[res["match_id"]]=res["winner"]
    for _ in range(len(allm)*3):
        changed=False
        for m in allm.values():
            if m["bye"] and m["winner"] is None and m["home"] is not None:m["winner"]=m["home"];changed=True
            if m["match_id"] in given and m["winner"] is None and m["home"] and m["away"] and given[m["match_id"]] in (m["home"],m["away"]):
                m["winner"]=given[m["match_id"]];m["loser"]=m["away"] if m["winner"]==m["home"] else m["home"];changed=True
            if m["winner"] is not None:
                changed=route(m,"winner_to") or changed
                changed=route(m,"loser_to") or changed
        if not changed:break
    for mid,v in given.items():
        m=allm[mid]
        if m["winner"]!=v:bad("results")
    if double and len(gf)==2:
        g1=gf[0];g2=gf[1]
        if g1["winner"] is not None:g2["required"]=g1["winner"]==g1["away"]
        else:g2["home"],g2["away"]=g1["home"],g1["away"]
    if double:
        return {"format":"double_elim","bracket_size":size,"bracket_reset":bool(p.get("bracket_reset",False)),"winners":wb,"losers":lb,"grand_final":gf}
    return {"format":"single_elim","bracket_size":size,"rounds":wb}

def generate(data):
    fmt=data.get("format");teams=data.get("teams");p=data.get("params",{})
    limits={"round_robin":(2,40),"swiss":(2,64),"single_elim":(2,128),"double_elim":(3,128)}
    if fmt not in limits or not isinstance(teams,list) or not isinstance(p,dict) or not limits[fmt][0]<=len(teams)<=limits[fmt][1] or any(not identifier(t) for t in teams) or len(set(teams))!=len(teams):bad("format","teams","params")
    if fmt=="round_robin":return round_robin(teams,p)
    if fmt=="swiss":return swiss(teams,p)
    if fmt=="single_elim":return eliminate(teams,p)
    return eliminate(teams,p,True)

@router.post("/audit/v1/fixtures")
async def fixtures(req:Request):
    return generate(await body(req))

