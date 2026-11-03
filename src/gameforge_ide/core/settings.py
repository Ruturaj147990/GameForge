"""Single source of truth for paths, engine location, model defaults and host-profile values (AD-15).

Resolution order for every value (first hit wins):
  1. environment variables GAMEFORGE_* (CI, tests, scripts)
  2. the user settings file %APPDATA%\\GameForge\\settings.json (written by the Settings view in P4)
  3. the host profile JSON named by GAMEFORGE_HOST_PROFILE or settings.json "host_profile" (developer machines)
  4. discovery (engine: Epic launcher manifest, then the registry) or a product default

No other module may contain a host path literal; tests/unit/test_no_host_paths.py enforces this.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

PACKAGE_ROOT = Path(__file__).resolve().parents[1]          # src/gameforge_ide
REPO_ROOT = PACKAGE_ROOT.parents[1]                          # repository root (source checkouts only, dev-only)
PINNED_ENGINE = "5.7"
DEFAULT_BRIDGE_PORT = 47815
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
MODEL_ROUTING_FILE = PACKAGE_ROOT / "config" / "model_routing.json"


def get_ops_root() -> Path:
    """Path to bundled gameforge_ops Content package under PACKAGE_ROOT."""
    return PACKAGE_ROOT / "unreal" / "GameForge" / "Content" / "Python" / "gameforge_ops"


def get_plugin_root() -> Path:
    """Path to bundled Unreal plugin package under PACKAGE_ROOT."""
    return PACKAGE_ROOT / "unreal" / "GameForge"



class EngineNotFoundError(RuntimeError):
    """Raised when an operation needs Unreal Engine and none is configured or discoverable."""


@dataclass(frozen=True)
class EngineInstall:
    root: Path
    version: str          # "5.7.4"
    changelist: int
    source: str           # "env" | "settings" | "host_profile" | "launcher" | "registry"


@dataclass(frozen=True)
class Settings:
    engine: Optional[EngineInstall]
    projects_root: Path
    artifacts_root: Path
    default_workspace: Path
    ollama_url: str
    bridge_port: int
    models: Dict[str, str]
    validation_root: Optional[Path] = None   # developer hosts only
    probe_project: Optional[Path] = None     # developer hosts only
    plugin_build: Optional[Path] = None      # developer hosts only
    host_profile: Dict[str, Any] = field(default_factory=dict)
    host_profile_path: Optional[Path] = None
    engine_channel: str = "pinned"  # "pinned" (5.7.4) | "next" (5.8)

    @property
    def engine_root(self) -> Path:
        if self.engine is None:
            raise EngineNotFoundError(
                f"Unreal Engine {PINNED_ENGINE} was not found. Set it in Settings or GAMEFORGE_ENGINE_ROOT.")
        return self.engine.root

    def model_for(self, role: str) -> str:
        if role not in self.models:
            raise KeyError(f"no model configured for role {role!r}; known roles: {sorted(self.models)}")
        return self.models[role]

    def require_dev(self, name: str) -> Path:
        value = getattr(self, name)
        if value is None:
            raise RuntimeError(f"{name} is only available on a developer host profile (GAMEFORGE_HOST_PROFILE)")
        return value


def _read_json(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def user_settings_path() -> Optional[Path]:
    override = os.environ.get("GAMEFORGE_USER_SETTINGS")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "GameForge" / "settings.json" if appdata else None


def engine_version(root: Path) -> Optional[tuple[str, int]]:
    """(``"5.7.4"``, changelist) from ``Engine/Build/Build.version``, or None if this is not an engine root."""
    data = _read_json(root / "Engine" / "Build" / "Build.version")
    try:
        return f"{data['MajorVersion']}.{data['MinorVersion']}.{data['PatchVersion']}", int(data.get("Changelist", 0))
    except KeyError:
        return None


def _install(root: Path, source: str) -> Optional[EngineInstall]:
    ver = engine_version(root)
    if ver is None or not (root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe").is_file():
        return None
    return EngineInstall(root=root, version=ver[0], changelist=ver[1], source=source)


def discover_engines() -> List[EngineInstall]:
    """Installed engines: Epic launcher manifests (*.item and dat), registry, and drive scanning. Only verified roots are returned."""
    found: List[EngineInstall] = []

    # 1. Check custom launcher manifest override (for tests/custom environments)
    manifest = os.environ.get("GAMEFORGE_LAUNCHER_MANIFEST")
    if manifest:
        for item in _read_json(Path(manifest)).get("InstallationList", []):
            if str(item.get("AppName", "")).startswith("UE_") and item.get("InstallLocation"):
                inst = _install(Path(item["InstallLocation"]), "launcher")
                if inst and all(i.root != inst.root for i in found):
                    found.append(inst)
        return found

    # 2. Comprehensive multi-source Unreal Engine discovery
    try:
        from ..unreal.discovery import discover_all_engines
        discovered = discover_all_engines(pinned_minor=PINNED_ENGINE)
        for d in discovered:
            if all(i.root != d.root for i in found):
                found.append(EngineInstall(root=d.root, version=d.version, changelist=d.changelist, source=d.source))
    except Exception:
        # Fall back to standard discovery if discovery module encounters an error
        if not manifest and os.environ.get("PROGRAMDATA"):
            manifest = str(Path(os.environ["PROGRAMDATA"]) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat")
            for item in _read_json(Path(manifest) if manifest else None).get("InstallationList", []):
                if str(item.get("AppName", "")).startswith("UE_") and item.get("InstallLocation"):
                    inst = _install(Path(item["InstallLocation"]), "launcher")
                    if inst and all(i.root != inst.root for i in found):
                        found.append(inst)
        if not os.environ.get("GAMEFORGE_SKIP_REGISTRY"):
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine") as base:
                    for i in range(winreg.QueryInfoKey(base)[0]):
                        with winreg.OpenKey(base, winreg.EnumKey(base, i)) as key:
                            inst = _install(Path(winreg.QueryValueEx(key, "InstalledDirectory")[0]), "registry")
                            if inst and all(x.root != inst.root for x in found):
                                found.append(inst)
            except OSError:
                pass

    return found


def _pick_engine(explicit: Optional[str], source: str) -> Optional[EngineInstall]:
    if explicit:
        return _install(Path(explicit), source)  # an explicit path that is not an engine resolves to None (fail closed)
    pinned = [e for e in discover_engines() if e.version.startswith(PINNED_ENGINE + ".")]
    return max(pinned, key=lambda e: e.changelist) if pinned else None


def _path(value: Any) -> Optional[Path]:
    return Path(str(value)) if value else None


def _load_models() -> Dict[str, str]:
    data = _read_json(MODEL_ROUTING_FILE)
    roles = data.get("roles", {})
    return {str(k): str(v) for k, v in roles.items()} if isinstance(roles, dict) else {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    user = _read_json(user_settings_path())
    profile_path = _path(os.environ.get("GAMEFORGE_HOST_PROFILE") or user.get("host_profile"))
    profile = _read_json(profile_path)

    def pick(env: str, key: str) -> Optional[Any]:
        return os.environ.get(env) or user.get(key) or profile.get(key)

    engine_explicit = pick("GAMEFORGE_ENGINE_ROOT", "engine_root")
    engine_source = ("env" if os.environ.get("GAMEFORGE_ENGINE_ROOT") else
                     "settings" if user.get("engine_root") else "host_profile")
    home = Path.home()
    models = _load_models()
    models.update({str(k): str(v) for k, v in (user.get("models") or {}).items()})
    return Settings(
        engine=_pick_engine(engine_explicit, engine_source),
        projects_root=_path(pick("GAMEFORGE_PROJECTS_ROOT", "projects_root")) or home / "Documents" / "GameForge" / "Projects",
        artifacts_root=_path(pick("GAMEFORGE_ARTIFACTS_ROOT", "artifacts_root")) or home / "Documents" / "GameForge",
        default_workspace=_path(pick("GAMEFORGE_WORKSPACE", "default_workspace")) or home / "Documents" / "GameForge",
        ollama_url=str(pick("GAMEFORGE_OLLAMA_URL", "ollama_url") or DEFAULT_OLLAMA_URL),
        bridge_port=int(pick("GAMEFORGE_BRIDGE_PORT", "bridge_port") or DEFAULT_BRIDGE_PORT),
        models=models,
        validation_root=_path(profile.get("validation_root")),
        probe_project=_path(profile.get("probe_project")),
        plugin_build=_path(profile.get("plugin_build")),
        host_profile=profile,
        host_profile_path=profile_path if profile else None,
        engine_channel=str(pick("GAMEFORGE_ENGINE_CHANNEL", "engine_channel") or "pinned"),
    )


def reset_settings_cache() -> None:
    """Tests and the Settings view call this after changing the environment or settings.json."""
    get_settings.cache_clear()


MISSING_ENGINE = Path("UNREAL_ENGINE_NOT_CONFIGURED")


def engine_root_or_missing() -> Path:
    """Engine root for constructors that must not raise; a missing engine fails later in tool checks."""
    s = get_settings()
    return s.engine.root if s.engine is not None else MISSING_ENGINE


def artifacts_dir(*parts: str) -> Path:
    return get_settings().artifacts_root.joinpath(*parts)
