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
import threading
from typing import Any, Dict, List, Optional

PACKAGE_ROOT = Path(__file__).resolve().parents[1]          # src/gameforge_ide
REPO_ROOT = PACKAGE_ROOT.parents[1]                          # repository root (source checkouts only, dev-only)
PINNED_ENGINE = "5.7"
NEXT_ENGINE = "5.8"
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
    default_task_mode: str = "planning"  # "planning" | "fast"
    default_autonomy_profile: str = "agentic"  # "manual" | "auto_edit" | "agentic"

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
    if path is None:
        return {}
    p = Path(path)
    if not p.is_file():
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.is_file():
            try:
                data = json.loads(bak.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.is_file():
            try:
                data = json.loads(bak.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    try:
                        p.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
                    except Exception:
                        pass
                    return data
            except Exception:
                pass
    return {}


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


def discover_engines(target_minor: str = PINNED_ENGINE) -> List[EngineInstall]:
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
        discovered = discover_all_engines(pinned_minor=target_minor)
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


def _pick_engine(explicit: Optional[str], source: str, channel: str = "pinned") -> Optional[EngineInstall]:
    if explicit:
        return _install(Path(explicit), source)  # an explicit path that is not an engine resolves to None (fail closed)
    target_minor = NEXT_ENGINE if channel == "next" else PINNED_ENGINE
    engines = discover_engines(target_minor=target_minor)
    matching = [e for e in engines if e.version.startswith(target_minor + ".")]
    if matching:
        return max(matching, key=lambda e: e.changelist)
    if channel == "next":
        # Fall back gracefully to pinned engine if next engine is not installed
        pinned = [e for e in engines if e.version.startswith(PINNED_ENGINE + ".")]
        if pinned:
            return max(pinned, key=lambda e: e.changelist)
    return None


def resolve_host_profile_path(raw: Optional[Any]) -> Optional[Path]:
    """Resolve a host profile path or name across CWD, REPO_ROOT configs, and PACKAGE_ROOT config."""
    if not raw:
        return None
    p = Path(str(raw))
    if p.is_file():
        return p.resolve()
    # Check relative to REPO_ROOT
    if REPO_ROOT and REPO_ROOT.is_dir():
        cand = REPO_ROOT / p
        if cand.is_file():
            return cand.resolve()
        cand = REPO_ROOT / "configs" / "host_profiles" / p
        if cand.is_file():
            return cand.resolve()
        if not p.name.endswith(".json"):
            cand = REPO_ROOT / "configs" / "host_profiles" / f"{p.name}.json"
            if cand.is_file():
                return cand.resolve()
    # Check relative to PACKAGE_ROOT
    cand = PACKAGE_ROOT / "config" / p
    if cand.is_file():
        return cand.resolve()
    return None


def _path(value: Any) -> Optional[Path]:
    return Path(str(value)) if value else None


def _load_models() -> Dict[str, str]:
    data = _read_json(MODEL_ROUTING_FILE)
    roles = data.get("roles", {})
    return {str(k): str(v) for k, v in roles.items()} if isinstance(roles, dict) else {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    user = _read_json(user_settings_path())
    raw_profile = os.environ.get("GAMEFORGE_HOST_PROFILE") or user.get("host_profile")
    profile_path = resolve_host_profile_path(raw_profile)
    profile = _read_json(profile_path)

    def pick(env: str, key: str) -> Optional[Any]:
        return os.environ.get(env) or user.get(key) or profile.get(key)

    channel = str(pick("GAMEFORGE_ENGINE_CHANNEL", "engine_channel") or "pinned")
    engine_explicit = pick("GAMEFORGE_ENGINE_ROOT", "engine_root")
    engine_source = ("env" if os.environ.get("GAMEFORGE_ENGINE_ROOT") else
                     "settings" if user.get("engine_root") else "host_profile")
    home = Path.home()
    models = _load_models()
    if isinstance(profile.get("models"), dict):
        models.update({str(k): str(v) for k, v in profile["models"].items()})
    if isinstance(user.get("models"), dict):
        models.update({str(k): str(v) for k, v in user["models"].items()})

    return Settings(
        engine=_pick_engine(engine_explicit, engine_source, channel=channel),
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
        engine_channel=channel,
        default_task_mode=str(pick("GAMEFORGE_TASK_MODE", "default_task_mode") or "planning"),
        default_autonomy_profile=str(pick("GAMEFORGE_AUTONOMY_PROFILE", "default_autonomy_profile") or "agentic"),
    )


_SETTINGS_LOCK = threading.Lock()

# DEF-133 FIX: Thread-safe initialisation guard for get_settings().
# lru_cache is NOT thread-safe during initial population: multiple threads can
# enter the function body simultaneously before the cache entry is set.
# In tests, 4 gameforge-job threads concurrently instantiate CapabilityRegistry,
# each calling get_settings() → scan_filesystem_drives() → glob.scandir(), causing
# a Windows fatal access violation.  We use double-checked locking to serialize
# only the first (expensive) computation; subsequent calls hit the lru_cache.
_GET_SETTINGS_INIT_LOCK = threading.Lock()
_settings_initialized = False


def get_settings_safe() -> "Settings":
    """Thread-safe entry point: delegates to get_settings() with init-time serialization."""
    global _settings_initialized
    if _settings_initialized:
        return get_settings()          # fast-path: cache is warm, no lock needed
    with _GET_SETTINGS_INIT_LOCK:
        if not _settings_initialized:  # double-checked locking
            result = get_settings()
            _settings_initialized = True
            return result
        return get_settings()


def save_user_settings(data: Dict[str, Any]) -> Path:
    """Atomically and safely persist user settings to %APPDATA%/GameForge/settings.json.
    
    Uses thread-safe locking, two-phase atomic write, automatic .bak backup,
    fsync durability, Windows NTFS lock retries, and cache invalidation.
    """
    with _SETTINGS_LOCK:
        cfg_path = user_settings_path()
        if not cfg_path:
            raise RuntimeError("User settings path could not be determined; APPDATA is not set.")

        cfg_path = Path(cfg_path).resolve()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        existing: Dict[str, Any] = _read_json(cfg_path)
        existing.update(data)

        from ..storage.atomic import atomic_write_json
        atomic_write_json(cfg_path, existing, indent=2, sync=True, backup=True)
        reset_settings_cache()
        return cfg_path


def reset_settings_cache() -> None:
    """Tests and the Settings view call this after changing the environment or settings.json."""
    global _settings_initialized
    get_settings.cache_clear()
    _settings_initialized = False
    # Also invalidate the engine discovery cache so the next get_settings() call
    # re-discovers engines (e.g. after the user changes engine_root in tests).
    try:
        from ..unreal.discovery import invalidate_discovery_cache
        invalidate_discovery_cache()
    except Exception:
        pass


MISSING_ENGINE = Path("UNREAL_ENGINE_NOT_CONFIGURED")


def engine_root_or_missing() -> Path:
    """Engine root for constructors that must not raise; a missing engine fails later in tool checks."""
    s = get_settings()
    return s.engine.root if s.engine is not None else MISSING_ENGINE


def artifacts_dir(*parts: str) -> Path:
    return get_settings().artifacts_root.joinpath(*parts)
