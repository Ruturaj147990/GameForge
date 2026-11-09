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
