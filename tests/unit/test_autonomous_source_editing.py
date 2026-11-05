"""Tests for resilient code editing and full autonomous source engineering."""

from pathlib import Path
import pytest
from src.gameforge_ide.backend.security.boundary import BoundaryManager
from src.gameforge_ide.backend.tools.edit_tools import EditTools
from src.gameforge_ide.backend.tools.gateway import ToolGateway


def test_propose_edit_whitespace_tolerance(tmp_path: Path):
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample_file = tmp_path / "sample.cpp"
    sample_file.write_text(
        "void AGameCharacter::BeginPlay()\n"
        "{\n"
        "    Super::BeginPlay();\n"
        "    SetHealth(100.0f);\n"
        "}\n",
        encoding="utf-8"
    )

    # Indentation mismatch in target_content (2 spaces vs 4 spaces)
    res = et.propose_edit(
        subpath="sample.cpp",
        target_content="  Super::BeginPlay();\n  SetHealth(100.0f);",
        replacement_content="    Super::BeginPlay();\n    SetHealth(200.0f);\n    SetShield(50.0f);",
    )

    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]
    apply_res = et.apply_diff(diff_id)
    assert apply_res["status"] == "SUCCESS"

    updated = sample_file.read_text(encoding="utf-8")
    assert "SetHealth(200.0f);" in updated
    assert "SetShield(50.0f);" in updated


def test_propose_edit_full_file_rewrite_fallback(tmp_path: Path):
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample_file = tmp_path / "config.ini"
    sample_file.write_text("[Settings]\nSpeed=10\n", encoding="utf-8")

    # Empty target_content with replacement_content on existing file -> treated as full-file rewrite
    res = et.propose_edit(
        subpath="config.ini",
        target_content="",
        replacement_content="[Settings]\nSpeed=20\nGravity=980\n",
    )

    assert res["status"] == "PENDING_APPROVAL"
    apply_res = et.apply_diff(res["diff_id"])
    assert apply_res["status"] == "SUCCESS"

    updated = sample_file.read_text(encoding="utf-8")
    assert "Speed=20" in updated
    assert "Gravity=980" in updated


def test_gateway_propose_edit_path_aliases(tmp_path: Path):
    gw = ToolGateway(tmp_path)

    # Calling propose_edit using 'path' instead of 'subpath'
    res = gw.execute_tool(
        "propose_edit",
        {
            "path": "new_script.py",
            "replacement_content": "print('autonomous engineering')\n",
        }
    )

    assert res["status"] == "PENDING_APPROVAL"
    diff_id = res["diff_id"]
    apply_res = gw.execute_tool("apply_edit", {"diff_id": diff_id}, approval_granted=True)
    assert apply_res["status"] == "SUCCESS"

    created = tmp_path / "new_script.py"
    assert created.exists()
    assert "autonomous engineering" in created.read_text(encoding="utf-8")


def test_propose_edit_markdown_fence_stripping(tmp_path: Path):
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample_file = tmp_path / "Hero.cpp"
    sample_file.write_text("void AHero::Attack() { Damage = 10; }\n", encoding="utf-8")

    # Both target and replacement wrapped in markdown code fences
    res = et.propose_edit(
        subpath="Hero.cpp",
        target_content="```cpp\nvoid AHero::Attack() { Damage = 10; }\n```",
        replacement_content="```cpp\nvoid AHero::Attack() { Damage = 25; }\n```",
    )
    assert res["status"] == "PENDING_APPROVAL"
    apply_res = et.apply_diff(res["diff_id"])
    assert apply_res["status"] == "SUCCESS"
    assert "Damage = 25;" in sample_file.read_text(encoding="utf-8")


def test_propose_edit_multiline_blank_line_tolerance(tmp_path: Path):
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample_file = tmp_path / "Player.cpp"
    sample_file.write_text(
        "void APlayer::Init()\n"
        "{\n"
        "    SetupData();\n"
        "\n"
        "    StartTimer();\n"
        "}\n",
        encoding="utf-8"
    )

    # Model provides target without the internal blank line and 2-space indentation
    res = et.propose_edit(
        subpath="Player.cpp",
        target_content="  SetupData();\n  StartTimer();",
        replacement_content="    SetupData();\n    ConfigureNetwork();\n    StartTimer();",
    )
    assert res["status"] == "PENDING_APPROVAL"
    apply_res = et.apply_diff(res["diff_id"])
    assert apply_res["status"] == "SUCCESS"

    content = sample_file.read_text(encoding="utf-8")
    assert "ConfigureNetwork();" in content
    assert "StartTimer();" in content


def test_gateway_all_tools_parameter_aliases(tmp_path: Path):
    gw = ToolGateway(tmp_path)

    # 1. read_file with 'file_path'
    test_f = tmp_path / "readme.txt"
    test_f.write_text("Hello World\nLine 2\n", encoding="utf-8")
    read_res = gw.execute_tool("read_file", {"file_path": "readme.txt"})
    assert read_res["status"] == "SUCCESS"
    assert "Hello World" in read_res["content"]

    # 2. list_dir with 'directory'
    sub_dir = tmp_path / "Sub"
    sub_dir.mkdir()
    (sub_dir / "child.txt").write_text("child", encoding="utf-8")
    list_res = gw.execute_tool("list_dir", {"directory": "Sub"})
    assert list_res["status"] == "SUCCESS"
    assert any("child.txt" in item["path"] for item in list_res["items"])

    # 3. search_code with 'pattern'
    search_res = gw.execute_tool("search_code", {"pattern": "Hello", "path": "."})
    assert search_res["status"] == "SUCCESS"
    assert len(search_res["matches"]) >= 1

    # 4. propose_edit with 'target' and 'replacement' aliases
    prop_res = gw.execute_tool(
        "propose_edit",
        {
            "subpath": "readme.txt",
            "target": "Line 2",
            "replacement": "Line 2 Modified",
        }
    )
    assert prop_res["status"] == "PENDING_APPROVAL"
    diff_id = prop_res["diff_id"]

    # 5. apply_edit with 'diff_id'
    app_res = gw.execute_tool("apply_edit", {"diff_id": diff_id}, approval_granted=True)
    assert app_res["status"] == "SUCCESS"
    assert "Line 2 Modified" in test_f.read_text(encoding="utf-8")

    # 6. rollback_edit with 'id' alias
    rb_res = gw.execute_tool("rollback_edit", {"id": diff_id}, approval_granted=True)
    assert rb_res["status"] == "SUCCESS"
    assert "Line 2\n" in test_f.read_text(encoding="utf-8")


def test_atomic_batch_apply_and_rollback_with_aliases(tmp_path: Path):
    gw = ToolGateway(tmp_path)

    f1 = tmp_path / "mod1.txt"
    f1.write_text("base1\n", encoding="utf-8")
    f2 = tmp_path / "mod2.txt"
    f2.write_text("base2\n", encoding="utf-8")

    p1 = gw.execute_tool("propose_edit", {"subpath": "mod1.txt", "target_content": "base1", "replacement_content": "up1"})
    p2 = gw.execute_tool("propose_edit", {"subpath": "mod2.txt", "target_content": "base2", "replacement_content": "up2"})

    d1, d2 = p1["diff_id"], p2["diff_id"]

    # Apply batch with 'diff_ids' alias
    batch_res = gw.execute_tool("apply_batch", {"diff_ids": [d1, d2]}, approval_granted=True)
    assert batch_res["status"] == "SUCCESS"
    assert f1.read_text(encoding="utf-8") == "up1\n"
    assert f2.read_text(encoding="utf-8") == "up2\n"

    # Rollback batch with 'ids' alias
    rb_batch = gw.execute_tool("rollback_batch", {"ids": [d1, d2]}, approval_granted=True)
    assert rb_batch["status"] == "SUCCESS"
    assert f1.read_text(encoding="utf-8") == "base1\n"
    assert f2.read_text(encoding="utf-8") == "base2\n"


def test_project_index_cpp_symbols_and_fts_search(tmp_path: Path):
    from src.gameforge_ide.index.indexer import ProjectIndex

    src_dir = tmp_path / "Source" / "Game"
    src_dir.mkdir(parents=True)
    header = src_dir / "Character.h"
    header.write_text(
        "class GAME_API ACharacterBase : public AActor\n"
        "{\n"
        "    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = \"Combat\")\n"
        "    TMap<FString, int32> ScoreBoard;\n"
        "\n"
        "    UFUNCTION(BlueprintCallable)\n"
        "    virtual void NotifyActor(float DamageDelta);\n"
        "\n"
        "    void ResetState();\n"
        "};\n",
        encoding="utf-8",
    )

    idx = ProjectIndex(tmp_path)
    res_index = idx.index_project(force=True)
    assert res_index["indexed_files"] >= 1

    # Search for class
    s_class = idx.search_symbols("ACharacterBase")
    assert s_class["total"] >= 1
    assert s_class["results"][0]["name"] == "ACharacterBase"

    # Search for UPROPERTY with TMap
    s_prop = idx.search_symbols("ScoreBoard")
    assert s_prop["total"] >= 1
    assert s_prop["results"][0]["kind"] == "property"

    # Search with FTS5 reserved keywords ('NOT', 'NotifyActor')
    s_not = idx.search_symbols("NotifyActor")
    assert s_not["total"] >= 1
    assert s_not["results"][0]["name"] == "NotifyActor"

    # Search for regular member function
    s_fn = idx.search_symbols("ResetState")
    assert s_fn["total"] >= 1


def test_multiline_cpp_declarations_and_fts_tokenization(tmp_path: Path):
    """Test multi-line UCLASS, inheritance, UFUNCTION and UPROPERTY extraction and FTS5 tokenchars '_'."""
    from src.gameforge_ide.index.indexer import ProjectIndex

    src_dir = tmp_path / "Source" / "Game"
    src_dir.mkdir(parents=True)
    header = src_dir / "MultiLineActor.h"
    header.write_text(
        "UCLASS(\n"
        "    Blueprintable,\n"
        "    ClassGroup=(Custom)\n"
        ")\n"
        "class GAME_API AMultiLineActor :\n"
        "    public AActor\n"
        "{\n"
        "    UPROPERTY(\n"
        "        EditAnywhere,\n"
        "        Category = \"Config\"\n"
        "    )\n"
        "    TMap<\n"
        "        FString,\n"
        "        int32\n"
        "    > Player_Stats_Map;\n"
        "\n"
        "    UFUNCTION(\n"
        "        BlueprintCallable,\n"
        "        Category = \"Events\"\n"
        "    )\n"
        "    virtual void Execute_Action_Sequence(\n"
        "        float DeltaTime,\n"
        "        int32 ActionCode\n"
        "    );\n"
        "};\n",
        encoding="utf-8",
    )

    idx = ProjectIndex(tmp_path)
    res_index = idx.index_project(force=True)
    assert res_index["indexed_files"] >= 1

    # Class with multi-line inheritance
    s_class = idx.search_symbols("AMultiLineActor")
    assert s_class["total"] >= 1
    assert s_class["results"][0]["name"] == "AMultiLineActor"
    assert s_class["results"][0]["parent"] == "AActor"

    # Property with multi-line template and underscores
    s_prop = idx.search_symbols("Player_Stats_Map")
    assert s_prop["total"] >= 1
    assert s_prop["results"][0]["name"] == "Player_Stats_Map"
    assert s_prop["results"][0]["kind"] == "property"

    # FTS5 search with quotes and underscore tokenization
    s_quote = idx.search_symbols('"Player_Stats_Map"')
    assert s_quote["total"] >= 1
    assert s_quote["results"][0]["name"] == "Player_Stats_Map"

    # Multi-line function with underscores
    s_fn = idx.search_symbols("Execute_Action_Sequence")
    assert s_fn["total"] >= 1
    assert s_fn["results"][0]["name"] == "Execute_Action_Sequence"

    # Search query with FTS5 operators and special characters must not raise syntax error
    s_op = idx.search_symbols("NOT OR AND (Player_Stats_Map)*")
    assert isinstance(s_op["total"], int)


def test_batch_comma_separated_strings(tmp_path: Path):
    """Test batch application and rollback accepting comma-separated diff id strings."""
    gw = ToolGateway(tmp_path)

    f1 = tmp_path / "batch1.txt"
    f1.write_text("orig1\n", encoding="utf-8")
    f2 = tmp_path / "batch2.txt"
    f2.write_text("orig2\n", encoding="utf-8")

    p1 = gw.execute_tool("propose_edit", {"path": "batch1.txt", "target": "orig1", "replacement": "new1"})
    p2 = gw.execute_tool("propose_edit", {"path": "batch2.txt", "target": "orig2", "replacement": "new2"})

    d1, d2 = p1["diff_id"], p2["diff_id"]
    comma_ids = f"{d1}, {d2}"

    # Apply batch using comma-separated string
    apply_res = gw.execute_tool("apply_batch", {"diff_ids": comma_ids}, approval_granted=True)
    assert apply_res["status"] == "SUCCESS"
    assert len(apply_res["applied_diff_ids"]) == 2
    assert f1.read_text(encoding="utf-8") == "new1\n"
    assert f2.read_text(encoding="utf-8") == "new2\n"

    # Rollback batch using comma-separated string
    rb_res = gw.execute_tool("rollback_batch", {"diff_ids": comma_ids}, approval_granted=True)
    assert rb_res["status"] == "SUCCESS"
    assert len(rb_res["rolled_back_diff_ids"]) == 2
    assert f1.read_text(encoding="utf-8") == "orig1\n"
    assert f2.read_text(encoding="utf-8") == "orig2\n"


def test_full_file_rewrite_crlf_preservation(tmp_path: Path):
    """Full-file rewrite preserves CRLF line endings when replacement has LF."""
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    sample_file = tmp_path / "WindowsFile.ini"
    sample_file.write_bytes(b"[Section]\r\nKey=Value\r\n")

    # Propose full-file rewrite where replacement uses LF
    res = et.propose_edit(
        subpath="WindowsFile.ini",
        target_content="",
        replacement_content="[Section]\nKey=NewValue\nFlag=True\n",
    )
    assert res["status"] == "PENDING_APPROVAL"
    apply_res = et.apply_diff(res["diff_id"])
    assert apply_res["status"] == "SUCCESS"

    content_bytes = sample_file.read_bytes()
    # Must preserve CRLF line endings throughout the file
    assert b"\r\n" in content_bytes
    assert b"Key=NewValue\r\nFlag=True\r\n" in content_bytes
