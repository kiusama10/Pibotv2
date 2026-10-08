"""Durable storage bridge for SAO-CB.

SAO-CB keeps its compatibility DB in SQLite because the legacy adapter is already
written/tested against SQLite. On Render the local filesystem is ephemeral, so
this module mirrors a consistent SQLite snapshot into PiBot's PostgreSQL after
committed writes and restores it on boot.

This deliberately uses a dedicated table and never touches PiBot gameplay tables.
"""
from __future__ import annotations
import gzip, hashlib, os, sqlite3, tempfile, threading, time
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = os.getenv("SAOCB_DB_PATH", "/tmp/saocb.db")
_SYNC_ENABLED = os.getenv("SAOCB_PG_SNAPSHOT", "1") == "1" and bool(DATABASE_URL)
_lock = threading.RLock()
_restored = False


def _pg_connect():
    import psycopg2
    return psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)


def _ensure_pg_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS saocb_sqlite_snapshot (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            payload BYTEA NOT NULL,
            sha256 TEXT NOT NULL,
            sqlite_size BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        )
        """)
    conn.commit()


def restore_once() -> bool:
    """Restore the last verified SAO-CB DB snapshot before schema initialization."""
    global _restored
    with _lock:
        if _restored:
            return False
        _restored = True
        if not _SYNC_ENABLED:
            return False
        try:
            pg = _pg_connect(); _ensure_pg_table(pg)
            with pg.cursor() as cur:
                cur.execute("SELECT payload, sha256 FROM saocb_sqlite_snapshot WHERE id=1")
                row = cur.fetchone()
            pg.close()
            if not row:
                return False
            raw = gzip.decompress(bytes(row[0]))
            if hashlib.sha256(raw).hexdigest() != row[1]:
                raise RuntimeError("SAO-CB PostgreSQL snapshot checksum mismatch")
            target = Path(DB_PATH); target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".restore")
            tmp.write_bytes(raw)
            # Validate before replacing the live file.
            chk = sqlite3.connect(str(tmp))
            ok = chk.execute("PRAGMA quick_check").fetchone()[0]
            chk.close()
            if ok != "ok":
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"SAO-CB restored snapshot failed quick_check: {ok}")
            os.replace(tmp, target)
            print("[SAO-CB] Estado restaurado desde PostgreSQL.")
            return True
        except Exception as exc:
            print(f"[SAO-CB] AVISO: no se pudo restaurar snapshot PostgreSQL: {type(exc).__name__}: {exc}")
            return False


def persist_connection(source: sqlite3.Connection) -> bool:
    """Create a transaction-consistent SQLite backup and atomically mirror it to PG."""
    if not _SYNC_ENABLED:
        return False
    with _lock:
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="saocb-snapshot-", suffix=".db")
            os.close(fd)
            snap = sqlite3.connect(tmp_path)
            source.backup(snap)
            snap.commit()
            ok = snap.execute("PRAGMA quick_check").fetchone()[0]
            snap.close()
            if ok != "ok":
                raise RuntimeError(f"SQLite quick_check failed: {ok}")
            raw = Path(tmp_path).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            payload = gzip.compress(raw, compresslevel=6)
            pg = _pg_connect(); _ensure_pg_table(pg)
            with pg.cursor() as cur:
                cur.execute("""
                    INSERT INTO saocb_sqlite_snapshot(id,payload,sha256,sqlite_size,updated_at)
                    VALUES(1,%s,%s,%s,%s)
                    ON CONFLICT(id) DO UPDATE SET
                      payload=EXCLUDED.payload,
                      sha256=EXCLUDED.sha256,
                      sqlite_size=EXCLUDED.sqlite_size,
                      updated_at=EXCLUDED.updated_at
                """, (payload, digest, len(raw), int(time.time())))
            pg.commit(); pg.close()
            return True
        except Exception as exc:
            print(f"[SAO-CB] ERROR persistiendo snapshot: {type(exc).__name__}: {exc}")
            return False
        finally:
            if tmp_path:
                try: os.unlink(tmp_path)
                except OSError: pass


class DurableConnection(sqlite3.Connection):
    """SQLite connection that snapshots only after successful write transactions."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saocb_dirty = False

    @staticmethod
    def _is_write(sql: str) -> bool:
        head = (sql or "").lstrip().split(None, 1)
        return bool(head) and head[0].upper() in {"INSERT","UPDATE","DELETE","REPLACE","CREATE","ALTER","DROP","VACUUM"}

    def execute(self, sql, parameters=(), /):
        if self._is_write(sql): self._saocb_dirty = True
        return super().execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters, /):
        if self._is_write(sql): self._saocb_dirty = True
        return super().executemany(sql, seq_of_parameters)

    def executescript(self, sql_script, /):
        if any(self._is_write(x) for x in sql_script.split(';') if x.strip()): self._saocb_dirty = True
        return super().executescript(sql_script)

    def __exit__(self, exc_type, exc, tb):
        result = super().__exit__(exc_type, exc, tb)
        if exc_type is None and self._saocb_dirty:
            persist_connection(self)
            self._saocb_dirty = False
        return result


def connect(path: str):
    c = sqlite3.connect(path, factory=DurableConnection, timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    return c
