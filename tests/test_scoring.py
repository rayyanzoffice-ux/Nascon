import pytest
from backend.core import APIError, sign
from backend.scoring import event_apply, projection
from backend.seed import baseline

def test_signature_vector(monkeypatch):
    monkeypatch.setenv("DAY1_SALT","demo-salt")
    assert sign("evt-1",{"team_id":"t1","event_type":"goal"})=="972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501"

def test_scoring_and_correction(monkeypatch):
    monkeypatch.setenv("DAY1_SALT","demo-salt")
    state=baseline()
    def add(eid,typ,payload):
        return event_apply(state,{"event_id":eid,"match_id":"m1","type":typ,"payload":payload})
    assert add("init","match_init",{"sport_id":"football","home_team_id":"t1","away_team_id":"t2"})[0]==201
    add("start","match_start",{})
    assert add("goal","score",{"team_id":"t1","event_type":"goal"})[0]==201
    assert projection(state["matches"]["m1"],state["sports"])["home"]["score"]==1
    add("undo","compensation",{"compensates":"goal","reason":"VAR review"})
    p=projection(state["matches"]["m1"],state["sports"])
    assert p["home"]["score"]==0
    assert p["events"][2]["compensated"]
    assert p["events"][2]["compensated_by"]=="undo"

def test_idempotence_and_transition():
    state=baseline()
    data={"event_id":"init","match_id":"m","type":"match_init","payload":{"sport_id":"football","home_team_id":"a","away_team_id":"b"}}
    assert event_apply(state,data)[0]==201
    assert event_apply(state,data)[0]==200
    with pytest.raises(APIError) as x:
        event_apply(state,{"event_id":"e","match_id":"m","type":"score","payload":{"team_id":"a","event_type":"goal"}})
    assert x.value.code=="MATCH_NOT_IN_PROGRESS"
