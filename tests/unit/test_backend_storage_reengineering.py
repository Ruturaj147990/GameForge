"""Comprehensive verification tests for Backend, Core Architecture, Storage & File Engine Re-engineering."""
from __future__ import annotations

import hashlib
import os
import stat
import time
from pathlib import Path
import pytest

from src.gameforge_ide.backend.security.boundary import BoundaryManager
from src.gameforge_ide.backend.tools.edit_tools import EditTools
from src.gameforge_ide.backend.tools.fs_tools import tool_read_file, tool_search_code
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.core import jobs
from src.gameforge_ide.core.jobs import default_job_manager, terminate_all_children
from src.gameforge_ide.design.presets import preset_platformer
from src.gameforge_ide.design.store import load as gds_load, save as gds_save
from src.gameforge_ide.forge.model import RunSpec, RunState, StepKind, StepSpec
from src.gameforge_ide.forge.store import RunStore
from src.gameforge_ide.index.indexer import ProjectIndex


@pytest.fixture
def test_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# =========================================================================
# 1. EditTools: Directory Guard, NOOP, & Read-Only NTFS File Lock Resilience
# =========================================================================

def test_edit_tools_directory_guard(test_ws: Path):
    """Proposing an edit on a directory must fail with clear error."""
    boundary = BoundaryManager(test_ws)
    edit_tools = EditTools(boundary)

    dir_path = test_ws / "Source"
    dir_path.mkdir(parents=True)

    res = edit_tools.propose_edit(subpath="Source", target_content="a", replacement_content="b")
    assert res["status"] == "ERROR"
    assert "directory" in res["error"].lower()


def test_edit_tools_noop_identical(test_ws: Path):
    """Proposing an edit where replacement equals target must return NOOP without creating diff."""
    boundary = BoundaryManager(test_ws)
    edit_tools = EditTools(boundary)

    file_path = test_ws / "code.cpp"
    file_path.write_text("int health = 100;\n", encoding="utf-8")

    res = edit_tools.propose_edit(
        subpath="code.cpp",
        target_content="int health = 100;",
        replacement_content="int health = 100;",
    )
    assert res["status"] == "NOOP"
    assert "No changes proposed" in res["message"]


def test_edit_tools_atomic_write_readonly_resilience(test_ws: Path):
    """Atomic write must succeed even if the target file is marked read-only on Windows."""
    target = test_ws / "readonly_file.txt"
    target.write_text("original content\n", encoding="utf-8")

    # Set file to read-only
    os.chmod(target, stat.S_IREAD)

    EditTools._atomic_write(target, b"updated content\n")
    assert target.read_text(encoding="utf-8") == "updated content\n"

    # Reset permissions for cleanup
    os.chmod(target, stat.S_IWRITE | stat.S_IREAD)


# =========================================================================
# 2. Multi-File Atomic Transactions: apply_batch & rollback_batch
# =========================================================================

def test_apply_and_rollback_batch_success(test_ws: Path):
    """Verify applying a batch of interrelated file edits and rolling them back in batch."""
    gateway = ToolGateway(test_ws)
    edit_tools = gateway.edit_tools

    files = {
        "Module.h": "class Module { int version = 1; };",
        "Module.cpp": "void Module::Init() { version = 1; }",
        "App.cpp": "void Run() { Module m; m.Init(); }",
    }
    for name, content in files.items():
        (test_ws / name).write_text(content, encoding="utf-8")

    # Propose diffs
    p1 = edit_tools.propose_edit("Module.h", "version = 1;", "version = 2;")
    p2 = edit_tools.propose_edit("Module.cpp", "version = 1;", "version = 2;")
    p3 = edit_tools.propose_edit("App.cpp", "m.Init();", "m.Init(); // v2 startup")

    diff_ids = [p1["diff_id"], p2["diff_id"], p3["diff_id"]]

    # Apply batch
    res_batch = edit_tools.apply_batch(diff_ids)
    assert res_batch["status"] == "SUCCESS"
    assert len(res_batch["applied_diff_ids"]) == 3
    assert len(res_batch["files"]) == 3

    assert (test_ws / "Module.h").read_text(encoding="utf-8") == "class Module { int version = 2; };"
    assert (test_ws / "Module.cpp").read_text(encoding="utf-8") == "void Module::Init() { version = 2; }"
    assert "// v2 startup" in (test_ws / "App.cpp").read_text(encoding="utf-8")

    # Rollback batch
    res_rb_batch = edit_tools.rollback_batch(diff_ids)
    assert res_rb_batch["status"] == "SUCCESS"
    assert len(res_rb_batch["rolled_back_diff_ids"]) == 3

    for name, orig in files.items():
        assert (test_ws / name).read_text(encoding="utf-8") == orig


def test_apply_batch_stale_prevalidation_aborts_cleanly(test_ws: Path):
    """If any file in a batch is stale, apply_batch aborts immediately with 0 files modified."""
    gateway = ToolGateway(test_ws)
    edit_tools = gateway.edit_tools

    (test_ws / "f1.txt").write_text("file 1 initial", encoding="utf-8")
    (test_ws / "f2.txt").write_text("file 2 initial", encoding="utf-8")

    p1 = edit_tools.propose_edit("f1.txt", "file 1 initial", "file 1 new")
    p2 = edit_tools.propose_edit("f2.txt", "file 2 initial", "file 2 new")

    # Externally modify f2
    (test_ws / "f2.txt").write_text("file 2 externally modified", encoding="utf-8")

    # Apply batch must fail with STALE on pre-validation
    res = edit_tools.apply_batch([p1["diff_id"], p2["diff_id"]])
    assert res["status"] == "STALE"
    assert res["failed_diff_id"] == p2["diff_id"]

    # File 1 must remain untouched!
    assert (test_ws / "f1.txt").read_text(encoding="utf-8") == "file 1 initial"
    assert (test_ws / "f2.txt").read_text(encoding="utf-8") == "file 2 externally modified"


# =========================================================================
# 3. ProjectIndex: FTS5 Triggers & Scalable JOIN Query
# =========================================================================

def test_indexer_triggers_and_join_query(test_ws: Path):
    """Verify that SQLite triggers automatically synchronize symbols_fts on symbol insert/delete."""
    src_dir = test_ws / "Source" / "Game"
    src_dir.mkdir(parents=True)
    header = src_dir / "PlayerActor.h"
    header.write_text(
        """#pragma once
UCLASS()
class GAME_API APlayerActor : public AActor
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable)
    void FirePrimaryWeapon();
};
""",
        encoding="utf-8",
    )

    idx = ProjectIndex(test_ws)
    res_cold = idx.index_project()
    assert res_cold["indexed_files"] >= 1

    # Search via FTS JOIN
    res_search = idx.search_symbols("APlayerActor")
    assert res_search["total"] == 1
    assert res_search["results"][0]["name"] == "APlayerActor"
    assert res_search["results"][0]["kind"] == "class"

    # Search function
    res_fn = idx.search_symbols("FirePrimaryWeapon", kind="function")
    assert res_fn["total"] == 1
    assert res_fn["results"][0]["name"] == "FirePrimaryWeapon"

    # Search with wildcards and punctuation
    res_punct = idx.search_symbols("::APlayerActor*")
    assert res_punct["total"] >= 1

    # Modify file to remove FirePrimaryWeapon and add DashAbility
    header.write_text(
        """#pragma once
UCLASS()
class GAME_API APlayerActor : public AActor
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable)
    void DashAbility();
};
""",
        encoding="utf-8",
    )

    res_inc = idx.index_project()
    assert res_inc["indexed_files"] == 1

    # FirePrimaryWeapon must be purged from FTS without phantom rowids
    res_old = idx.search_symbols("FirePrimaryWeapon")
    assert res_old["total"] == 0

    res_new = idx.search_symbols("DashAbility")
    assert res_new["total"] == 1


# =========================================================================
# 4. Filesystem Tools: Regex Safety & Robust Reading
# =========================================================================

def test_tool_search_code_invalid_regex_graceful(test_ws: Path):
    """Invalid regex patterns must not crash tool_search_code."""
    boundary = BoundaryManager(test_ws)
    (test_ws / "file.txt").write_text("sample content", encoding="utf-8")

    res = tool_search_code(boundary, query="[unclosed_bracket", is_regex=True)
    assert "error" in res
    assert "Invalid regular expression" in res["error"]


def test_tool_read_file_boundary_bounds(test_ws: Path):
    """Line slicing with out-of-bounds start/end must return safely."""
    boundary = BoundaryManager(test_ws)
    f = test_ws / "lines.txt"
    f.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    res = tool_read_file(boundary, "lines.txt", start_line=-5, end_line=2)
    assert res["status"] == "SUCCESS"
    assert res["total_lines"] == 3
    assert "line 1" in res["content"]
    assert "line 2" in res["content"]


# =========================================================================
# 5. GDS & Forge Store Resilience
# =========================================================================

def test_design_store_save_load_resilience(test_ws: Path):
    """GDS save and load should handle atomic updates and retry loops."""
    gds = preset_platformer(title="StoreTestGame")
    assert gds.meta.revision == 1
    main_path = gds_save(test_ws, gds)
    assert main_path.is_file()

    loaded = gds_load(test_ws)
    assert loaded is not None
    assert loaded.meta.title == "StoreTestGame"
    assert loaded.meta.revision == 1

    # Save revision 2
    gds_v2 = gds.model_copy(deep=True)
    gds_v2.meta.revision = 2
    gds_save(test_ws, gds_v2)
    loaded_v2 = gds_load(test_ws)
    assert loaded_v2 is not None
    assert loaded_v2.meta.revision == 2


def test_forge_run_store_save_load_resilience(test_ws: Path):
    """RunStore atomic save, index update, and load."""
    store = RunStore(project_dir=None, workspace_dir=test_ws)
    s = StepSpec(step_id="step1", kind=StepKind.DESIGN, title="Design")
    run_spec = RunSpec(
        run_id="run_test_001",
        title="Test Build Run",
        workspace_dir=str(test_ws),
        steps=[s],
    )
    state = RunState.new(run_spec)

    saved_path = store.save(state)
    assert saved_path.is_file()

    loaded = store.load("run_test_001")
    assert loaded is not None
    assert loaded.status == "PENDING"
    assert loaded.run.title == "Test Build Run"

    # Runs index check
    index = store.get_runs_index()
    assert len(index) >= 1
    assert index[0]["run_id"] == "run_test_001"


# =========================================================================
# 6. Gateway Tool Dispatch for Batch Operations & ToolService
# =========================================================================

def test_gateway_apply_and_rollback_batch_dispatch(test_ws: Path):
    """ToolGateway must dispatch apply_batch and rollback_batch through execute_tool."""
    gw = ToolGateway(test_ws)
    edit_tools = gw.edit_tools

    (test_ws / "alpha.txt").write_text("alpha 1", encoding="utf-8")
    (test_ws / "beta.txt").write_text("beta 1", encoding="utf-8")

    p1 = edit_tools.propose_edit("alpha.txt", "alpha 1", "alpha 2")
    p2 = edit_tools.propose_edit("beta.txt", "beta 1", "beta 2")
    diff_ids = [p1["diff_id"], p2["diff_id"]]

    # Dispatch apply_batch with approval_granted=True
    res_app = gw.execute_tool("apply_batch", {"diff_ids": diff_ids}, approval_granted=True)
    assert res_app["status"] == "SUCCESS"
    assert len(res_app["applied_diff_ids"]) == 2
    assert (test_ws / "alpha.txt").read_text(encoding="utf-8") == "alpha 2"
    assert (test_ws / "beta.txt").read_text(encoding="utf-8") == "beta 2"

    # Dispatch rollback_batch with approval_granted=True
    res_rb = gw.execute_tool("rollback_batch", {"diff_ids": diff_ids}, approval_granted=True)
    assert res_rb["status"] == "SUCCESS"
    assert len(res_rb["rolled_back_diff_ids"]) == 2
    assert (test_ws / "alpha.txt").read_text(encoding="utf-8") == "alpha 1"
    assert (test_ws / "beta.txt").read_text(encoding="utf-8") == "beta 1"


def test_indexer_large_scale_symbol_search_benchmark(test_ws: Path):
    """Benchmark indexer searching over a large symbol table (10,000 symbols).
    
    Verifies that the SQL JOIN and FTS triggers prevent SQLite variable limit
    overflow (SQLITE_MAX_VARIABLE_NUMBER) and return in < 50ms.
    """
    idx = ProjectIndex(test_ws)
    conn = idx._get_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")
        # Insert 10,000 synthetic symbols with various prefixes
        for i in range(10000):
            conn.execute(
                "INSERT INTO symbols (kind, name, file, line, parent) VALUES (?, ?, ?, ?, ?)",
                ("function", f"GF_BenchmarkFunction_{i:05d}", f"Source/File_{i % 50}.cpp", i, "AActor"),
            )
        conn.commit()
    finally:
        conn.close()

    # Search symbols using FTS matching thousands of rows
    t0 = time.perf_counter()
    res = idx.search_symbols("GF_BenchmarkFunction", limit=50)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert res["total"] == 10000
    assert len(res["results"]) == 50
    assert duration_ms < 50.0  # Must be < 50ms requirement
    assert res["results"][0]["name"].startswith("GF_BenchmarkFunction_")


def test_large_file_50k_lines_safe_edit_benchmark(test_ws: Path):
    """50,000+ line C++ file atomic write and rollback benchmark."""
    gw = ToolGateway(test_ws)
    edit_tools = gw.edit_tools

    large_file = test_ws / "HugeCoreEngine.cpp"
    lines = [f"int32_t EngineRegister_{i} = {i * 13};" for i in range(50000)]
    large_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert large_file.stat().st_size > 1_500_000

    target = "int32_t EngineRegister_25000 = 325000;"
    replacement = "int32_t EngineRegister_25000 = 777777; // Patched value"

    t0 = time.perf_counter()
    prop = edit_tools.propose_edit("HugeCoreEngine.cpp", target, replacement)
    assert prop["status"] == "PENDING_APPROVAL"
    diff_id = prop["diff_id"]

    res_app = edit_tools.apply_diff(diff_id)
    assert res_app["status"] == "SUCCESS"
    assert replacement in large_file.read_text(encoding="utf-8")

    res_rb = edit_tools.rollback_diff(diff_id)
    assert res_rb["status"] == "SUCCESS"
    duration = time.perf_counter() - t0

    assert duration < 2.0  # Completed in < 2 seconds for 50k lines
    assert target in large_file.read_text(encoding="utf-8")
    assert replacement not in large_file.read_text(encoding="utf-8")


# =========================================================================
# 7. Core Jobs: JobManager workers and terminate_all_children
# =========================================================================

def test_jobs_pool_and_termination_primitive():
    """Verify JobManager default workers and terminate_all_children function."""
    mgr = default_job_manager()
    assert mgr._executor._max_workers >= 4

    # terminate_all_children returns bool without raising
    res = terminate_all_children(exit_code=0)
    assert isinstance(res, bool)
