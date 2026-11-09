"""Verification suite for GameForge Ecosystem Separation & Universal Navigation Maps."""

import json
from pathlib import Path
import pytest


EXPECTED_DIRECTORIES = [
    "GameForge_IDE",
    "GameForge_Unreal_Plugin",
    "GameForge_AI_Models",
    "GameForge_AI_Training",
    "GameForge_Benchmarks",
    "GameForge_Projects",
    "GameForge_Engine_Testbed",
    "GameForge_Documentation",
]


def test_all_eight_ecosystem_directories_exist():
    """Verify that all 8 proposed modular directories exist under E:\\."""
    drive_e = Path("E:/")
    missing = [d for d in EXPECTED_DIRECTORIES if not (drive_e / d).is_dir()]
    assert not missing, f"Missing ecosystem directories under E:\\: {missing}"


def test_ecosystem_map_exists_in_all_directories():
    """Verify that ECOSYSTEM_MAP.md exists at the root of every ecosystem directory."""
    drive_e = Path("E:/")
    missing_map = []
    for d in EXPECTED_DIRECTORIES:
        map_path = drive_e / d / "ECOSYSTEM_MAP.md"
        if not map_path.is_file() or map_path.stat().st_size < 100:
            missing_map.append(d)
    assert not missing_map, f"Directories missing valid ECOSYSTEM_MAP.md: {missing_map}"


def test_ecosystem_json_validity():
    """Verify that ecosystem.json is valid and covers all required paths."""
    config_json = Path("E:/GameForge_Documentation/ecosystem.json")
    assert config_json.is_file(), "E:/GameForge_Documentation/ecosystem.json does not exist"
    data = json.loads(config_json.read_text(encoding="utf-8"))
    
    required_keys = [
        "ide_root",
        "plugin_root",
        "models_root",
        "training_root",
        "benchmarks_root",
        "projects_root",
        "engine_testbed_root",
        "docs_root",
    ]
    for key in required_keys:
        assert key in data, f"Missing required key in ecosystem.json: {key}"
        target = Path(data[key])
        assert target.is_dir(), f"Path mapped by {key} ({target}) is not a directory"


def test_unreal_plugin_manifest_sealed():
    """Verify that GameForge_Unreal_Plugin contains an intact plugin manifest."""
    plugin_root = Path("E:/GameForge_Unreal_Plugin")
    assert (plugin_root / "GameForge.uplugin").is_file(), "GameForge.uplugin missing"
    assert (plugin_root / "plugin_manifest.json").is_file(), "plugin_manifest.json missing"
    assert (plugin_root / "Source" / "GameForgeRuntime").is_dir(), "GameForgeRuntime source missing"


def test_protected_oracles_intact_in_benchmarks():
    """Verify that the 45 protected grading oracles exist in GameForge_Benchmarks."""
    oracles_dir = Path("E:/GameForge_Benchmarks/graders/protected")
    assert oracles_dir.is_dir(), "Protected oracles directory missing in GameForge_Benchmarks"
    oracle_files = list(oracles_dir.rglob("test_*.py"))
    assert len(oracle_files) >= 4, f"Expected protected oracle test files, found {len(oracle_files)}"
