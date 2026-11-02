import json
from . import provider
from .db import pool

LEASE_SECONDS = 300
ACTIVE = "('queued','leased','running')"

class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message

def _lock(cur):
    cur.execute("SELECT 1 FROM quota WHERE id = 1 FOR UPDATE")

def _free(cur) -> int:
    cur.execute("SELECT total - used - leased AS free FROM quota WHERE id = 1")
    return cur.fetchone()["free"]

def _expire_and_promote(cur):
    cur.execute("""
        WITH e AS (UPDATE lookups SET status='expired'
                   WHERE status='leased' AND lease_expires_at <= now() RETURNING 1)
        UPDATE quota SET leased = leased - (SELECT count(*) FROM e) WHERE id = 1""")
    free = _free(cur)
    if free > 0:
        cur.execute("""
            WITH picked AS (DELETE FROM queue WHERE seq IN
                              (SELECT seq FROM queue ORDER BY seq LIMIT %s) RETURNING lookup_id),
                 p AS (UPDATE lookups SET status='leased',
                                          lease_expires_at = now() + make_interval(secs => %s)
                       WHERE id IN (SELECT lookup_id FROM picked) RETURNING 1)
            UPDATE quota SET leased = leased + (SELECT count(*) FROM p) WHERE id = 1""",
            (free, LEASE_SECONDS))

def _view(cur, lookup_id) -> dict:
    cur.execute("""
        SELECT l.id, l.indicator, l.analyst_id, l.verdict,
               CASE WHEN l.status='leased' AND l.lease_expires_at <= now() THEN 'expired' ELSE l.status END AS status,
               GREATEST(0, EXTRACT(EPOCH FROM (l.lease_expires_at - now())))::int AS seconds_left,
               (SELECT count(*) FROM queue q WHERE q.seq <= qq.seq) AS position
        FROM lookups l LEFT JOIN queue qq ON qq.lookup_id = l.id
        WHERE l.id = %s""", (lookup_id,))
    row = cur.fetchone()
    if not row:
        raise ApiError(404, "lookup not found")
    row["id"] = str(row["id"])
    if row["status"] != "queued":
        row["position"] = None
    if row["status"] not in ("leased", "running"):
        row["seconds_left"] = None
    return row

def quota_snapshot() -> dict:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT total, used, leased, total-used-leased AS available,
                       (SELECT count(*) FROM queue) AS queued FROM quota WHERE id=1""")
        return cur.fetchone()

def request_enrichment(indicator: str, analyst_id: str, key: str) -> dict:
    indicator = indicator.strip().lower()
    with pool.connection() as conn, conn.cursor() as cur:
        _lock(cur)
        cur.execute("SELECT lookup_id FROM idempotency_keys WHERE key=%s", (key,))
        if (r := cur.fetchone()):
            return {**_view(cur, r["lookup_id"]), "shared": False, "replayed": True}
        _expire_and_promote(cur)
        cur.execute(f"SELECT id FROM lookups WHERE indicator=%s AND status IN {ACTIVE}", (indicator,))
        if (r := cur.fetchone()):
            cur.execute("INSERT INTO idempotency_keys (key, lookup_id) VALUES (%s,%s)", (key, r["id"]))
            return {**_view(cur, r["id"]), "shared": True, "replayed": False}
        if _free(cur) > 0:
            cur.execute("""INSERT INTO lookups (indicator, analyst_id, status, lease_expires_at)
                           VALUES (%s,%s,'leased', now() + make_interval(secs => %s)) RETURNING id""",
                        (indicator, analyst_id, LEASE_SECONDS))
            lid = cur.fetchone()["id"]
            cur.execute("UPDATE quota SET leased = leased + 1 WHERE id=1")
        else:
            cur.execute("INSERT INTO lookups (indicator, analyst_id, status) VALUES (%s,%s,'queued') RETURNING id",
                        (indicator, analyst_id))
            lid = cur.fetchone()["id"]
            cur.execute("INSERT INTO queue (lookup_id) VALUES (%s)", (lid,))
        cur.execute("INSERT INTO idempotency_keys (key, lookup_id) VALUES (%s,%s)", (key, lid))
        return {**_view(cur, lid), "shared": False, "replayed": False}

def run_lookup(lookup_id: str) -> dict:
    with pool.connection() as conn, conn.cursor() as cur:
        _lock(cur)
        _expire_and_promote(cur)
        cur.execute("SELECT status, indicator FROM lookups WHERE id=%s FOR UPDATE", (lookup_id,))
        row = cur.fetchone()
        if not row:
            raise ApiError(404, "lookup not found")
        if row["status"] == "completed":          
            return _view(cur, lookup_id)
        if row["status"] != "leased":
            raise ApiError(409, f"cannot run: lookup is {row['status']}")
        cur.execute("UPDATE lookups SET status='running' WHERE id=%s", (lookup_id,))
        indicator = row["indicator"]
    try:
        result = provider.lookup(indicator)
    except Exception:
        with pool.connection() as conn, conn.cursor() as cur:
            _lock(cur)
            cur.execute("UPDATE lookups SET status='leased' WHERE id=%s", (lookup_id,))  
        raise ApiError(502, "provider failed; lease kept, you can retry")
    with pool.connection() as conn, conn.cursor() as cur:
        _lock(cur)
        cur.execute("UPDATE lookups SET status='completed', verdict=%s::jsonb WHERE id=%s",
                    (json.dumps(result), lookup_id))
        cur.execute("UPDATE quota SET leased = leased - 1, used = used + 1 WHERE id=1")
        _expire_and_promote(cur)
        return _view(cur, lookup_id)

def get_lookup(lookup_id: str) -> dict:
    with pool.connection() as conn, conn.cursor() as cur:
        return _view(cur, lookup_id)

def sweep():
    with pool.connection() as conn, conn.cursor() as cur:
        _lock(cur)
        _expire_and_promote(cur)

def reset(total: int):
    with pool.connection() as conn, conn.cursor() as cur:
        _lock(cur)
        cur.execute("TRUNCATE queue, idempotency_keys, lookups")
        cur.execute("UPDATE quota SET total=%s, used=0, leased=0 WHERE id=1", (total,))
