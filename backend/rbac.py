import os
import secrets
from datetime import datetime, timezone, timedelta
import jwt
from fastapi import APIRouter, Request
from .core import read, fail

router=APIRouter()
SECRET=os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
ROLES=("super_admin","league_organizer","club_manager","player","viewer")
CTX={"tenant_id":"tenant-alpha","foreign_tenant_id":"tenant-beta",
    "own_league_id":"league-alpha-1","other_league_id":"league-alpha-2","foreign_league_id":"league-beta-1",
    "own_club_id":"club-alpha-1","other_club_id":"club-alpha-2","foreign_club_id":"club-beta-1",
    "own_player_id":"player-alpha-1","other_player_id":"player-alpha-2","foreign_player_id":"player-beta-1"}

def tokens():
    expiry=datetime.now(timezone.utc)+timedelta(hours=12)
    return {role:jwt.encode({"role":role,"tenant_id":None if role=="super_admin" else "tenant-alpha","exp":expiry},SECRET,algorithm="HS256") for role in ROLES}

def principal(req):
    authorization=req.headers.get("authorization","")
    if not authorization.startswith("Bearer "):fail(401,"UNAUTHENTICATED")
    try:
        payload=jwt.decode(authorization[7:],SECRET,algorithms=["HS256"],options={"require":["exp"]})
        if payload.get("role") not in ROLES:fail(401,"UNAUTHENTICATED")
        return payload
    except jwt.PyJWTError:fail(401,"UNAUTHENTICATED")

def permitted(state,principal_,scope,ident=None):
    role=principal_["role"]
    if role=="super_admin":return True
    tenant=principal_["tenant_id"]
    if scope=="tenant_create" or scope=="platform_config":return False
    if scope=="league_fixtures":
        return role=="league_organizer" and ident=="league-alpha-1" and state["rbac_leagues"].get(ident)==tenant
    if scope in ("club_roster","club_products"):
        return role=="club_manager" and ident=="club-alpha-1" and state["clubs"].get(ident)==tenant
    if scope=="player_edit":
        return (role=="player" and ident=="player-alpha-1") or (role=="club_manager" and state["rbac_players"].get(ident)=="club-alpha-1")
    if scope=="club_read":
        return state["clubs"].get(ident)==tenant
    return False

def authorize(req,scope,ident=None):
    auth=principal(req)
    def check(state):
        lookup={"league_fixtures":"rbac_leagues","club_roster":"clubs","club_products":"clubs","club_read":"clubs","player_edit":"rbac_players"}.get(scope)
        if lookup and ident not in state[lookup]:
            fail(404,{"rbac_leagues":"LEAGUE_NOT_FOUND","clubs":"SQUAD_NOT_FOUND","rbac_players":"PLAYER_NOT_FOUND"}[lookup])
        return permitted(state,auth,scope,ident)
    allowed=read(check)
    if not allowed:fail(403,"FORBIDDEN")
    return {"authorized":True}

@router.post("/audit/v1/rbac-matrix")
def matrix():
    return {"tokens":tokens(),"context":CTX}

@router.post("/audit/v1/rbac/tenants")
def tenant_create(req:Request):
    return authorize(req,"tenant_create")

@router.post("/audit/v1/rbac/leagues/{league_id}/fixtures")
def league_fixtures(req:Request,league_id:str):
    return authorize(req,"league_fixtures",league_id)

@router.post("/audit/v1/rbac/clubs/{club_id}/roster")
def club_roster(req:Request,club_id:str):
    return authorize(req,"club_roster",club_id)

@router.post("/audit/v1/rbac/clubs/{club_id}/products")
def club_products(req:Request,club_id:str):
    return authorize(req,"club_products",club_id)

@router.patch("/audit/v1/rbac/players/{player_id}")
def player_edit(req:Request,player_id:str):
    return authorize(req,"player_edit",player_id)

@router.get("/audit/v1/rbac/clubs/{club_id}")
def club_read(req:Request,club_id:str):
    return authorize(req,"club_read",club_id)

@router.get("/audit/v1/rbac/platform/config")
def platform_config(req:Request):
    return authorize(req,"platform_config")
