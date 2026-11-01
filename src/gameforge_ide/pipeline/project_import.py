"""Project import, reverse draft, and GameForge management enablement (WI-8.6).

Safely opens existing Unreal projects in read-only mode:
- Indexes C++ classes, levels, and input actions.
- Generates a reverse draft GameDesignSpec marked with generator="model:import" and extra_checks=["imported: true"].
- Enables GameForge management: copies GameForge plugin into Plugins/GameForge.
- Protects git repository: never commits to user branches. If .git exists, defaults to checkpoints disabled with warning.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ..design.draft import DesignDraft, DraftWin
from ..design.expand import expand_draft
from ..design.gds import GameDesignSpec, Genre, CameraKind, LevelSpec, LayoutKind, Scene, Vec2
from ..forge.project_graph import ProjectGraph
from ..index.indexer import ProjectIndex


class ProjectInspection(BaseModel):
    project_name: str
    project_dir: str
    uproject_path: str
    engine_association: str = ""
    levels: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)
    input_actions: List[str] = Field(default_factory=list)
    is_gameforge_managed: bool = False
    has_git_repo: bool = False
    total_files: int = 0


def inspect_project(project_dir: Path) -> ProjectInspection:
    """Inspect an existing Unreal project folder in read-only mode."""
    p_dir = project_dir.resolve()
    uprojects = list(p_dir.glob("*.uproject"))
    if not uprojects:
        raise FileNotFoundError(f"No .uproject found in {p_dir}")

    uproject = uprojects[0]
    p_name = uproject.stem

    # Read descriptor
    engine_assoc = ""
    try:
        data = json.loads(uproject.read_text(encoding="utf-8"))
        engine_assoc = str(data.get("EngineAssociation", ""))
    except Exception:
        pass

    # Index project (read-only)
    idx = ProjectIndex(p_dir)
    res = idx.index_project()

    # Discover C++ classes
    sym_res = idx.search_symbols("", kind="class", limit=50)
    classes = [r["name"] for r in sym_res.get("results", [])]

    # Discover levels from Content
    levels = []
    content_dir = p_dir / "Content"
    if content_dir.is_dir():
        for root, _, files in os.walk(content_dir):
            for f in files:
                if f.endswith(".umap"):
                    rel = str((Path(root) / f).relative_to(content_dir)).replace("\\", "/")
                    levels.append(rel[:-5])  # strip .umap

    if not levels:
        levels = ["DefaultLevel"]

    # Discover input actions from Config/DefaultInput.ini
    input_actions = []
    input_ini = p_dir / "Config" / "DefaultInput.ini"
    if input_ini.is_file():
        for line in input_ini.read_text(encoding="utf-8", errors="replace").splitlines():
            line_str = line.strip()
            if "ActionMappings=" in line_str or "ActionName=" in line_str:
                parts = line_str.split("ActionName=\"")
                if len(parts) > 1:
                    act_name = parts[1].split("\"")[0]
                    if act_name not in input_actions:
                        input_actions.append(act_name)

    is_managed = (p_dir / "Plugins" / "GameForge").is_dir()
    has_git = (p_dir / ".git").is_dir()

    return ProjectInspection(
        project_name=p_name,
        project_dir=str(p_dir),
        uproject_path=str(uproject),
        engine_association=engine_assoc,
        levels=sorted(levels),
        classes=sorted(classes),
        input_actions=sorted(input_actions),
        is_gameforge_managed=is_managed,
        has_git_repo=has_git,
        total_files=res.get("total_files", 0),
    )


def generate_reverse_draft(
    inspection: ProjectInspection,
    model_caller: Optional[Callable[[str, str], str]] = None,
) -> GameDesignSpec:
    """Synthesize a reverse draft GDS inferred from the indexed project."""
    top_classes = ", ".join(inspection.classes[:5]) if inspection.classes else "Actor"
    pitch = (
        f"Imported Unreal project '{inspection.project_name}' featuring "
        f"{len(inspection.levels)} level(s) and gameplay classes: {top_classes}."
    )

    draft = DesignDraft(
        title=inspection.project_name,
        genre=Genre.ACTION_ADVENTURE,
        camera=CameraKind.THIRD_PERSON,
        pitch=pitch,
        win=[DraftWin(type="reach_goal")],
    )

    gds = expand_draft(draft)

    # Sanitize project name to valid PascalCase (^[A-Z][A-Za-z0-9]{1,30}$)
    raw_pname = re.sub(r"[^A-Za-z0-9]", "", inspection.project_name)[:30]
    if raw_pname and raw_pname[0].isalpha() and len(raw_pname) >= 2:
        clean_pname = raw_pname[0].upper() + raw_pname[1:]
    else:
        clean_pname = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", inspection.project_name) if part)[:30]
        if not clean_pname or not clean_pname[0].isalpha() or len(clean_pname) < 2:
            clean_pname = "ImportedProject"

    data = gds.model_dump()
    data["meta"]["project_name"] = clean_pname
    data["meta"]["title"] = inspection.project_name
    data["meta"]["generator"] = "model:import"

    # Set discovered levels
    if inspection.levels:
        new_levels = []
        for i, lvl_name in enumerate(inspection.levels):
            clean_id = "".join(c if c.isalnum() or c == "_" else "_" for c in lvl_name.lower())[:30]
            if not clean_id or not clean_id[0].isalpha():
                clean_id = f"level_{i+1}"
            new_levels.append(
                {
                    "level_id": clean_id,
                    "layout": "open_world",
                    "size_m": {"x": 100.0, "y": 100.0},
                    "seed": 2026 + i,
                }
            )
        data["scene"] = {
            "levels": new_levels,
            "start_level": new_levels[0]["level_id"],
        }
        for ent in data.get("entities", []):
            ent["level_id"] = new_levels[0]["level_id"]

    # Add extra check marker
    extra_checks = data.setdefault("acceptance", {}).setdefault("extra_checks", [])
    if "imported: true" not in extra_checks:
        extra_checks.append("imported: true")

    return GameDesignSpec.model_validate(data)


def enable_gameforge_management(
    project_dir: Path,
    plugin_source_dir: Optional[Path] = None,
    git_strategy: Literal["disabled", "worktree"] = "disabled",
) -> Dict[str, Any]:
    """Enable GameForge management on an existing project."""
    p_dir = project_dir.resolve()
    target_plugin = p_dir / "Plugins" / "GameForge"
    target_plugin.parent.mkdir(parents=True, exist_ok=True)

    # 1. Copy plugin
    src_plugin = plugin_source_dir or (Path(__file__).resolve().parents[1] / "unreal" / "GameForge")
    if not src_plugin.is_dir():
        try:
            from ..core.settings import get_settings
            s = get_settings()
            if s.plugin_build and s.plugin_build.is_dir():
                src_plugin = s.plugin_build
            elif s.validation_root:
                candidate = s.validation_root / "P3_kittest_20261031" / "Plugins" / "GameForge"
                if candidate.is_dir():
                    src_plugin = candidate
        except Exception:
            pass

    if src_plugin.is_dir() and not target_plugin.is_dir():
        shutil.copytree(src_plugin, target_plugin, ignore=shutil.ignore_patterns("Intermediate", "Binaries"))

    # 2. Checkpoints & Git
    warning = ""
    has_git = (p_dir / ".git").is_dir()
    if has_git:
        if git_strategy == "disabled":
            warning = "Checkpoints disabled: rollback unavailable on external git repository."
        elif git_strategy == "worktree":
            # Set up branch gameforge/checkpoints
            pass
    else:
        # Initialize GameForge git repo
        try:
            import subprocess
            subprocess.run(["git", "init"], cwd=str(p_dir), capture_output=True, check=True)
            (p_dir / ".gitignore").write_text(
                "Binaries/\nIntermediate/\nSaved/\n.vs/\n*.sln\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=str(p_dir), capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit before GameForge management"], cwd=str(p_dir), capture_output=True, check=True)
        except Exception:
            pass

    # 3. Initialize project graph
    graph = ProjectGraph()
    graph.save(p_dir)

    return {
        "ok": True,
        "plugin_installed": target_plugin.is_dir(),
        "git_strategy": git_strategy if has_git else "gameforge_repo",
        "warning": warning,
    }
