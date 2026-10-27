"""Unit and integration tests for Phase 2 — Verified Unreal Engine Integration.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
1. Unreal 5.7.4 version handshake and feature detection.
2. Security boundary: unauthorized caller mutations strictly rejected.
3. Real actor creation with read-back verification of level membership and properties.
4. Quarantine asset import (/Game/Quarantine/) with class read-back.
5. Blueprint compilation with structured diagnostic read-back.
6. Readiness gates: shader compilation and PIE block mutations.
7. Pre-mutation snapshot recording and hash-verified rollback with conflict detection.
8. Supervisor crash recovery returns typed EDITOR_CRASHED.
"""

from __future__ import annotations

import asyncio
import pytest
from pathlib import Path

from src.gameforge_ide.unreal.mutation_queue import SerializedMutationQueue
from src.gameforge_ide.unreal.operations import UnrealOperationsLibrary
from src.gameforge_ide.unreal.security import EditorSecurityError, UnrealSecurityBoundary
from src.gameforge_ide.unreal.snapshot import SnapshotManager
from src.gameforge_ide.unreal.supervisor import UnrealSupervisor
from src.gameforge_ide.unreal.transport import PythonRemoteTransport


@pytest.fixture
def unreal_env(tmp_path: Path):
    """Sets up an isolated supervisor and unreal workspace environment."""
    workspace = tmp_path / "UnrealProject"
    workspace.mkdir()
    engine_root = Path(r"E:\UE\UE_5.7")
    supervisor = UnrealSupervisor(workspace_root=workspace, engine_root=engine_root)
    return workspace, supervisor


def test_engine_discovery_and_version_handshake(unreal_env):
    """Engine discovery verifies UE 5.7.4 installation and identification handshake."""
    workspace, supervisor = unreal_env
    assert supervisor.check_engine_installed(), "Unreal Engine 5.7.4 expected at E:\\UE\\UE_5.7"

    handshake = supervisor.handshake()
    assert handshake["status"] == "HANDSHAKE_OK"
    assert handshake["engine_version"] == "5.7.4"
    assert handshake["token_verified"] is True
    assert "spawn_actor" in handshake["supported_operations"]
    assert "import_asset" in handshake["supported_operations"]


@pytest.mark.anyio
async def test_unauthorized_mutation_rejected_by_security_boundary(unreal_env):
    """Rule 3 & Blueprint §3: Unauthenticated remote calls must fail closed."""
    workspace, supervisor = unreal_env

    # 1. Missing token
    with pytest.raises(EditorSecurityError) as exc_missing:
        await supervisor.execute_operation(
            "spawn_actor",
            {"actor_class": "PointLight", "location": {"x": 0, "y": 0, "z": 100}},
            token=None,
        )
    assert "without a valid session token" in str(exc_missing.value)

    # 2. Forged / invalid token
    with pytest.raises(EditorSecurityError) as exc_forged:
        await supervisor.execute_operation(
            "spawn_actor",
            {"actor_class": "PointLight", "location": {"x": 0, "y": 0, "z": 100}},
            token="forged_attacker_token_12345",
        )
    assert "Unauthorized editor mutation blocked" in str(exc_forged.value)


@pytest.mark.anyio
async def test_actor_creation_mutation_and_genuine_readback(unreal_env):
    """Rule 7: Spawning an actor must be verified by actual level and actor query read-back."""
    workspace, supervisor = unreal_env
    token = supervisor.get_session_token()

    # Spawn actor
    loc = {"x": 150.0, "y": 200.0, "z": 50.0}
    res = await supervisor.execute_operation(
        "spawn_actor",
        {
            "actor_class": "StaticMeshActor",
            "location": loc,
            "label": "SM_HeroCrate_01",
            "level_path": "/Game/Maps/TestArena",
        },
        token=token,
    )
    assert res["ok"] is True
    assert res["data"]["actor_label"] == "SM_HeroCrate_01"

    # Read-back 1: Query actors in level
    actors = supervisor.operations.actors_in_level("/Game/Maps/TestArena")
    assert len(actors) == 1
    hero = actors[0]
    assert hero["label"] == "SM_HeroCrate_01"
    assert hero["class"] == "StaticMeshActor"
    assert hero["location"] == loc

    # Read-back 2: Verify non-existent level returns empty
    assert len(supervisor.operations.actors_in_level("/Game/Maps/EmptyLevel")) == 0


@pytest.mark.anyio
async def test_quarantine_asset_import_and_readback(unreal_env):
    """Imported assets stage in quarantine path (/Game/Quarantine/) with class validation."""
    workspace, supervisor = unreal_env
    token = supervisor.get_session_token()

    # Create dummy source asset on disk
    src_mesh = workspace / "raw_prop.obj"
    src_mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")

    res = await supervisor.execute_operation(
        "import_asset",
        {
            "source_file": "raw_prop.obj",
            "destination_path": "/Game/Quarantine/Props",
            "asset_class": "StaticMesh",
        },
        token=token,
    )
    assert res["ok"] is True
    assert res["reversibility"] == "snapshot-only"

    target_path = "/Game/Quarantine/Props/raw_prop"
    # Genuine read-back
    exists_res = supervisor.operations.asset_exists(target_path, "StaticMesh")
    assert exists_res["exists"] is True
    assert exists_res["class_match"] is True

    # Negative check
    neg = supervisor.operations.asset_exists("/Game/Props/NonExistent")
    assert neg["exists"] is False


@pytest.mark.anyio
async def test_blueprint_compilation_and_readback(unreal_env):
    """Blueprint compilation yields structured compiler diagnostics."""
    workspace, supervisor = unreal_env
    token = supervisor.get_session_token()

    res = await supervisor.execute_operation(
        "compile_blueprint",
        {"blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"},
        token=token,
    )
    assert res["ok"] is True

    # Read-back
    comp_readback = supervisor.operations.compile_blueprint_result("/Game/Blueprints/BP_PlayerCharacter")
    assert comp_readback["status"] == "COMPILED"
    assert comp_readback["errors_count"] == 0


@pytest.mark.anyio
async def test_editor_readiness_gate_blocks_during_shaders_and_pie(unreal_env):
    """Readiness gate: mutation queue blocks execution when shaders are compiling or in PIE."""
    workspace, supervisor = unreal_env
    token = supervisor.get_session_token()

    # 1. Simulate shader compilation
    supervisor.queue.set_readiness(compiling_shaders=True)
    res_shader = await supervisor.execute_operation(
        "spawn_actor",
        {"actor_class": "CameraActor", "location": {"x": 0, "y": 0, "z": 0}},
        token=token,
    )
    assert res_shader["ok"] is False
    assert "compiling shaders" in res_shader["error"]

    # 2. Simulate PIE active
    supervisor.queue.set_readiness(in_pie=True)
    res_pie = await supervisor.execute_operation(
        "spawn_actor",
        {"actor_class": "CameraActor", "location": {"x": 0, "y": 0, "z": 0}},
        token=token,
    )
    assert res_pie["ok"] is False
    assert "Play-In-Editor (PIE)" in res_pie["error"]

    # 3. Restore idle readiness
    supervisor.queue.set_readiness()
    res_ready = await supervisor.execute_operation(
        "spawn_actor",
        {"actor_class": "CameraActor", "location": {"x": 0, "y": 0, "z": 0}},
        token=token,
    )
    assert res_ready["ok"] is True


def test_snapshot_pre_post_and_safe_rollback_conflict(unreal_env):
    """Snapshot rollback restores pre-mutation bytes and detects user conflict."""
    workspace, supervisor = unreal_env
    snap_mgr = supervisor.snapshots

    asset_file = workspace / "Game" / "Props" / "Chest.uasset"
    asset_file.parent.mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(b"INITIAL_CHEST_V1_BYTES")

    rel_path = "Game/Props/Chest.uasset"

    # Step 1: Pre-snapshot
    snap_id = snap_mgr.create_pre_snapshot("edit_chest", [rel_path])

    # Step 2: Mutation
    asset_file.write_bytes(b"MUTATED_CHEST_V2_BYTES")
    snap_mgr.commit_post_state(snap_id)

    # Step 3: Independent modification by user
    asset_file.write_bytes(b"INDEPENDENT_USER_V3_BYTES")

    # Step 4: Attempt rollback — must detect CONFLICT and refuse to overwrite
    res_conflict = snap_mgr.rollback(snap_id)
    assert res_conflict["status"] == "CONFLICT"
    assert "Modified independently" in res_conflict["conflicts"][0]
    assert asset_file.read_bytes() == b"INDEPENDENT_USER_V3_BYTES"


def test_supervisor_simulated_crash_recovery(unreal_env):
    """Crash recovery restores pre-task snapshot and returns typed EDITOR_CRASHED."""
    workspace, supervisor = unreal_env
    snap_mgr = supervisor.snapshots

    config_file = workspace / "Config" / "Editor.ini"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("[Editor]\nVersion=5.7.4", encoding="utf-8")

    rel_path = "Config/Editor.ini"
    snap_id = snap_mgr.create_pre_snapshot("update_config", [rel_path])

    # Mutate
    config_file.write_text("[Editor]\nCORRUPTED_DURING_CRASH", encoding="utf-8")
    snap_mgr.commit_post_state(snap_id)

    # Crash occurs
    crash_report = supervisor.handle_simulated_crash(snap_id)
    assert crash_report["status"] == "EDITOR_CRASHED"
    assert crash_report["rollback_result"]["status"] == "RESTORED"

    # Verified clean restoration
    assert config_file.read_text(encoding="utf-8") == "[Editor]\nVersion=5.7.4"
