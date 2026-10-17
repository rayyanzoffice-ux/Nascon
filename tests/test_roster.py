from backend.seed import baseline
from backend.roster import setup_apply,transfer_apply,maybe_return
def sample():
    return {"league":{"league_id":"test-l","tenant_id":"tenant-alpha","sport_id":"football","transfer_window":{"open":"2026-09-01","close":"2026-09-30"},"required_positions":{},"max_squad_size":3},"squads":[{"squad_id":"s1","club_id":"c1","tenant_id":"tenant-alpha","name":"First"},{"squad_id":"s2","club_id":"c2","tenant_id":"tenant-alpha","name":"Second"}],"players":[{"player_id":"p1","name":"Ali","position":"df","squad_id":"s1","role":"starter"}]}
def test_loan_auto_return():
    s=baseline();setup_apply(s,sample())
    d={"request_id":"tr1","league_id":"test-l","player_id":"p1","type":"loan","from_squad_id":"s1","to_squad_id":"s2","effective_date":"2026-09-28","loan_end_date":"2026-10-03","reason":"cover","requested_by":"manager"}
    assert transfer_apply(s,d)[0]==201
    maybe_return(s["players"]["p1"],"2026-10-04")
    assert s["players"]["p1"]["squad_id"]=="s1"
    assert [x["action"] for x in s["players"]["p1"]["history"]]==["loan","loan_return"]
