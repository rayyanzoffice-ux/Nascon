import jwt, pytest
from backend.rbac import tokens,permitted,SECRET
from backend.seed import baseline
def test_roles_and_tenant():
    s=baseline()
    org={"role":"league_organizer","tenant_id":"tenant-alpha"}
    assert permitted(s,org,"league_fixtures","league-alpha-1")
    assert not permitted(s,org,"league_fixtures","league-alpha-2")
    assert not permitted(s,org,"club_roster","club-alpha-1")
    assert not permitted(s,org,"club_read","club-beta-1")
    assert permitted(s,{"role":"super_admin"},"platform_config")
def test_jwt_signed():
    result=tokens()
    assert jwt.decode(result["viewer"],SECRET,algorithms=["HS256"])["role"]=="viewer"
