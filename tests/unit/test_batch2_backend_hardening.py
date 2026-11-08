"""Unit tests verifying Batch 2 backend hardening fixes."""
import hashlib
import json
import pytest
from pathlib import Path

from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.agent.task_state import TaskState, TaskAcceptancePredicate
from src.gameforge_ide.backend.agent.repair_system import RepairEngine, RootCause
from src.gameforge_ide.backend.security.boundary import BoundaryManager, SecurityViolationError
from src.gameforge_ide.index.indexer import ProjectIndex
from src.gameforge_ide.storage.atomic import atomic_write_text


def test_session_manager_tuple_and_bak_deletion(tmp_path: Path):
    sm = SessionManager(tmp_path)
    sess = sm.create_session("TestSess")
    sess_id = sess.session_id

    # Verify session file exists
    primary = tmp_path / ".gameforge" / "sessions" / f"{sess_id}.json"
    bak = primary.with_suffix(".json.bak")
    assert primary.is_file()

    # Create backup sidecar
    atomic_write_text(primary, json.dumps(sess.model_dump()), backup=True)
    assert bak.is_file()

    # Corrupt primary
    primary.write_text("{CORRUPTED_JSON", encoding="utf-8")

    # Read through get_session -> should recover from bak
    loaded = sm.get_session(sess_id)
    assert loaded is not None
    assert loaded.session_id == sess_id

    # Delete session -> must delete both primary and .bak
    res = sm.delete_session(sess_id)
    assert res is True
    assert not primary.exists()
    assert not bak.exists()
    assert sm.get_session(sess_id) is None


def test_task_state_file_changed_predicate(tmp_path: Path):
    target_file = tmp_path / "Source" / "MyGame" / "MyActor.cpp"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("// initial content", encoding="utf-8")
    init_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

    # Case 1: Propose edit without application -> MUST NOT satisfy file_changed
    ts = TaskState(
        task_id="t1",
        session_id="s1",
        user_prompt="Add jump",
        goal="Add jump to MyActor",
        acceptance=[
            TaskAcceptancePredicate(
                predicate_type="file_changed",
                target="Source/MyGame/MyActor.cpp",
            )
        ],
    )
    all_sat, unmet = ts.evaluate_acceptance(
        workspace_root=tmp_path,
        tool_history=[
            {"tool_name": "propose_edit", "status": "PENDING_APPROVAL", "arguments": {"path": "Source/MyGame/MyActor.cpp"}}
        ],
        modified_files=set(),
    )
    assert not all_sat
    assert len(unmet) == 1
    assert not ts.acceptance[0].satisfied

    # Case 2: Content actually changed on disk and matched post hash
    new_content = "// modified content with jump"
    target_file.write_text(new_content, encoding="utf-8")
    new_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

    all_sat2, unmet2 = ts.evaluate_acceptance(
        workspace_root=tmp_path,
        tool_history=[
            {
                "tool_name": "write_file",
                "status": "APPLIED",
                "output": {
                    "file_path": "Source/MyGame/MyActor.cpp",
                    "original_sha256": init_hash,
                    "new_sha256": new_hash,
                },
            }
        ],
        modified_files={Path("Source/MyGame/MyActor.cpp")},
    )
    assert all_sat2
    assert len(unmet2) == 0
    assert ts.acceptance[0].satisfied


def test_repair_engine_signature_lookup(tmp_path: Path):
    engine = RepairEngine(tmp_path)
    rc1 = RootCause(
        cause_id="error_c1083",
        signature="c1083:CoreMinimal.h",
        category="code_defect",
        primary_file="Source/MyGame/MyActor.cpp",
        summary="Cannot open include file CoreMinimal.h",
        description="Cannot open include file CoreMinimal.h",
    )
    # Record attempt
    engine.record_attempt(rc1, diff_text="// fix include", modified_files=["Source/MyGame/MyActor.cpp"], result_status="failed", diag_count_before=1, diag_count_after=1)
    assert engine.attempt_counts.get(rc1.signature, 0) == 1
    # Different cause_id but same signature
    rc1_dup = RootCause(
        cause_id="error_different_id",
        signature="c1083:CoreMinimal.h",
        category="code_defect",
        primary_file="Source/MyGame/MyActor.cpp",
        summary="Different error ID same signature",
        description="Different error ID same signature",
    )
    assert engine.attempt_counts.get(rc1_dup.signature, 0) == 1


def test_boundary_protected_patterns(tmp_path: Path):
    bm = BoundaryManager(tmp_path)

    # Protected paths should fail on write
    with pytest.raises(SecurityViolationError):
        bm.validate_path(".gameforge/egress.json", allow_write=True)
    with pytest.raises(SecurityViolationError):
        bm.validate_path(".gameforge/spend.jsonl", allow_write=True)
    with pytest.raises(SecurityViolationError):
        bm.validate_path(".gameforge/tasks/task_123.json", allow_write=True)
    with pytest.raises(SecurityViolationError):
        bm.validate_path("graders/protected/test.py", allow_write=True)

    # Allowed cache / index paths
    p_cache = bm.validate_path(".gameforge/cache/temp.txt", allow_write=True)
    assert p_cache is not None
    p_src = bm.validate_path("Source/MyActor.cpp", allow_write=True)
    assert p_src is not None


def test_indexer_json_deps(tmp_path: Path):
    proj_dir = tmp_path / "MyProject"
    proj_dir.mkdir(parents=True, exist_ok=True)
    idx = ProjectIndex(proj_dir)

    assets = [
        {
            "path": "/Game/Environment/Tree_01",
            "class": "StaticMesh",
            "dependencies": ["/Game/Materials/M_Wood", "/Game/Textures/T_Bark_D"],
        }
    ]
    count = idx.index_assets(assets)
    assert count == 1

    # Query raw DB to verify json serialization
    conn = idx._get_connection()
    cur = conn.execute("SELECT deps_json FROM assets WHERE path = ?", ("/Game/Environment/Tree_01",))
    row = cur.fetchone()
    assert row is not None
    deps_raw = row[0]
    parsed = json.loads(deps_raw)
    assert isinstance(parsed, list)
    assert "/Game/Materials/M_Wood" in parsed


def test_character_generator_arm_cylinders(tmp_path: Path):
    from src.gameforge_ide.backend.models.character_spec import CharacterSpec
    from src.gameforge_ide.backend.tools.character_generator import ProceduralSkinnedCharacterGenerator

    spec = CharacterSpec(
        character_id="char_test_arm",
        name="ArmTestHero",
        purpose="Player Avatar",
        category="humanoid",
        height_cm=180.0,
        triangle_budget=30000,
        target_territory="GLOBAL",
    )
    gen = ProceduralSkinnedCharacterGenerator(output_dir=tmp_path)
    bundle = gen.generate_humanoid(spec)

    arm_verts = [v for v in bundle.vertices if abs(v.position[0]) > 15.0 and 80.0 <= v.position[2] <= 150.0]
    assert len(arm_verts) > 0
    z_coords = [v.position[2] for v in arm_verts]
    assert max(z_coords) - min(z_coords) > 40.0, "Arm cylinders must have non-zero height"


def test_runtime_restore_safe_read_tuple_and_non_dict(tmp_path: Path):
    from src.gameforge_ide.backend.agent.runtime import AgentRuntime
    from src.gameforge_ide.backend.providers.router import ModelRouter

    sm = SessionManager(tmp_path)
    sess = sm.create_session("RestoreTest")
    sess_id = sess.session_id

    router = ModelRouter()
    runtime = AgentRuntime(tmp_path, session_manager=sm, model_router=router)

    primary_task = tmp_path / ".gameforge" / "tasks" / f"{sess_id}.json"
    bak_task = primary_task.with_suffix(".json.bak")
    primary_task.parent.mkdir(parents=True, exist_ok=True)
    primary_task.write_text("[1, 2, 3]", encoding="utf-8")

    task = runtime.get_task_state(sess_id)
    assert task is None

    valid_task = TaskState(
        task_id=f"task_{sess_id}",
        session_id=sess_id,
        user_prompt="Add jump",
        goal="Add jump mechanic",
    )
    bak_task.write_text(json.dumps(valid_task.model_dump()), encoding="utf-8")

    recovered_task = runtime.get_task_state(sess_id)
    assert recovered_task is not None
    assert recovered_task.task_id == f"task_{sess_id}"
    assert recovered_task.goal == "Add jump mechanic"
