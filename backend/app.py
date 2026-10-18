import json, re, time
from collections import defaultdict, deque
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .core import APIError, ORDER, SPORT_ID, EVENT_ID, bad, fail, identifier, positive_int, integer, validate_order, boot, read, mutate, set_seed
from .seed import baseline

app = FastAPI(title="NaSCon 2026 Phase I")
rate = defaultdict(deque)
@app.on_event("startup")
def startup():
    boot(baseline)

@app.exception_handler(APIError)
async def api_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"error":{"code":exc.code,"message":exc.message,"details":exc.details}})

@app.middleware("http")
async def envelope(request, call_next):
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        from .guest import bearer_token, reject_guest_write
        try:
            reject_guest_write(bearer_token(request))
        except APIError as exc:
            return JSONResponse(status_code=exc.status, content={"error":{"code":exc.code,"message":exc.message,"details":exc.details}})
    if request.method in ("POST","PATCH","PUT") and request.url.path.startswith("/audit/v1/"):
        body = await request.body()
        if len(body) > 1048576:
            return JSONResponse(status_code=413, content={"error":{"code":"PAYLOAD_TOO_LARGE","message":"Body exceeds 1MB","details":{}}})
    if request.url.path.startswith("/api/v1/"):
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = rate[ip]
        while q and q[0] < now-10: q.popleft()
        if len(q) >= 100:
            return JSONResponse(status_code=429, headers={"Retry-After":"10"}, content={"error":{"code":"RATE_LIMITED","message":"Too many requests","details":{}}})
        q.append(now)
    try:
        return await call_next(request)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error":{"code":"VALIDATION_ERROR","message":"Malformed request","details":{"fields":[]}}})

async def body(request, optional=False):
    raw = await request.body()
    if not raw and optional: return {}
    try: data = json.loads(raw, parse_constant=lambda _: bad("body"))
    except (ValueError, UnicodeDecodeError): bad("body")
    if not isinstance(data,dict): bad("body")
    return data

@app.get("/health")
def health():
    return read(lambda s: {"status":"ok"} if s.get("sports") and s.get("tenants") else fail(503,"VALIDATION_ERROR"))

@app.get("/api/v1/ping")
def ping():
    return {"pong":True}

@app.post("/audit/v1/reset")
async def reset(req: Request):
    data=await body(req,True)
    seed=data.get("seed",42)
    stock=data.get("stock",{"var-jersey-001-M":1,"var-jersey-001-L":5})
    if not integer(seed): bad("seed")
    if not isinstance(stock,dict) or any(not identifier(k) or not integer(v) or v<0 for k,v in stock.items()): bad("stock")
    state=baseline(seed,stock)
    set_seed(state)
    return {"status":"reset_complete","seed":seed,"sports":list(state["sports"]),"tenants":list(state["tenants"]),"stock":{key:v["stock"] for key,v in state["inventory"].items()}}

def validate_sport(d):
    fields=[]
    sid=d.get("sport_id"); name=d.get("name"); model=d.get("scoring_model")
    if not isinstance(sid,str) or not SPORT_ID.fullmatch(sid): fields.append("sport_id")
    if not isinstance(name,str) or not (1<=len(name)<=80): fields.append("name")
    if model not in ("event","innings","round"): fields.append("scoring_model")
    periods=d.get("periods")
    if not isinstance(periods,dict): fields.append("periods")
    else:
        keys={"event":["count","duration_minutes"],"innings":["innings_per_team","overs_per_innings","balls_per_over","wickets_per_innings"],"round":["best_of"]}.get(model,[])
        if any(not positive_int(periods.get(k)) for k in keys) or (model=="round" and positive_int(periods.get("best_of")) and periods["best_of"]%2==0): fields.append("periods")
    ev=d.get("scoring_events")
    if not isinstance(ev,dict) or not ev: fields.append("scoring_events")
    else:
        for key,value in ev.items():
            if not isinstance(key,str) or not EVENT_ID.fullmatch(key) or not isinstance(value,dict):
                fields.append("scoring_events"); break
            if model=="event" and not positive_int(value.get("points")) or model=="round" and not positive_int(value.get("rounds")) or model=="innings" and (not integer(value.get("runs")) or value["runs"]<0 or type(value.get("legal_ball")) is not bool or type(value.get("wicket")) is not bool):
                fields.append("scoring_events"); break
    if type(d.get("draw_allowed")) is not bool: fields.append("draw_allowed")
    overtime=d.get("overtime")
    if not isinstance(overtime,dict) or overtime.get("policy") not in ("none","extra_time","shootout","golden_score","super_over") or ("duration_minutes" in overtime and (not integer(overtime["duration_minutes"]) or overtime["duration_minutes"]<0)):
        fields.append("overtime")
    roster=d.get("roster")
    if not isinstance(roster,dict) or not positive_int(roster.get("min_squad_size")) or not positive_int(roster.get("max_squad_size")) or (positive_int(roster.get("min_squad_size")) and positive_int(roster.get("max_squad_size")) and roster["min_squad_size"]>roster["max_squad_size"]) or not isinstance(roster.get("required_positions"),dict) or any(not isinstance(k,str) or not integer(v) or v<0 for k,v in (roster.get("required_positions") if isinstance(roster.get("required_positions"),dict) else {}).items()):
        fields.append("roster")
    try: order=validate_order(d.get("tie_break_order"))
    except APIError: fields.append("tie_break_order"); order=ORDER
    if fields: bad(*dict.fromkeys(fields))
    saved={k:d[k] for k in ("sport_id","name","scoring_model","periods","scoring_events","draw_allowed","overtime","roster")}
    saved["tie_break_order"]=order
    return saved

@app.post("/audit/v1/sports",status_code=201)
async def create_sport(req:Request):
    config=validate_sport(await body(req))
    def change(s):
        sid=config["sport_id"]
        if sid in s["sports"]: fail(409,"SPORT_EXISTS")
        s["sports"][sid]=config
        return {"sport_id":sid,"status":"created","config":config}
    return mutate(change)

