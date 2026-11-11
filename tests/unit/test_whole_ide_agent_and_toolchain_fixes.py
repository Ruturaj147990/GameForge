import hashlib
import json
import pytest
from pathlib import Path

from src.gameforge_ide.pipeline.autofix import autofix
from src.gameforge_ide.backend.agent.task_state import (
    TaskAcceptancePredicate,
    TaskState,
)
from src.gameforge_ide.backend.agent.tool_call_parser import (
    parse_text_for_tool_calls,
)


def test_autofix_repairs_c2662_const_member_helpers():
    """Verify autofix detects helper methods called from const member functions and adds const."""
    h = """#pragma once
#include "CoreMinimal.h"
#include "GFGameBase.h"
#include "GFGameImpl.generated.h"

UCLASS()
class LUDO_API AGFGameImpl : public AGFGameBase
{
	GENERATED_BODY()

public:
	AGFGameImpl();
	virtual FString GetStatusText() const override;
	virtual FString GetSecondaryStatusText() const override;

private:
	bool IsPieceInHomeRun(int32 PlayerIndex, int32 PieceIndex);
	FString GetPlayerColorName(int32 Index);
};
"""
    cpp = """#include "GFGameImpl.h"

FString AGFGameImpl::GetStatusText() const
{
	return FString::Printf(TEXT("Turn: %s"), *GetPlayerColorName(0));
}

FString AGFGameImpl::GetSecondaryStatusText() const
{
	int32 Count = 0;
	if (IsPieceInHomeRun(0, 0)) Count++;
	return FString::Printf(TEXT("Home: %d"), Count);
}

FString AGFGameImpl::GetPlayerColorName(int32 Index)
{
	return TEXT("Red");
}

bool AGFGameImpl::IsPieceInHomeRun(int32 PlayerIndex, int32 PieceIndex)
{
	return true;
}
"""
    files = {"GFGameImpl.h": h, "GFGameImpl.cpp": cpp}
    fixed, notes = autofix(files)

    # Both helper declarations in header must now be const
    assert "FString GetPlayerColorName(int32 Index) const;" in fixed["GFGameImpl.h"]
    assert "bool IsPieceInHomeRun(int32 PlayerIndex, int32 PieceIndex) const;" in fixed["GFGameImpl.h"]

    # Both definitions in cpp must now be const
    assert "FString AGFGameImpl::GetPlayerColorName(int32 Index) const" in fixed["GFGameImpl.cpp"]
    assert "bool AGFGameImpl::IsPieceInHomeRun(int32 PlayerIndex, int32 PieceIndex) const" in fixed["GFGameImpl.cpp"]
    assert any("const" in n for n in notes)


def test_autofix_repairs_c2662_from_compiler_diagnostics():
    """Verify autofix uses C2662 diagnostics to fix functions."""
    h = """#pragma once
#include "CoreMinimal.h"

class AGFGameImpl
{
public:
	int32 ComputeScore(int32 Multiplier);
};
"""
    cpp = """#include "GFGameImpl.h"

int32 AGFGameImpl::ComputeScore(int32 Multiplier)
{
	return 100 * Multiplier;
}
"""
    diags = [
        {
            "severity": "error",
            "code": "C2662",
            "file": "GFGameImpl.cpp",
            "line": 45,
            "message": "'int32 AGFGameImpl::ComputeScore(int32)': cannot convert 'this' pointer from 'const AGFGameImpl' to 'AGFGameImpl &'",
        }
    ]
    files = {"GFGameImpl.h": h, "GFGameImpl.cpp": cpp}
    fixed, notes = autofix(files, diags=diags)

    assert "int32 ComputeScore(int32 Multiplier) const;" in fixed["GFGameImpl.h"]
    assert "int32 AGFGameImpl::ComputeScore(int32 Multiplier) const" in fixed["GFGameImpl.cpp"]
    assert any("fixing C2662" in n for n in notes)


def test_autofix_repairs_c4458_shadowed_world_in_custom_rule():
    """Verify autofix renames shadowed World declarations across any C++ file."""
    rule_cpp = """#include "LudoGameModeRule.h"

void ULudoGameModeRule::OnEvent(const FGameForgeEvent& Event)
{
	Super::OnEvent(Event);
	UWorld* World = GetWorld();
	AGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;
	if (GS) { GS->AddStat(FName(TEXT("score")), 1.0f); }
}
"""
    files = {"LudoGameModeRule.cpp": rule_cpp}
    fixed, notes = autofix(files)

    assert "UWorld* CurrentWorld = GetWorld();" in fixed["LudoGameModeRule.cpp"]
    assert "CurrentWorld ? CurrentWorld->" in fixed["LudoGameModeRule.cpp"]
    assert any("C4458" in n for n in notes)


def test_task_state_wildcard_file_changed_acceptance(tmp_path):
    """Verify file_changed(*) evaluates successfully when an actual file is modified."""
    task = TaskState(
        task_id="task_test_123",
        session_id="sess_123",
        goal="Fix compiler errors",
        intent="mutate",
    )
    pred = TaskAcceptancePredicate(
        predicate_type="file_changed",
        target="*",
    )
    task.acceptance = [pred]

    # Create target file in workspace
    src_dir = tmp_path / "Source" / "Game"
    src_dir.mkdir(parents=True)
    cpp_file = src_dir / "GameImpl.cpp"
    cpp_file.write_text("void Foo() {}", encoding="utf-8")

    pre_hash = hashlib.sha256(b"void Foo() {}").hexdigest()
    cpp_file.write_text("void Foo() const {}", encoding="utf-8")
    post_hash = hashlib.sha256(b"void Foo() const {}").hexdigest()

    tool_history = [
        {
            "tool_name": "propose_edit",
            "arguments": {"subpath": "Source/Game/GameImpl.cpp"},
            "output": json.dumps({
                "status": "APPLIED",
                "file_path": "Source/Game/GameImpl.cpp",
                "original_sha256": pre_hash,
                "new_sha256": post_hash,
            }),
            "status": "SUCCESS",
        }
    ]

    all_sat, unmet = task.evaluate_acceptance(
        workspace_root=tmp_path,
        modified_files={"Source/Game/GameImpl.cpp"},
        tool_history=tool_history,
    )

    assert all_sat is True
    assert len(unmet) == 0
    assert pred.satisfied is True
    assert "verified modified on disk" in pred.evidence


def test_tool_call_parser_python_style_and_unified_diff():
    """Verify tool_call_parser extracts Python-style function calls and unified diffs."""
    # 1. Python-style function call
    py_call_text = 'I will now apply the edit:\npropose_edit(subpath="Source/Ludo/GFGameImpl.h", replacement_content="// Fixed\\n")\nDone.'
    res = parse_text_for_tool_calls(py_call_text)
    assert len(res.calls) == 1
    call = res.calls[0]
    assert call.name == "propose_edit"
    assert call.arguments.get("subpath") == "Source/Ludo/GFGameImpl.h"
    assert call.arguments.get("replacement_content") == "// Fixed\n"

    # 2. Unified diff
    diff_text = """Here is the unified diff to fix the error:
--- a/Source/Ludo/GFGameImpl.h
+++ b/Source/Ludo/GFGameImpl.h
@@ -64,1 +64,1 @@
-	FString GetPlayerColorName(int32 Index);
+	FString GetPlayerColorName(int32 Index) const;
"""
    res_diff = parse_text_for_tool_calls(diff_text)
    assert len(res_diff.calls) == 1
    call_diff = res_diff.calls[0]
    assert call_diff.name == "apply_diff"
    assert call_diff.arguments.get("subpath") == "Source/Ludo/GFGameImpl.h"
    assert "GetPlayerColorName" in call_diff.arguments.get("diff", "")


def test_autofix_synthesizes_stubs_for_missing_definitions():
    """Verify autofix detects functions declared in header but missing in cpp and generates valid stubs (preventing LNK2019)."""
    h = """#pragma once
#include "CoreMinimal.h"
#include "GFGameBase.h"

class AGFGameImpl : public AGFGameBase
{
public:
	AGFGameImpl();
	FVector GetGridRotation(int32 X, int32 Y);
	bool CanMovePiece(int32 PlayerIndex, int32 PieceIndex);
};
"""
    cpp = """#include "GFGameImpl.h"

AGFGameImpl::AGFGameImpl()
{
}
"""
    files = {"GFGameImpl.h": h, "GFGameImpl.cpp": cpp}
    fixed, notes = autofix(files)

    assert "FVector AGFGameImpl::GetGridRotation(int32 X, int32 Y)" in fixed["GFGameImpl.cpp"]
    assert "return FVector::ZeroVector;" in fixed["GFGameImpl.cpp"]
    assert "bool AGFGameImpl::CanMovePiece(int32 PlayerIndex, int32 PieceIndex)" in fixed["GFGameImpl.cpp"]
    assert "return false;" in fixed["GFGameImpl.cpp"]
    assert any("preventing LNK2019" in n for n in notes)


def test_apply_edit_idempotent_already_applied(tmp_path):
    """Verify that calling apply_diff on an already applied diff succeeds idempotently."""
    from src.gameforge_ide.backend.security.boundary import BoundaryManager
    from src.gameforge_ide.backend.tools.edit_tools import EditTools

    target_file = tmp_path / "TestFile.cpp"
    target_file.write_text("int original_val = 1;\n", encoding="utf-8")

    boundary = BoundaryManager(tmp_path)
    edit_tools = EditTools(boundary)

    prop = edit_tools.propose_edit(
        subpath="TestFile.cpp",
        target_content="int original_val = 1;\n",
        replacement_content="int original_val = 42;\n",
    )
    diff_id = prop["diff_id"]

    # First apply
    apply1 = edit_tools.apply_diff(diff_id=diff_id)
    assert apply1["status"] == "SUCCESS"
    assert "42" in target_file.read_text(encoding="utf-8")

    # Second apply (must be idempotent and return SUCCESS, not ERROR)
    apply2 = edit_tools.apply_diff(diff_id=diff_id)
    assert apply2["status"] == "SUCCESS"
    assert apply2.get("already_applied") is True


def test_boundary_posix_drive_path_normalization(tmp_path):
    """Verify that Unix/Git-Bash drive paths like /E/... are normalized without false security violations."""
    from src.gameforge_ide.backend.security.boundary import BoundaryManager

    boundary = BoundaryManager(tmp_path)
    # Construct a POSIX-style path for the tmp_path
    drive_letter = tmp_path.drive.rstrip(":").upper()
    if drive_letter:
        posix_path = f"/{drive_letter}{tmp_path.as_posix()[len(tmp_path.drive):]}"
        resolved = boundary.validate_path(posix_path, allow_write=False)
        assert resolved == tmp_path.resolve()


def test_fs_tools_path_and_subpath_flexible_resolution(tmp_path):
    """Verify tool_list_dir and tool_read_file handle both path and subpath and set status: ERROR on errors."""
    from src.gameforge_ide.backend.security.boundary import BoundaryManager
    from src.gameforge_ide.backend.tools.fs_tools import tool_list_dir, tool_read_file

    sub_dir = tmp_path / "SubModule"
    sub_dir.mkdir()
    f1 = sub_dir / "Module.h"
    f1.write_text("class Module {};\n", encoding="utf-8")

    boundary = BoundaryManager(tmp_path)

    # Both path (as workspace) and subpath provided
    res = tool_list_dir(boundary, path=str(tmp_path), subpath="SubModule")
    assert res["status"] == "SUCCESS"
    assert any("Module.h" in item["path"] for item in res["items"])

    # Error status must be explicitly set on failure
    err_res = tool_list_dir(boundary, subpath="NonExistentDir")
    assert err_res["status"] == "ERROR"
    assert "error" in err_res

    read_err = tool_read_file(boundary, subpath="NonExistentFile.txt")
    assert read_err["status"] == "ERROR"
    assert "error" in read_err


def test_runtime_stream_repetition_detection():
    """Verify runaway token repetition loop detection."""
    from src.gameforge_ide.backend.agent.runtime import AgentRuntime

    normal_text = "To fix this issue, let's inspect the files in the directory. Then we will apply the required changes."
    assert AgentRuntime._detect_stream_repetition(normal_text) is False

    repetitive_text = (
        "However, since the error message indicates that the pending diff was not found, let's try listing.\n"
        "However, since the error message indicates that the pending diff was not found, let's try reading.\n"
        "However, since the error message indicates that the pending diff was not found, let's try proposing."
    )
    assert AgentRuntime._detect_stream_repetition(repetitive_text) is True


def test_verify_disk_contents_remaps_workspace_prefix(tmp_path):
    """Verify EditTools.verify_disk_contents remaps leading workspace directory name."""
    from src.gameforge_ide.backend.security.boundary import BoundaryManager
    from src.gameforge_ide.backend.tools.edit_tools import EditTools

    ws_name = tmp_path.name
    test_f = tmp_path / "Header.h"
    test_f.write_text("#pragma once\n", encoding="utf-8")

    boundary = BoundaryManager(tmp_path)
    edit_tools = EditTools(boundary)

    # Calling with WorkspaceName/Header.h
    res = edit_tools.verify_disk_contents(subpath=f"{ws_name}/Header.h")
    assert res["status"] == "SUCCESS"
    assert res["verified"] is True


def test_tool_gateway_logs_warnings_on_errors(tmp_path, caplog):
    """Verify ToolGateway logs warnings when tools fail or encounter errors."""
    import logging
    from src.gameforge_ide.backend.tools.gateway import ToolGateway

    gateway = ToolGateway(tmp_path)

    with caplog.at_level(logging.WARNING):
        # 1. Non-existent file read
        res = gateway.execute_tool("read_file", {"subpath": "NoSuchFile.cpp"})
        assert res["status"] == "ERROR"
        assert any("NoSuchFile.cpp" in rec.message for rec in caplog.records)

        # 2. Unknown tool
        res_unk = gateway.execute_tool("unregistered_tool_xyz", {})
        assert res_unk["status"] == "ERROR"
        assert any("Unknown tool" in rec.message for rec in caplog.records)


def test_launcher_terminal_logging_configuration():
    """Verify _configure_terminal_logging sets up handlers and levels across gameforge packages."""
    import logging
    from src.gameforge_ide.launcher import _configure_terminal_logging

    _configure_terminal_logging(verbose=False)
    for name in ("src", "src.gameforge_ide", "gameforge_ide", "gameforge"):
        logger = logging.getLogger(name)
        assert logger.level == logging.INFO


def test_boundary_and_tools_support_leading_slash_paths(tmp_path):
    """Verify BoundaryManager and EditTools properly handle subpaths starting with leading slash."""
    from src.gameforge_ide.backend.security.boundary import BoundaryManager
    from src.gameforge_ide.backend.tools.edit_tools import EditTools
    from src.gameforge_ide.backend.tools.fs_tools import tool_list_dir

    src_dir = tmp_path / "Source" / "MyGame"
    src_dir.mkdir(parents=True)
    header_file = src_dir / "MyHeader.h"
    header_file.write_text("// original content\n", encoding="utf-8")

    boundary = BoundaryManager(tmp_path)
    # 1. validate_path with leading slash
    resolved = boundary.validate_path("/Source/MyGame/MyHeader.h")
    assert resolved == header_file

    # 2. list_dir with leading slash path
    list_res = tool_list_dir(boundary, path="/Source/MyGame/", max_depth=1)
    assert list_res["status"] == "SUCCESS"
    assert any("MyHeader.h" in item["path"] for item in list_res["items"])

    # 3. verify_disk_contents with leading slash subpath
    edit_tools = EditTools(boundary)
    v_res = edit_tools.verify_disk_contents(subpath="/Source/MyGame/MyHeader.h", expected_fragment="original")
    assert v_res["status"] == "SUCCESS"
    assert v_res["verified"] is True

    # 4. propose_edit with leading slash subpath
    prop_res = edit_tools.propose_edit(
        subpath="/Source/MyGame/MyHeader.h",
        target_content="// original content\n",
        replacement_content="// new content\n",
    )
    assert prop_res["status"] in ("SUCCESS", "PENDING_APPROVAL")

    # 5. delete_file with leading slash subpath
    del_res = edit_tools.delete_file(subpath="/Source/MyGame/MyHeader.h")
    assert del_res["status"] == "SUCCESS"
    assert not header_file.exists()


def test_qa_generate_handles_all_of_and_any_of_composite_conditions():
    """Verify qa.generate creates executable scenarios for AllOf and AnyOf without ScenarioGaps."""
    from src.gameforge_ide.design.presets import preset_platformer
    from src.gameforge_ide.design.gds import AllOf, AnyOf, EventOccurred, ScenarioRef, StatCompare
    from src.gameforge_ide.qa.generate import generate
    from src.gameforge_ide.qa.manifest import LevelManifest, ManifestActor

    gds = preset_platformer()
    gds.goals.win = [
        AllOf(
            items=[
                EventOccurred(event="wave.cleared"),
                StatCompare(stat="game.counter.waves_cleared", op=">=", value=3.0),
            ]
        ),
        AnyOf(
            items=[
                EventOccurred(event="goal.reached"),
                StatCompare(stat="game.score", op=">=", value=10.0),
            ]
        ),
    ]
    gds.acceptance.scenarios = [
        ScenarioRef(scenario_id="win_all", derived_from="goals.win[0]", must_pass=True),
        ScenarioRef(scenario_id="win_any", derived_from="goals.win[1]", must_pass=True),
        ScenarioRef(scenario_id="smoke", derived_from="smoke", must_pass=True),
    ]

    manifest = LevelManifest(
        level_id="lvl1",
        map="/Game/Maps/TestMap",
        player_start=(0.0, 0.0, 100.0),
        actors=[
            ManifestActor(actor_id="goal", tag="GF_Goal", cls="GameForgeGoal", location=(500.0, 0.0, 100.0)),
        ],
    )

    scenarios, gaps = generate(gds, [manifest])
    assert len(gaps) == 0, f"Expected 0 gaps for AllOf and AnyOf, got: {gaps}"
    assert len(scenarios) == 3

    sc_all = next(s for s in scenarios if s.scenario_id == "win_all")
    assert "Verify all" in sc_all.description
    assert any(getattr(exp, "event", None) == "wave.cleared" for exp in sc_all.expect)

    sc_any = next(s for s in scenarios if s.scenario_id == "win_any")
    assert "Verify any" in sc_any.description



