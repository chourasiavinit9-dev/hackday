"""
SkillForge — Audit Ledger
Hash-chained tamper-evident action ledger. Every tool action is recorded.

Storage backends (auto-selected):
  DATABASE_URL set  → PostgreSQL (Render / DigitalOcean Managed Postgres)
  DATABASE_URL unset → SQLite (local dev, /tmp on Render free tier)
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Optional

DB_PATH    = os.environ.get("SKILLFORGE_DB", "skillforge.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")   # PostgreSQL DSN on Render

# Detect backend
_USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_record(sequence, timestamp, run_id, skill, tool,
                 input_digest, result_digest, previous_hash) -> str:
    payload = f"{sequence}|{timestamp}|{run_id}|{skill or ''}|{tool}|{input_digest}|{result_digest}|{previous_hash}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _digest(data) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


COLS = ["sequence", "timestamp", "run_id", "skill", "tool",
        "input_digest", "result_digest", "previous_hash", "hash"]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS ledger (
    sequence       INTEGER PRIMARY KEY,
    timestamp      TEXT NOT NULL,
    run_id         TEXT NOT NULL,
    skill          TEXT,
    tool           TEXT NOT NULL,
    input_digest   TEXT NOT NULL,
    result_digest  TEXT NOT NULL,
    previous_hash  TEXT NOT NULL,
    hash           TEXT NOT NULL
)
"""


# ── PostgreSQL backend ────────────────────────────────────────────────────────

def _pg_conn():
    import psycopg2
    # Render injects postgres:// but psycopg2 needs postgresql://
    dsn = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(dsn)


def _pg_init():
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL.replace("INTEGER PRIMARY KEY",
                                           "SERIAL PRIMARY KEY"))
        conn.commit()


def _pg_last() -> Optional[dict]:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ledger ORDER BY sequence DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                return dict(zip(COLS, row))
    return None


def _pg_insert(sequence, timestamp, run_id, skill, tool,
               input_digest, result_digest, previous_hash, hash_val):
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ledger (sequence, timestamp, run_id, skill, tool,
                    input_digest, result_digest, previous_hash, hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (sequence, timestamp, run_id, skill, tool,
                  input_digest, result_digest, previous_hash, hash_val))
        conn.commit()


def _pg_all() -> list[dict]:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ledger ORDER BY sequence ASC")
            return [dict(zip(COLS, row)) for row in cur.fetchall()]


def _pg_history(run_id, limit) -> list[dict]:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            if run_id:
                cur.execute(
                    "SELECT * FROM ledger WHERE run_id=%s ORDER BY sequence DESC LIMIT %s",
                    (run_id, limit))
            else:
                cur.execute(
                    "SELECT * FROM ledger ORDER BY sequence DESC LIMIT %s",
                    (limit,))
            return [dict(zip(COLS, row)) for row in cur.fetchall()]


def _pg_clear():
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ledger")
        conn.commit()


# ── SQLite backend ────────────────────────────────────────────────────────────

def _sq_conn():
    import sqlite3
    return sqlite3.connect(DB_PATH)


def _sq_init():
    with _sq_conn() as conn:
        conn.execute(CREATE_SQL)
        conn.commit()


def _sq_last() -> Optional[dict]:
    with _sq_conn() as conn:
        row = conn.execute(
            "SELECT * FROM ledger ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row:
            return dict(zip(COLS, row))
    return None


def _sq_insert(sequence, timestamp, run_id, skill, tool,
               input_digest, result_digest, previous_hash, hash_val):
    with _sq_conn() as conn:
        conn.execute("""
            INSERT INTO ledger (sequence, timestamp, run_id, skill, tool,
                input_digest, result_digest, previous_hash, hash)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (sequence, timestamp, run_id, skill, tool,
              input_digest, result_digest, previous_hash, hash_val))
        conn.commit()


def _sq_all() -> list[dict]:
    with _sq_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ledger ORDER BY sequence ASC"
        ).fetchall()
    return [dict(zip(COLS, row)) for row in rows]


def _sq_history(run_id, limit) -> list[dict]:
    with _sq_conn() as conn:
        if run_id:
            rows = conn.execute(
                "SELECT * FROM ledger WHERE run_id=? ORDER BY sequence DESC LIMIT ?",
                (run_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ledger ORDER BY sequence DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(zip(COLS, row)) for row in rows]


def _sq_clear():
    with _sq_conn() as conn:
        conn.execute("DELETE FROM ledger")
        conn.commit()


# ── Unified AuditLedger ───────────────────────────────────────────────────────

class AuditLedger:
    def __init__(self, db_path: str = DB_PATH):
        global DB_PATH
        DB_PATH = db_path   # allow tests to inject a temp path
        self.db_path = db_path
        self._backend = "postgres" if _USE_POSTGRES else "sqlite"
        self._init_db()

    def _init_db(self):
        if _USE_POSTGRES:
            try:
                _pg_init()
                return
            except Exception as e:
                print(f"[Ledger] Postgres init failed ({e}), falling back to SQLite")
        _sq_init()

    def _get_last(self) -> Optional[dict]:
        try:
            if _USE_POSTGRES:
                return _pg_last()
        except Exception:
            pass
        return _sq_last()

    def append(self, run_id: str, skill: Optional[str], tool: str,
               input_data, result_data) -> dict:
        last = self._get_last()
        sequence      = (last["sequence"] + 1) if last else 1
        previous_hash = last["hash"] if last else "0" * 64
        timestamp     = datetime.utcnow().isoformat()
        input_digest  = _digest(input_data)
        result_digest = _digest(result_data)
        hash_val = _hash_record(sequence, timestamp, run_id, skill, tool,
                                input_digest, result_digest, previous_hash)
        try:
            if _USE_POSTGRES:
                _pg_insert(sequence, timestamp, run_id, skill, tool,
                           input_digest, result_digest, previous_hash, hash_val)
            else:
                _sq_insert(sequence, timestamp, run_id, skill, tool,
                           input_digest, result_digest, previous_hash, hash_val)
        except Exception as e:
            print(f"[Ledger] Write error: {e}")

        return {
            "sequence": sequence, "timestamp": timestamp, "run_id": run_id,
            "skill": skill, "tool": tool, "input_digest": input_digest,
            "result_digest": result_digest, "previous_hash": previous_hash,
            "hash": hash_val
        }

    def verify(self) -> dict:
        try:
            records = _pg_all() if _USE_POSTGRES else _sq_all()
        except Exception:
            records = _sq_all()

        if not records:
            return {"valid": True, "total_records": 0,
                    "message": "Empty ledger — nothing to verify."}

        previous_hash = "0" * 64
        for r in records:
            expected = _hash_record(
                r["sequence"], r["timestamp"], r["run_id"], r["skill"],
                r["tool"], r["input_digest"], r["result_digest"], r["previous_hash"]
            )
            if r["hash"] != expected or r["previous_hash"] != previous_hash:
                return {
                    "valid": False,
                    "total_records": len(records),
                    "first_invalid_sequence": r["sequence"],
                    "message": f"Tamper detected at action #{r['sequence']}"
                }
            previous_hash = r["hash"]

        return {
            "valid": True,
            "total_records": len(records),
            "first_invalid_sequence": None,
            "message": f"Ledger integrity verified — {len(records)} actions checked.",
            "backend": self._backend
        }

    def history(self, run_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        try:
            return _pg_history(run_id, limit) if _USE_POSTGRES else _sq_history(run_id, limit)
        except Exception:
            return _sq_history(run_id, limit)

    def clear(self):
        """For testing only."""
        if _USE_POSTGRES:
            _pg_clear()
        else:
            _sq_clear()


# ── Singleton ─────────────────────────────────────────────────────────────────
_ledger: Optional[AuditLedger] = None


def get_ledger() -> AuditLedger:
    global _ledger
    if _ledger is None:
        _ledger = AuditLedger()
    return _ledger
