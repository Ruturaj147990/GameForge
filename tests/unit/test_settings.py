"""P0 WI-0.2: core/settings.py resolution order and engine discovery."""
import json
from pathlib import Path

import pytest

from src.gameforge_ide.core import settings as S


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for k in ("GAMEFORGE_ENGINE_ROOT", "GAMEFORGE_HOST_PROFILE", "GAMEFORGE_PROJECTS_ROOT", "GAMEFORGE_LAUNCHER_MANIFEST",
              "GAMEFORGE_WORKSPACE", "GAMEFORGE_ARTIFACTS_ROOT", "GAMEFORGE_BRIDGE_PORT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(tmp_path / "user_settings.json"))
    monkeypatch.setenv("GAMEFORGE_SKIP_REGISTRY", "1")
    monkeypatch.setenv("GAMEFORGE_LAUNCHER_MANIFEST", str(tmp_path / "no_manifest.dat"))
    S.reset_settings_cache()
    yield
    S.reset_settings_cache()


def _fake_engine(root: Path) -> Path:
    (root / "Engine/Build").mkdir(parents=True)
    (root / "Engine/Build/Build.version").write_text(json.dumps(
        {"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 4, "Changelist": 123}), encoding="utf-8")
    (root / "Engine/Binaries/Win64").mkdir(parents=True)
    (root / "Engine/Binaries/Win64/UnrealEditor.exe").write_bytes(b"")
    return root


def test_engine_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMEFORGE_ENGINE_ROOT", str(_fake_engine(tmp_path / "UE")))
    s = S.get_settings()
    assert s.engine.version == "5.7.4" and s.engine.source == "env"


def test_engine_from_launcher_manifest(tmp_path, monkeypatch):
    root = _fake_engine(tmp_path / "UE")
    man = tmp_path / "LauncherInstalled.dat"
    man.write_text(json.dumps({"InstallationList": [{"AppName": "UE_5.7", "InstallLocation": str(root)}]}), encoding="utf-8")
    monkeypatch.setenv("GAMEFORGE_LAUNCHER_MANIFEST", str(man))
    s = S.get_settings()
    assert s.engine.root == root and s.engine.source == "launcher"


def test_explicit_non_engine_path_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("GAMEFORGE_ENGINE_ROOT", str(tmp_path / "empty"))
    s = S.get_settings()
    assert s.engine is None
    with pytest.raises(S.EngineNotFoundError):
        _ = s.engine_root


def test_host_profile_values(tmp_path, monkeypatch):
    prof = tmp_path / "hp.json"
    prof.write_text(json.dumps({"probe_project": str(tmp_path / "P.uproject"), "projects_root": str(tmp_path / "proj")}),
                    encoding="utf-8")
    monkeypatch.setenv("GAMEFORGE_HOST_PROFILE", str(prof))
    s = S.get_settings()
    assert s.require_dev("probe_project") == tmp_path / "P.uproject"
    assert s.projects_root == tmp_path / "proj"


def test_require_dev_without_profile_raises():
    with pytest.raises(RuntimeError):
        S.get_settings().require_dev("probe_project")


def test_models_from_routing_file():
    s = S.get_settings()
    assert s.model_for("chat") == "gameforge-qwen3.5-9b:latest"
    assert s.model_for("fast") == "gameforge-qwen3.5-4b:latest"
    with pytest.raises(KeyError):
        s.model_for("nope")
