"""Small transactional SQLite repository. Artifacts are never deleted here."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_SCHEDULE = {
    "enabled": False, "interval_minutes": 1440, "count": 1, "produced": 0,
    "tracks": ["procedural"], "difficulty": "easy", "video_duration": 24,
    "population": 1500, "generations": 30, "budget_seconds": 600,
    "destination": "", "next_run": None, "mode": "draft",
}
DEFAULT_LIMITS = {"memory_mb": 4096, "threads": 2, "disk_gb": 20, "min_free_gb": 1}


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created REAL NOT NULL,
                    config TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    kind TEXT NOT NULL, state TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    error TEXT, destination TEXT NOT NULL DEFAULT '',
                    dedupe_key TEXT UNIQUE
                );
                CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(state, next_attempt, created);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS publications (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, platform TEXT NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL, message TEXT NOT NULL,
                    UNIQUE(run_id, platform)
                );
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", ("schedule", json.dumps(DEFAULT_SCHEDULE)))
            db.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", ("limits", json.dumps(DEFAULT_LIMITS)))

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def get_setting(self, key: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else {}

    def set_setting(self, key: str, value: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))

    def add_run(self, run_id: str, config: dict, created: float | None = None) -> None:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO runs (id, created, config) VALUES (?, ?, ?)",
                       (run_id, created or time.time(), json.dumps(config)))

    def runs(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM runs ORDER BY created DESC").fetchall()
        return [{**dict(row), "config": json.loads(row["config"])} for row in rows]

    def enqueue(self, run_id: str, kind: str = "run", destination: str = "", dedupe_key: str | None = None) -> dict:
        if kind not in {"run", "resume", "render"}:
            raise ValueError("Type de tâche invalide")
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if dedupe_key:
                row = db.execute("SELECT * FROM jobs WHERE dedupe_key=?", (dedupe_key,)).fetchone()
                if row:
                    return dict(row)
            row = db.execute("SELECT * FROM jobs WHERE run_id=? AND state IN ('queued','running','retrying','stopping')", (run_id,)).fetchone()
            if row:
                return dict(row)
            job_id = uuid.uuid4().hex
            db.execute("INSERT INTO jobs(id,run_id,kind,state,created,updated,destination,dedupe_key) VALUES (?,?,?,'queued',?,?,?,?)",
                       (job_id, run_id, kind, now, now, destination, dedupe_key))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def jobs(self, run_id: str | None = None) -> list[dict]:
        with self.connect() as db:
            if run_id:
                rows = db.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY created DESC", (run_id,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 200").fetchall()
        return [dict(row) for row in rows]

    def recover(self) -> int:
        """Mark stale active rows before the worker checks recovery eligibility."""
        with self.connect() as db:
            cursor = db.execute("UPDATE jobs SET state='interrupted', updated=?, error=? WHERE state IN ('running','stopping')",
                                (time.time(), "Application interrompue. Reprendre depuis la dernière génération sauvegardée."))
        return cursor.rowcount

    def retry_interrupted(self, job_id: str, kind: str) -> bool:
        """Keep the same attempt budget and idempotency key across app restarts."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["state"] != "interrupted":
                return False
            if row["attempts"] >= row["max_attempts"]:
                db.execute("UPDATE jobs SET state='failed',error=?,updated=? WHERE id=?",
                           ("Nombre maximal de tentatives atteint après interruption. Reprise manuelle disponible.", time.time(), job_id))
                return False
            delay = min(300, 15 * 2 ** max(0, row["attempts"] - 1))
            db.execute("UPDATE jobs SET state='retrying',kind=?,error=?,updated=?,next_attempt=? WHERE id=?",
                       (kind, "Reprise automatique après interruption ; sauvegarde vérifiée.", time.time(), time.time() + delay, job_id))
            return True

    def claim(self, now: float | None = None) -> dict | None:
        now = now or time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('running','stopping') LIMIT 1").fetchone():
                return None
            row = db.execute("SELECT * FROM jobs WHERE state IN ('queued','retrying') AND next_attempt<=? ORDER BY created LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,updated=? WHERE id=?", (now, row["id"]))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def finish(self, job_id: str, state: str, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?, error=?,updated=? WHERE id=?", (state, error, time.time(), job_id))

    def fail(self, job_id: str, error: str) -> str:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            retry = row["attempts"] < row["max_attempts"]
            state = "retrying" if retry else "failed"
            delay = min(300, 15 * 2 ** max(0, row["attempts"] - 1))
            db.execute("UPDATE jobs SET state=?,error=?,updated=?,next_attempt=? WHERE id=?",
                       (state, error[-2000:], time.time(), time.time() + delay, job_id))
        return state

    def stop(self, run_id: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=CASE WHEN state='running' THEN 'stopping' ELSE 'cancelled' END,updated=? WHERE run_id=? AND state IN ('queued','retrying','running')",
                       (time.time(), run_id))

    def publication(self, run_id: str, platform: str, message: str) -> dict:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO publications VALUES (?,?,?,'manual',?,?)",
                       (uuid.uuid4().hex, run_id, platform, time.time(), message))
            return dict(db.execute("SELECT * FROM publications WHERE run_id=? AND platform=?", (run_id, platform)).fetchone())

    def publications(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM publications ORDER BY created DESC")]
