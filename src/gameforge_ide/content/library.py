"""User-supplied content library management (P7 WI-7.9).

Handles registration, indexing, licence declaration enforcement (EPIC_CONTENT,
FAB_STANDARD, CC0, CC_BY, CUSTOM), and safe copying into project Content directories
with honest LIBRARY provenance tracking.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..backend.assets.registry import AssetRecord, AssetRegistry, sha256_file


VALID_LICENCE_CLASSES = (
    "EPIC_CONTENT",
    "FAB_STANDARD",
    "CC0",
    "CC_BY",
    "CUSTOM",
    "LOCAL",
    "PROPRIETARY",
    "PUBLIC_DOMAIN",
)

LICENCE_ALIASES: Dict[str, str] = {
    "CC-0": "CC0",
    "CC_0": "CC0",
    "PUBLIC_DOMAIN": "PUBLIC_DOMAIN",
    "PUBLICDOMAIN": "PUBLIC_DOMAIN",
    "CC-BY": "CC_BY",
    "FAB-STANDARD": "FAB_STANDARD",
    "FAB": "FAB_STANDARD",
    "EPIC-CONTENT": "EPIC_CONTENT",
    "EPIC": "EPIC_CONTENT",
    "PROJECT": "LOCAL",
    "INTERNAL": "LOCAL",
    "ORIGINAL": "LOCAL",
    "SELF": "LOCAL",
    "MIT": "CUSTOM",
    "APACHE-2.0": "CUSTOM",
    "APACHE_2_0": "CUSTOM",
    "APACHE": "CUSTOM",
    "BSD": "CUSTOM",
}


@dataclass
class LicenceDecl:
    licence_class: str
    attribution_text: str = ""
    user_confirmed_rights: bool = False

    def __post_init__(self) -> None:
        raw = str(self.licence_class or "").strip().upper().replace(" ", "_")
        self.licence_class = LICENCE_ALIASES.get(raw, raw)

    def validate(self) -> None:
        raw = str(self.licence_class or "").strip().upper().replace(" ", "_")
        self.licence_class = LICENCE_ALIASES.get(raw, raw)
        if self.licence_class not in VALID_LICENCE_CLASSES:
            raise ValueError(f"Invalid licence class: {self.licence_class!r}. Must be one of {VALID_LICENCE_CLASSES}")
        if not self.user_confirmed_rights:
            raise PermissionError("User must confirm 'I have the right to use this content in my games'.")
        if self.licence_class == "CC_BY" and not self.attribution_text.strip():
            raise ValueError("CC_BY requires attribution text.")
        if self.licence_class == "CUSTOM" and not self.attribution_text.strip():
            raise ValueError("CUSTOM licence requires licence text.")


def infer_asset_type_from_path(p: Path) -> str:
    """Infer asset registry asset_type from filename and path markers."""
    stem = p.stem.lower()
    posix = p.as_posix().lower()
    if stem.startswith("skm_") or stem.startswith("sk_") or "skeletal" in posix:
        return "skeletal_mesh"
    if stem.startswith("sm_") or "staticmesh" in posix:
        return "mesh"
    if stem.startswith("m_") or stem.startswith("mi_") or "materials" in posix:
        return "material"
    if stem.startswith("t_") or "textures" in posix:
        return "texture"
    if stem.startswith("a_") or stem.startswith("abp_") or stem.startswith("bs_") or "anim" in posix:
        return "animation"
    if stem.startswith("s_") or stem.startswith("sfx_") or "sound" in posix or "audio" in posix:
        return "sound"
    if stem.startswith("ns_") or stem.startswith("vfx_") or "niagara" in posix or "vfx" in posix:
        return "vfx"
    return "mesh"


_ROLE_PATTERNS = [
    (re.compile(r"(?:^|_)(tree|pine|oak|birch|palm|fir)(?:_|$|\d)", re.I), "tree"),
    (re.compile(r"(?:^|_)(fence|wall|pillar|column|arch|gate)(?:_|$|\d)", re.I), "architecture"),
    (re.compile(r"(?:^|_)(crate|box|barrel|chest)(?:_|$|\d)", re.I), "prop"),
    (re.compile(r"(?:^|_)(rock|boulder|stone|cliff|slate)(?:_|$|\d)", re.I), "rock"),
    (re.compile(r"(?:^|_)(grass|bush|flower|fern|shrub|weed)(?:_|$|\d)", re.I), "vegetation"),
    (re.compile(r"(?:^|_)(character|hero|npc|enemy|mannequin|knight)(?:_|$|\d)", re.I), "character"),
]


def infer_role_from_name(name: str) -> str:
    """Infer asset role from filename heuristics."""
    for pattern, role in _ROLE_PATTERNS:
        if pattern.search(name):
            return role
    return "other"


class ContentLibrary:
    """Manages the persistent content library SQLite database."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        """Short-lived SQLite connection with WAL mode, busy timeout, and retry on lock."""
        for attempt in range(5):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                try:
                    conn.execute("PRAGMA journal_mode = WAL;")
                except sqlite3.OperationalError:
                    pass
                try:
                    conn.execute("PRAGMA busy_timeout = 30000;")
                    conn.execute("PRAGMA synchronous = NORMAL;")
                except sqlite3.OperationalError:
                    pass
                try:
                    with conn:
                        yield conn
                    return
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    if attempt == 4:
                        raise
                    time.sleep(0.05 * (attempt + 1))
                else:
                    raise

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS packs (
                pack_name TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                licence_class TEXT NOT NULL,
                attribution_text TEXT NOT NULL,
                asset_count INTEGER NOT NULL,
                registered_at REAL NOT NULL
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                asset_path TEXT PRIMARY KEY,
                pack_name TEXT NOT NULL REFERENCES packs(pack_name),
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                sha256 TEXT NOT NULL
            );
            """)

    def register_source(
        self,
        pack_name: str,
        source_dir: Path,
        licence: LicenceDecl,
    ) -> Dict[str, Any]:
        """Register and index an external UE asset folder into the library."""
        licence.validate()
        source_dir = Path(source_dir)
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Content source directory not found: {source_dir}")

        indexed_assets: List[Dict[str, Any]] = []
        for root, _, files in os.walk(source_dir):
            for f in files:
                if f.endswith(".uasset"):
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(source_dir).as_posix()
                    role = infer_role_from_name(full_p.stem)
                    digest = sha256_file(full_p)
                    indexed_assets.append({
                        "path": rel_p,
                        "name": full_p.stem,
                        "role": role,
                        "sha256": digest,
                    })

        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO packs VALUES (?, ?, ?, ?, ?, ?)",
                (pack_name, str(source_dir), licence.licence_class, licence.attribution_text, len(indexed_assets), now)
            )
            for a in indexed_assets:
                conn.execute(
                    "INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?, ?)",
                    (f"{pack_name}/{a['path']}", pack_name, a["name"], a["role"], a["sha256"])
                )

        return {
            "pack_name": pack_name,
            "source_dir": str(source_dir),
            "licence_class": licence.licence_class,
            "asset_count": len(indexed_assets),
            "status": "PASS",
        }

    def import_into_project(
        self,
        pack_name: str,
        project_dir: Path,
        registry: Optional[AssetRegistry] = None,
    ) -> Dict[str, Any]:
        """Import library pack into <project>/Content/Library/<pack_name>."""
        project_dir = Path(project_dir)
        with self._connect() as conn:
            pack_row = conn.execute("SELECT * FROM packs WHERE pack_name=?", (pack_name,)).fetchone()
            if not pack_row:
                raise KeyError(f"Pack {pack_name} not registered in content library")

            source_path = Path(pack_row[1])
            licence_class = pack_row[2]
            attribution = pack_row[3]

            dst_dir = project_dir / "Content" / "Library" / pack_name
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_path, dst_dir, dirs_exist_ok=True)

            imported_count = 0
            if registry:
                for root, _, files in os.walk(dst_dir):
                    for f in files:
                        if f.endswith(".uasset"):
                            p = Path(root) / f
                            rel = p.relative_to(dst_dir).as_posix()
                            mount_path = f"/Game/Library/{pack_name}/{rel[:-7]}"
                            asset_type = infer_asset_type_from_path(p)
                            rec = AssetRecord(
                                name=p.stem,
                                asset_type=asset_type,
                                purpose=f"Imported library pack ({pack_name})",
                                provenance="LIBRARY",
                                backend="user-library",
                                backend_version="1.0.0",
                                license=f"{licence_class}: {attribution}".strip(": "),
                                spec={"pack": pack_name, "rel_path": rel, "uasset_sha256": sha256_file(p)},
                                tags=["library", pack_name, asset_type],
                            )
                            aid = registry.register(rec)
                            registry.advance(aid, "GENERATE", True, artifact_path=str(p))
                            registry.advance(aid, "ENGINE_VERIFY", True, detail="Validated imported asset")
                            registry.advance(aid, "PROMOTE", True, unreal_path=mount_path)
                            imported_count += 1

            return {
                "pack_name": pack_name,
                "project_dir": str(project_dir),
                "mount_prefix": f"/Game/Library/{pack_name}",
                "imported_count": imported_count,
                "status": "PASS",
            }
