"""Database-backed single-poller guard.
Only one PiBot process sharing DATABASE_URL may own Telegram polling at a time.
The PostgreSQL advisory lock lives for the lifetime of the dedicated connection.
"""
import hashlib
import psycopg2
from src.config import DATABASE_URL, BOT_TOKEN

_LOCK_CONN = None


def acquire_single_poller_lock() -> bool:
    global _LOCK_CONN
    if _LOCK_CONN is not None and not _LOCK_CONN.closed:
        return True
    # Lock is stable for this bot token but never logs/exposes the token.
    raw = hashlib.sha256(("pibot-poller:" + BOT_TOKEN).encode()).digest()[:8]
    key = int.from_bytes(raw, "big", signed=True)
    conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)
    conn.autocommit = True
    with conn.cursor() as c:
        c.execute("SELECT pg_try_advisory_lock(%s)", (key,))
        ok = bool(c.fetchone()[0])
    if not ok:
        conn.close()
        return False
    _LOCK_CONN = conn
    return True
