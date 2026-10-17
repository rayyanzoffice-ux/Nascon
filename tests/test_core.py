from backend.core import canonical, sign, validate_order
from backend.seed import baseline, baseline_sports
import os

def test_signature_vector(monkeypatch):
    monkeypatch.setenv("DAY1_SALT","demo-salt")
    assert sign("evt-1",{"team_id":"t1","event_type":"goal"})=="972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501"

def test_seeds():
    state=baseline()
    assert list(state["sports"])==["football","basketball","cricket","esports"]
    assert state["inventory"]["var-jersey-001-M"]["stock"]==1

def test_canonical():
    assert canonical({"b":1,"a":"é"})=='{"a":"é","b":1}'
