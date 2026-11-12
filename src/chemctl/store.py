import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid4().hex[:16]}"


class Store:
    """One connection per operation; the API worker and GUI never share connections."""

    def __init__(self, home: Path):
        home.mkdir(parents=True, exist_ok=True)
        self.path = home / "chemctl.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                    updated_at TEXT NOT NULL, PRIMARY KEY(kind,id)
                );
                CREATE INDEX IF NOT EXISTS record_kind ON records(kind,updated_at);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, at TEXT NOT NULL,
                    action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL
                );
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.row_factory = sqlite3.Row
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind, key, body):
        with self.connect() as db:
            db.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
                       (kind, key, json.dumps(body, ensure_ascii=False, allow_nan=False), now()))
        return body

    def get(self, kind, key):
        with self.connect() as db:
            row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind, limit=50, offset=0, filters=None):
        clause, args = "kind=?", [kind]
        # Filter keys are chosen by the service, never interpolated from API input.
        for field, value in (filters or {}).items():
            if value is not None:
                clause += " AND json_extract(body, ?) = ?"
                args.extend([f"$.{field}", value])
        with self.connect() as db:
            total = db.execute(f"SELECT count(*) FROM records WHERE {clause}", args).fetchone()[0]
            rows = db.execute(f"SELECT body FROM records WHERE {clause} ORDER BY updated_at DESC LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        return {"items": [json.loads(r[0]) for r in rows], "total": total, "limit": limit, "offset": offset}

    def audit(self, action, target, detail=None):
        with self.connect() as db:
            db.execute("INSERT INTO audit(at,action,target,detail) VALUES(?,?,?,?)", (now(), action, target, json.dumps(detail or {}, ensure_ascii=False)))

    def events(self, target, limit=100):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM audit WHERE target=? ORDER BY id DESC LIMIT ?", (target, limit)).fetchall()
        return [dict(r) for r in rows]

    def backup(self, target):
        dest = sqlite3.connect(target)
        try:
            with self.connect() as source:
                source.backup(dest)
        finally:
            dest.close()
