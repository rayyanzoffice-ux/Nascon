import copy
import hashlib
import hmac
import json
import os
import re
import time
from queue import Empty, Queue
from threading import Lock
from datetime import datetime, timezone
from contextlib import contextmanager
import psycopg

ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
SPORT_ID = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_ID = re.compile(r"^[a-z0-9_]{1,40}$")
ORDER = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://nascon@localhost:5432/nascon")
_CONNECTION_LIMIT = 32
_connections = Queue(maxsize=_CONNECTION_LIMIT)
_connection_count = 0
_connection_lock = Lock()

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


def sign_day2(id_, payload):
    """Shared Day 2 HMAC primitive; callers supply their contract payload."""
    salt=os.environ.get("DAY2_SALT")
    if not salt:
        raise RuntimeError("DAY2_SALT is required for Day 2 signatures")
    if not isinstance(id_,str) or not isinstance(payload,dict):bad("signature_payload")
    message=(id_+"|"+canonical(payload)).encode("utf-8")
    return hmac.new(salt.encode("utf-8"),message,hashlib.sha256).hexdigest()


def verify_day2(id_, payload, signature):
    return isinstance(signature,str) and hmac.compare_digest(sign_day2(id_,payload),signature)

def validate_order(values, fallback=ORDER):
    if values is None:
        return list(fallback)
    if not isinstance(values, list) or any(not isinstance(x,str) or x not in ORDER for x in values) or len(set(values)) != len(values):
        bad("tie_break_order")
    return [x for x in values if x != "draw_lots"] + ["draw_lots"]

def init_database():
    for attempt in range(30):
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as c:
                c.execute("CREATE TABLE IF NOT EXISTS app_state (id INTEGER PRIMARY KEY CHECK (id=1), doc JSONB NOT NULL)")
            return
        except psycopg.OperationalError:
            if attempt == 29: raise
            time.sleep(1)


@contextmanager
def database_connection():
    """Lease a PostgreSQL connection without changing transaction semantics.

    API reads are bursty (QR viewers) and creating a TCP connection for every
    request makes otherwise inexpensive reads queue behind connection setup.
    Connections remain process-local and are rolled back before reuse after an
    error, so request state cannot leak across callers.
    """
    global _connection_count
    try:
        conn = _connections.get_nowait()
    except Empty:
        with _connection_lock:
            if _connection_count < _CONNECTION_LIMIT:
                conn = psycopg.connect(DATABASE_URL)
                _connection_count += 1
            else:
                conn = None
        if conn is None:
            conn = _connections.get(timeout=10)
    reusable = True
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        if isinstance(exc, psycopg.Error):
            reusable = False
        try:
            conn.rollback()
        except psycopg.Error:
            reusable = False
        raise
    finally:
        if reusable and not conn.closed:
            _connections.put(conn)
        else:
            try:
                conn.close()
            finally:
                with _connection_lock:
                    _connection_count -= 1


def warm_database_connections(count=16):
    """Create a modest set of reusable connections before a traffic burst."""
    leased = []
    try:
        for _ in range(min(count, _CONNECTION_LIMIT)):
            with _connection_lock:
                global _connection_count
                if _connection_count >= _CONNECTION_LIMIT:
                    break
                conn = psycopg.connect(DATABASE_URL)
                _connection_count += 1
            leased.append(conn)
    finally:
        for conn in leased:
            _connections.put(conn)


def _database_call(fn):
    """Retry once after a PostgreSQL restart invalidates an idle connection."""
    for attempt in range(2):
        try:
            with database_connection() as conn:
                return fn(conn)
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if attempt:
                raise

def read(fn):
    def operation(c):
        row = c.execute("SELECT doc FROM app_state WHERE id=1").fetchone()
        if row is None:
            raise RuntimeError("Database not seeded")
        return fn(row[0])
    return _database_call(operation)


def read_fragment(sql, params, fn):
    """Run a read against a small JSONB projection instead of the whole state."""
    def operation(c):
        row = c.execute(sql, params).fetchone()
        if row is None or row[0] is None:
            raise RuntimeError("Database not seeded")
        return fn(row[0])
    return _database_call(operation)

def mutate(fn):
    def operation(c):
        with c.transaction():
            row = c.execute("SELECT doc FROM app_state WHERE id=1 FOR UPDATE").fetchone()
            if row is None: raise RuntimeError("Database not seeded")
            state = row[0]
            result = fn(state)
            c.execute("UPDATE app_state SET doc=%s::jsonb WHERE id=1", (json.dumps(state),))
            return result
    return _database_call(operation)

def set_seed(state):
    with database_connection() as c:
        with c.transaction():
            c.execute("INSERT INTO app_state(id,doc) VALUES(1,%s::jsonb) ON CONFLICT(id) DO UPDATE SET doc=EXCLUDED.doc", (json.dumps(state),))

def boot(seed_fn):
    init_database()
    with database_connection() as c:
        row = c.execute("SELECT 1 FROM app_state WHERE id=1").fetchone()
    if row is None: set_seed(seed_fn(42, None))
    warm_database_connections()

