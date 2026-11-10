"""Per-workspace asset registry (roadmap AD-4): one SQLite file, no service process.

Records every artifact's lifecycle stage, honest provenance class, backend/licence, hashes, dependencies and
evidence, so a generated asset can be found, reused and audited. Stage moves are append-only events.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

STAGES = ("SPEC", "GENERATE", "POSTPROCESS", "VALIDATE", "QUARANTINE", "IMPORT", "ENGINE_VERIFY", "REVIEW",
          "PROMOTE", "REJECTED")
PROVENANCE = ("procedural", "neural", "imported", "human", "native", "codegen",
              "PROC", "NATIVE", "CODEGEN", "EPIC_CONTENT", "LIBRARY", "NEURAL", "HUMAN")
ASSET_TYPES = ("mesh", "skeletal_mesh", "texture", "material", "animation", "sound", "vfx", "sequence",
               "blueprint", "widget", "level", "other")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY, name TEXT NOT NULL, asset_type TEXT NOT NULL, purpose TEXT NOT NULL,
    provenance TEXT NOT NULL, backend TEXT NOT NULL, backend_version TEXT NOT NULL, license TEXT NOT NULL,
    spec_sha256 TEXT NOT NULL, artifact_path TEXT, artifact_sha256 TEXT, unreal_path TEXT,
    stage TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', preview_path TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS asset_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    stage TEXT NOT NULL, ok INTEGER NOT NULL, detail TEXT NOT NULL, evidence TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS asset_deps (
    asset_id TEXT NOT NULL REFERENCES assets(asset_id), depends_on TEXT NOT NULL,
    PRIMARY KEY (asset_id, depends_on));
"""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_spec(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass
class AssetRecord:
    name: str
    asset_type: str
    purpose: str
    provenance: str
    backend: str
    backend_version: str
    license: str
    spec: dict
    tags: list[str] = field(default_factory=list)

    @property
    def asset_id(self) -> str:
        return f"{self.asset_type}:{self.name}:{sha256_spec(self.spec)[:12]}"


class AssetRegistry:
    def __init__(self, workspace: str | Path):
        self.path = Path(workspace) / ".gameforge" / "assets.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        # One short-lived connection per call with WAL mode and lock retry: no handle outlives it, so Windows never sees the file locked.
        for attempt in range(5):
            try:
                db = sqlite3.connect(self.path, timeout=30.0)
                db.row_factory = sqlite3.Row
                try:
                    db.execute("PRAGMA journal_mode = WAL;")
                except sqlite3.OperationalError:
                    pass
                try:
                    db.execute("PRAGMA busy_timeout = 30000;")
                    db.execute("PRAGMA synchronous = NORMAL;")
                except sqlite3.OperationalError:
                    pass
                try:
                    with db:
                        yield db
                    return
                finally:
                    db.close()
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    if attempt == 4:
                        raise
                    time.sleep(0.05 * (attempt + 1))
                else:
                    raise

    def close(self) -> None:
        """Kept for API symmetry; connections are already closed after every call."""

    def register(self, record: AssetRecord) -> str:
        if record.provenance not in PROVENANCE:
            raise ValueError(f"unknown provenance {record.provenance!r}")
        if record.asset_type not in ASSET_TYPES:
            raise ValueError(f"unknown asset type {record.asset_type!r}")
        if not record.license.strip():
            raise ValueError("licence must be recorded")
        now = time.time()
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,'SPEC',?,NULL,?,?)",
                (record.asset_id, record.name, record.asset_type, record.purpose, record.provenance, record.backend,
                 record.backend_version, record.license, sha256_spec(record.spec), ",".join(record.tags), now, now))
        return record.asset_id

    def advance(self, asset_id: str, stage: str, ok: bool, detail: str = "", evidence: list[str] | None = None,
                artifact_path: str | None = None, unreal_path: str | None = None) -> None:
        """Record a lifecycle step. A failed step does not move the asset; PROMOTE needs a passed ENGINE_VERIFY."""
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}")
        row = self.get(asset_id)
        if row is None:
            raise KeyError(asset_id)
        if stage == "PROMOTE" and ok and not self._passed(asset_id, "ENGINE_VERIFY"):
            raise ValueError("cannot promote an asset without a passed ENGINE_VERIFY step")
        now = time.time()
        with self._connect() as db:
            db.execute("INSERT INTO asset_events (asset_id, stage, ok, detail, evidence, at) VALUES (?,?,?,?,?,?)",
                            (asset_id, stage, int(ok), detail, json.dumps(evidence or []), now))
            if artifact_path:
                art_sha = sha256_file(artifact_path) if Path(artifact_path).is_file() else None
                db.execute("UPDATE assets SET artifact_path=?, artifact_sha256=? WHERE asset_id=?",
                                (artifact_path, art_sha, asset_id))
            if unreal_path:
                db.execute("UPDATE assets SET unreal_path=? WHERE asset_id=?", (unreal_path, asset_id))
            if ok:
                db.execute("UPDATE assets SET stage=?, updated_at=? WHERE asset_id=?", (stage, now, asset_id))

    def add_dependency(self, asset_id: str, depends_on: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO asset_deps VALUES (?,?)", (asset_id, depends_on))

    def artifact_unchanged(self, asset_id: str) -> bool:
        """True when the artifact on disk still matches the recorded hash."""
        row = self.get(asset_id)
        if not row or not row["artifact_path"] or not Path(row["artifact_path"]).exists():
            return False
        try:
            return sha256_file(row["artifact_path"]) == row["artifact_sha256"]
        except OSError:
            return False

    def get(self, asset_id: str) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()

    def history(self, asset_id: str) -> list[sqlite3.Row]:
        with self._connect() as db:
            return db.execute("SELECT * FROM asset_events WHERE asset_id=? ORDER BY id", (asset_id,)).fetchall()

    def dependencies(self, asset_id: str) -> list[str]:
        with self._connect() as db:
            return [r[0] for r in db.execute("SELECT depends_on FROM asset_deps WHERE asset_id=?", (asset_id,))]

    def search(self, text: str = "", asset_type: str | None = None, stage: str | None = None) -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM assets WHERE (name LIKE ? OR purpose LIKE ? OR tags LIKE ?)", [f"%{text}%"] * 3
        if asset_type:
            sql, args = sql + " AND asset_type=?", args + [asset_type]
        if stage:
            sql, args = sql + " AND stage=?", args + [stage]
        with self._connect() as db:
            return db.execute(sql + " ORDER BY updated_at DESC", args).fetchall()

    def _passed(self, asset_id: str, stage: str) -> bool:
        with self._connect() as db:
            return db.execute("SELECT 1 FROM asset_events WHERE asset_id=? AND stage=? AND ok=1",
                              (asset_id, stage)).fetchone() is not None
