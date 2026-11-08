"""Unit tests for Multi-File Change Manifest & Bounded Prose Recovery (DEF-304)."""

from pathlib import Path
import pytest

from src.gameforge_ide.backend.agent.multi_file_manifest import (
    BoundedRecoveryHandler,
    FileChangeOperation,
    MultiFileChangeManifest,
)
from src.gameforge_ide.backend.tools.gateway import ToolGateway


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    src_dir = tmp_path / "Source" / "MyGame"
    src_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_file_change_operation_inference_and_symbol_scan():
    """Operation correctly infers header vs source and scans reflection macros."""
    header_content = (
        "#pragma once\n"
        "#include \"CoreMinimal.h\"\n"
        "#include \"GameFramework/Actor.h\"\n"
        "#include \"MyActor.generated.h\"\n\n"
        "UCLASS()\n"
        "class MYGAME_API AMyActor : public AActor {\n"
        "    GENERATED_BODY()\n"
        "public:\n"
        "    UPROPERTY(EditAnywhere)\n"
        "    float Health;\n"
        "    UFUNCTION(BlueprintCallable)\n"
        "    void TakeDamage(float Amount);\n"
        "};\n"
    )
    op = FileChangeOperation.create(
        subpath="Source/MyGame/MyActor.h",
        replacement_content=header_content,
    )
    assert op.file_type == "header"
    assert "AMyActor" in op.symbols_declared
    assert "UCLASS" in op.reflection_macros
    assert "GENERATED_BODY" in op.reflection_macros
    assert "UPROPERTY" in op.reflection_macros
    assert "UFUNCTION" in op.reflection_macros


def test_manifest_reflection_consistency_validation():
    """Detects missing GENERATED_BODY() or misplaced .generated.h include."""
    # Invalid: missing GENERATED_BODY()
    invalid_header_1 = (
        "#pragma once\n"
        "#include \"CoreMinimal.h\"\n"
        "#include \"Player.generated.h\"\n\n"
        "UCLASS()\n"
        "class APlayer : public AActor {\n"
        "public:\n"
        "    int Score;\n"
        "};\n"
    )
    manifest = MultiFileChangeManifest(goal="Test reflection")
    manifest.add_operation(FileChangeOperation.create("Source/MyGame/Player.h", invalid_header_1))
    valid, errs = manifest.validate_reflection_consistency()
    assert not valid
    assert any("GENERATED_BODY()" in e for e in errs)

    # Invalid: .generated.h is not the last include
    invalid_header_2 = (
        "#pragma once\n"
        "#include \"Player.generated.h\"\n"
        "#include \"ExtraInclude.h\"\n\n"
        "UCLASS()\n"
        "class APlayer : public AActor {\n"
        "    GENERATED_BODY()\n"
        "};\n"
    )
    manifest2 = MultiFileChangeManifest(goal="Test include order")
    manifest2.add_operation(FileChangeOperation.create("Source/MyGame/Player.h", invalid_header_2))
    valid2, errs2 = manifest2.validate_reflection_consistency()
    assert not valid2
    assert any("final #include" in e for e in errs2)


def test_topological_execution_ordering_across_4_files():
    """Sorts declarations before consumers and headers before implementations across 4+ files."""
    # 4 C++ files with dependency relations:
    # 1. BaseEntity.h (defines ABaseEntity)
    # 2. BaseEntity.cpp (implements ABaseEntity)
    # 3. PlayerCharacter.h (inherits ABaseEntity, includes BaseEntity.h)
    # 4. PlayerCharacter.cpp (implements APlayerCharacter)
    op1 = FileChangeOperation.create(
        subpath="Source/MyGame/BaseEntity.h",
        replacement_content="#pragma once\nclass ABaseEntity {};\n",
    )
    op2 = FileChangeOperation.create(
        subpath="Source/MyGame/BaseEntity.cpp",
        replacement_content="#include \"BaseEntity.h\"\n",
    )
    op3 = FileChangeOperation.create(
        subpath="Source/MyGame/PlayerCharacter.h",
        replacement_content="#pragma once\n#include \"BaseEntity.h\"\nclass APlayerCharacter : public ABaseEntity {};\n",
    )
    op4 = FileChangeOperation.create(
        subpath="Source/MyGame/PlayerCharacter.cpp",
        replacement_content="#include \"PlayerCharacter.h\"\n",
    )

    # Add in mixed / reverse order
    manifest = MultiFileChangeManifest(goal="Order 4 files")
    manifest.add_operation(op4)
    manifest.add_operation(op3)
    manifest.add_operation(op2)
    manifest.add_operation(op1)

    ordered = manifest.get_topological_execution_order()
    ordered_paths = [op.subpath for op in ordered]

    # Verify BaseEntity.h precedes BaseEntity.cpp
    assert ordered_paths.index("Source/MyGame/BaseEntity.h") < ordered_paths.index("Source/MyGame/BaseEntity.cpp")
    # Verify BaseEntity.h precedes PlayerCharacter.h (decl before consumer)
    assert ordered_paths.index("Source/MyGame/BaseEntity.h") < ordered_paths.index("Source/MyGame/PlayerCharacter.h")
    # Verify PlayerCharacter.h precedes PlayerCharacter.cpp
    assert ordered_paths.index("Source/MyGame/PlayerCharacter.h") < ordered_paths.index("Source/MyGame/PlayerCharacter.cpp")


def test_manifest_apply_success_and_compilation_verification(workspace: Path):
    """Applies multi-file changes and runs verification command successfully."""
    gateway = ToolGateway(workspace)
    manifest = MultiFileChangeManifest(
        goal="Add player interface",
        verification_command="python -c \"import os; assert os.path.exists('Source/MyGame/Player.cpp')\"",
    )
    manifest.add_operation(
        FileChangeOperation.create(
            subpath="Source/MyGame/Player.h",
            replacement_content="#pragma once\n// Player header\n",
        )
    )
    manifest.add_operation(
        FileChangeOperation.create(
            subpath="Source/MyGame/Player.cpp",
            replacement_content="#include \"Player.h\"\n// Player implementation\n",
        )
    )

    res = manifest.apply(gateway, verify_compilation=True, rollback_on_failure=True, approval_granted=True)
    assert res.status == "verified"
    assert res.operations_applied == 2
    assert res.verification_passed is True
    assert (workspace / "Source" / "MyGame" / "Player.h").exists()
    assert (workspace / "Source" / "MyGame" / "Player.cpp").exists()


def test_manifest_rollback_on_verification_failure(workspace: Path):
    """When verification fails, applied changes are rolled back transactionally."""
    orig_file = workspace / "Source" / "MyGame" / "Existing.cpp"
    orig_file.write_text("// original content\nint x = 1;\n", encoding="utf-8")

    gateway = ToolGateway(workspace)
    manifest = MultiFileChangeManifest(
        goal="Faulty patch",
        verification_command="python -c \"import sys; sys.exit(1)\"",  # Force failure
    )
    manifest.add_operation(
        FileChangeOperation.create(
            subpath="Source/MyGame/Existing.cpp",
            target_content="// original content\nint x = 1;\n",
            replacement_content="// broken edit\nint x = 999;\n",
            operation_kind="modify",
        )
    )
    new_file_op = FileChangeOperation.create(
        subpath="Source/MyGame/NewFile.cpp",
        replacement_content="// new file\n",
        operation_kind="create",
    )
    manifest.add_operation(new_file_op)

    res = manifest.apply(gateway, verify_compilation=True, rollback_on_failure=True, approval_granted=True)
    assert res.status == "rolled_back"
    assert res.verification_passed is False

    # Check original file content is restored
    assert orig_file.read_text(encoding="utf-8") == "// original content\nint x = 1;\n"
    # Check new file was unlinked
    assert not (workspace / "Source" / "MyGame" / "NewFile.cpp").exists()


def test_bounded_recovery_handler_extracts_prose_manifest(workspace: Path):
    """Bounded recovery handler extracts file changes from prose code blocks."""
    handler = BoundedRecoveryHandler(max_retries=3)
    prose = (
        "Here are the changes you requested:\n\n"
        "### `Source/MyGame/Health.h`\n"
        "```cpp\n"
        "#pragma once\n"
        "struct FHealth { float Current; };\n"
        "```\n\n"
        "And the source file:\n"
        "### `Source/MyGame/Health.cpp`\n"
        "```cpp\n"
        "#include \"Health.h\"\n"
        "```\n"
    )

    can_recover, manifest, msg = handler.evaluate_prose_turn(prose, turn_attempt=0, workspace_root=workspace)
    assert can_recover is True
    assert manifest is not None
    assert len(manifest.operations) == 2
    assert manifest.operations[0].subpath == "Source/MyGame/Health.h"
    assert manifest.operations[1].subpath == "Source/MyGame/Health.cpp"


def test_bounded_recovery_handler_respects_max_retries(workspace: Path):
    """Bounded recovery halts when attempt reaches max_retries limit."""
    handler = BoundedRecoveryHandler(max_retries=3)
    can_recover, manifest, msg = handler.evaluate_prose_turn("Just conversational text", turn_attempt=3, workspace_root=workspace)
    assert can_recover is False
    assert manifest is None
    assert "budget exhausted" in msg.lower()


def test_manifest_rejects_path_traversal_before_snapshot(workspace: Path):
    """Manifest must reject traversal before reading or writing any target."""
    outside = workspace.parent / "outside.txt"
    outside.write_text("do not touch", encoding="utf-8")
    gateway = ToolGateway(workspace)
    manifest = MultiFileChangeManifest(goal="Traversal regression")
    manifest.add_operation(
        FileChangeOperation.create(
            subpath="../outside.txt",
            replacement_content="overwritten",
            operation_kind="create",
        )
    )
    result = manifest.apply(gateway, approval_granted=True)
    assert result.status == "failed"
    assert outside.read_text(encoding="utf-8") == "do not touch"


def test_manifest_rejects_dependency_cycles():
    """Cyclic dependencies must be rejected rather than silently reordered."""
    first = FileChangeOperation.create(
        "Source/MyGame/A.h", "class A {};", operation_kind="create", dependencies=["B.h"]
    )
    second = FileChangeOperation.create(
        "Source/MyGame/B.h", "class B {};", operation_kind="create", dependencies=["A.h"]
    )
    manifest = MultiFileChangeManifest(goal="Cycle regression", operations=[first, second])
    with pytest.raises(ValueError, match="dependency cycle"):
        manifest.get_topological_execution_order()


def test_manifest_does_not_bypass_request_all_approval(workspace: Path):
    """Multi-file application must respect gateway approval policy."""
    gateway = ToolGateway(workspace)
    manifest = MultiFileChangeManifest(goal="Approval regression")
    manifest.add_operation(
        FileChangeOperation.create(
            "Source/MyGame/NeedsApproval.cpp",
            "// must not be written without approval",
            operation_kind="create",
        )
    )
    result = manifest.apply(gateway, approval_granted=False)
    assert result.status == "failed"
    assert not (workspace / "Source/MyGame/NeedsApproval.cpp").exists()


def test_manifest_full_file_replacement_for_recovered_prose(workspace: Path):
    """A prose-recovered full-file body can safely replace an existing file."""
    target = workspace / "Source/MyGame/Existing.cpp"
    target.write_text("// old body\n", encoding="utf-8")
    gateway = ToolGateway(workspace)
    manifest = MultiFileChangeManifest(goal="Recovered full-file replacement")
    manifest.add_operation(
        FileChangeOperation.create(
            "Source/MyGame/Existing.cpp",
            replacement_content="// complete recovered body\nint value = 7;\n",
            target_content="",
            operation_kind="modify",
        )
    )
    result = manifest.apply(
        gateway, verify_compilation=False, approval_granted=True
    )
    assert result.status == "applied"
    assert "int value = 7;" in target.read_text(encoding="utf-8")
