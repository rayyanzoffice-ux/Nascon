from backend.fixtures import generate

def test_round_robin_odd_balance():
    x=generate({"format":"round_robin","teams":["a","b","c","d","e"],"params":{"legs":2}})
    assert x["round_count"]==10
    assert x["summary"]["total"]==20
    pair=set()
    for round_ in x["rounds"]:
        assert len(round_["byes"])==1
        for m in round_["matches"]:pair.add((m["home"],m["away"]))
    assert len(pair)==20

def test_elimination_seeding():
    b=generate({"format":"single_elim","teams":[f"t{i}" for i in range(1,7)]})
    first=b["rounds"][0]["matches"]
    assert [m["home"] for m in first]==["t1","t4","t2","t3"]
    assert [m["bye"] for m in first]==[True,False,True,False]

def test_swiss_first_round():
    s=generate({"format":"swiss","teams":["a","b","c","d","e"]})
    assert [(m["home"],m["away"]) for m in s["pairings"]]==[("a","c"),("b","d")]
    assert s["bye"]=="e"
