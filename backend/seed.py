from .core import ORDER, sign

def baseline_sports():
    common = list(ORDER)
    return {
      "football": {"sport_id":"football","name":"Football","scoring_model":"event","periods":{"count":2,"duration_minutes":45},"scoring_events":{"goal":{"points":1}},"draw_allowed":True,"overtime":{"policy":"none"},"tie_break_order":common,"roster":{"min_squad_size":11,"max_squad_size":25,"required_positions":{"gk":1}}},
      "basketball":{"sport_id":"basketball","name":"Basketball","scoring_model":"event","periods":{"count":4,"duration_minutes":12},"scoring_events":{"free_throw":{"points":1},"two_pointer":{"points":2},"three_pointer":{"points":3}},"draw_allowed":False,"overtime":{"policy":"extra_time","duration_minutes":5},"tie_break_order":common,"roster":{"min_squad_size":5,"max_squad_size":15,"required_positions":{}}},
      "cricket":{"sport_id":"cricket","name":"Cricket","scoring_model":"innings","periods":{"innings_per_team":1,"overs_per_innings":20,"balls_per_over":6,"wickets_per_innings":10},"scoring_events":{"dot_ball":{"runs":0,"legal_ball":True,"wicket":False},"single":{"runs":1,"legal_ball":True,"wicket":False},"two":{"runs":2,"legal_ball":True,"wicket":False},"four":{"runs":4,"legal_ball":True,"wicket":False},"six":{"runs":6,"legal_ball":True,"wicket":False},"wide":{"runs":1,"legal_ball":False,"wicket":False},"no_ball":{"runs":1,"legal_ball":False,"wicket":False},"wicket":{"runs":0,"legal_ball":True,"wicket":True}},"draw_allowed":True,"overtime":{"policy":"super_over"},"tie_break_order":common,"roster":{"min_squad_size":11,"max_squad_size":18,"required_positions":{"wicketkeeper":1}}},
      "esports":{"sport_id":"esports","name":"Esports","scoring_model":"round","periods":{"best_of":3},"scoring_events":{"round_win":{"rounds":1}},"draw_allowed":False,"overtime":{"policy":"none"},"tie_break_order":common,"roster":{"min_squad_size":5,"max_squad_size":8,"required_positions":{}}}
    }

def baseline(seed=42, stock=None):
    defaults={"var-jersey-001-M":1,"var-jersey-001-L":5}
    defaults.update(stock or {})
    state={"seed":seed,"sports":baseline_sports(),"tenants":{"tenant-alpha":"Alpha Sports","tenant-beta":"Beta Athletics"},
      "leagues":{},"matches":{},"events_by_id":{},"rosters":{},"players":{},"transfers":{},"offline":{},"orders":{},
      "inventory":{key:{"stock":value,"reserved":0,"price_minor":450000} for key,value in defaults.items()},
      "clubs":{"club-alpha-1":"tenant-alpha","club-alpha-2":"tenant-alpha","club-beta-1":"tenant-beta"},
      "rbac_leagues":{"league-alpha-1":"tenant-alpha","league-alpha-2":"tenant-alpha","league-beta-1":"tenant-beta"},
      "rbac_players":{"player-alpha-1":"club-alpha-1","player-alpha-2":"club-alpha-2","player-beta-1":"club-beta-1","player-beta-2":"club-beta-1"},
      "auth_serial":0,
      # Day 2 reset entities. These are deliberately plain state records so
      # feature modules can extend them without changing the Day 1 schema.
      "stream_keys":{},"player_stream_keys":{},"costream_sessions":{},
      "athlete_follows":{},"vod_index":{},"qr_links":{},
      "guest_tokens":{"guest_anon_tok_7721":{"status":"valid","merged":False,"role":"guest","read_only":True}},
      "carts":{"player-alpha-1":{"user_id":"player-alpha-1","currency":"PKR","items":[]}},
      "day2_signature_records":{}}
    for pid,club in (("player-alpha-1","club-alpha-1"),("player-alpha-2","club-alpha-2"),("player-beta-1","club-beta-1"),("player-beta-2","club-beta-1")):
        state["players"][pid]={"player_id":pid,"club_id":club,"tenant_id":"tenant-alpha" if club.startswith("club-alpha") else "tenant-beta","name":pid.replace("-"," ").title()}
    events=[]
    for eid,kind,payload in (("m1-init","match_init",{"sport_id":"football","home_team_id":"club-alpha-1","away_team_id":"club-alpha-2","league_id":"league-alpha-1"}),
                             ("m1-start","match_start",{}),("m1-goal","score",{"team_id":"club-alpha-1","event_type":"goal"})):
        events.append({"event_id":eid,"type":kind,"payload":payload,"signature":sign(eid,payload)})
        state["events_by_id"][eid]={"request":{"event_id":eid,"match_id":"match-m1","type":kind,"payload":payload},"response":{"event_id":eid,"match_id":"match-m1","type":kind,"signature":events[-1]["signature"]}}
    state["matches"]["match-m1"]={"match_id":"match-m1","sport_id":"football","league_id":"league-alpha-1","home":"club-alpha-1","away":"club-alpha-2","events":events}
    state["qr_links"]={
      "match-m1":{"entity_id":"match-m1","short_url":"http://localhost:8080/q/m1-live","scan_count":0},
      "player-alpha-1":{"entity_id":"player-alpha-1","short_url":"http://localhost:8080/q/p-alpha-1","scan_count":0},
      "club-alpha-1":{"entity_id":"club-alpha-1","short_url":"http://localhost:8080/q/c-alpha-1","scan_count":0}}
    return state
