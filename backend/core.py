import copy
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from contextlib import contextmanager
import psycopg

ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
SPORT_ID = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_ID = re.compile(r"^[a-z0-9_]{1,40}$")
ORDER = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://nascon:nascon_local@localhost:5432/nascon")

class APIError(Exception):
    def __init__(self, status, code, details=None, message=None):
        self.status = status
        self.code = code
        self.details = details or {}
        self.message = message or code.replace("_", " ").title()
        super().__init__(self.message)

def fail(status, code, **details):
    raise APIError(status, code, details)

def bad(*fields):
    fail(400, "VALIDATION_ERROR", fields=list(fields))

def identifier(x):
    return isinstance(x, str) and ID.fullmatch(x) is not None

def positive_int(x):
    return type(x) is int and x >= 1

def integer(x):
    return type(x) is int

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sign(id_, payload):
    salt = os.environ.get("DAY1_SALT", "")
    return hmac.new(salt.encode("utf-8"), (id_ + "|" + canonical(payload)).encode("utf-8"), hashlib.sha256).hexdigest()

def validate_order(values, fallback=ORDER):
    if values is None:
        return list(fallback)
    if not isinstance(values, list) or any(not isinstance(x,str) or x not in ORDER for x in values) or len(set(values)) != len(values):
        bad("tie_break_order")
    return list(values) if "draw_lots" in values else list(values) + ["draw_lots"]

def init_database():
    for attempt in range(30):
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as c:
                c.execute("CREATE TABLE IF NOT EXISTS app_state (id INTEGER PRIMARY KEY CHECK (id=1), doc JSONB NOT NULL)")
            return
        except psycopg.OperationalError:
            if attempt == 29: raise
            time.sleep(1)

def read(fn):
    with psycopg.connect(DATABASE_URL) as c:
        row = c.execute("SELECT doc FROM app_state WHERE id=1").fetchone()
        if row is None:
            raise RuntimeError("Database not seeded")
        return fn(row[0])

def mutate(fn):
    with psycopg.connect(DATABASE_URL) as c:
        with c.transaction():
            row = c.execute("SELECT doc FROM app_state WHERE id=1 FOR UPDATE").fetchone()
            if row is None: raise RuntimeError("Database not seeded")
            state = row[0]
            result = fn(state)
            c.execute("UPDATE app_state SET doc=%s::jsonb WHERE id=1", (json.dumps(state),))
            return result

def set_seed(state):
    with psycopg.connect(DATABASE_URL) as c:
        with c.transaction():
            c.execute("INSERT INTO app_state(id,doc) VALUES(1,%s::jsonb) ON CONFLICT(id) DO UPDATE SET doc=EXCLUDED.doc", (json.dumps(state),))

def boot(seed_fn):
    init_database()
    with psycopg.connect(DATABASE_URL) as c:
        row = c.execute("SELECT 1 FROM app_state WHERE id=1").fetchone()
    if row is None: set_seed(seed_fn(42, None))
