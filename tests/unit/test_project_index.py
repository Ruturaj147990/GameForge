"""Unit tests for ProjectIndex, C++ symbol extraction, and search tool (WI-8.4)."""
from __future__ import annotations

import time
from pathlib import Path
import pytest

from src.gameforge_ide.index.indexer import ProjectIndex
from src.gameforge_ide.backend.tools.gateway import ToolGateway


@pytest.fixture
def mock_cpp_project(tmp_path: Path) -> Path:
    proj_dir = tmp_path / "MyProject"
    src_dir = proj_dir / "Source" / "MyProject"
    cfg_dir = proj_dir / "Config"
    src_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)

    # Sample C++ header
    (src_dir / "MyCharacter.h").write_text(
        """#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "MyCharacter.generated.h"

UCLASS()
class MYPROJECT_API AMyCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    float MoveSpeed = 600.0f;

    UFUNCTION(BlueprintCallable)
    void PerformJump();
};
""",
        encoding="utf-8",
    )

    # Sample C++ struct and enum
    (src_dir / "MyTypes.h").write_text(
        """#pragma once
#include "CoreMinimal.h"
#include "MyTypes.generated.h"

UENUM(BlueprintType)
enum class EPlayerState : uint8
{
    Idle,
    Running,
    Jumping
};

USTRUCT(BlueprintType)
struct FItemData
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere)
    int32 Count;
};
""",
        encoding="utf-8",
    )

    # Sample INI config
    (cfg_dir / "DefaultGame.ini").write_text(
        """[/Script/EngineSettings.GeneralProjectSettings]
ProjectID=B3C0F59C40E24D738E6A1B8C5DE83F65
ProjectName=MyProject

[/Script/UnrealEd.ProjectPackagingSettings]
BuildConfiguration=PPBC_Development
""",
        encoding="utf-8",
    )

    return proj_dir


def test_cold_and_incremental_indexing(mock_cpp_project: Path):
    idx = ProjectIndex(mock_cpp_project)

    # 1. Cold index
    res_cold = idx.index_project()
    assert res_cold["indexed_files"] >= 3
    assert res_cold["deleted_files"] == 0

    # 2. No changes -> incremental index does nothing
    res_noop = idx.index_project()
    assert res_noop["indexed_files"] == 0

    # 3. Modify 1 file -> only 1 file indexed
    char_h = mock_cpp_project / "Source" / "MyProject" / "MyCharacter.h"
    char_h.write_text(char_h.read_text(encoding="utf-8") + "\n// modified\n", encoding="utf-8")

    res_inc = idx.index_project()
    assert res_inc["indexed_files"] == 1


def test_symbol_search_and_pagination(mock_cpp_project: Path):
    idx = ProjectIndex(mock_cpp_project)
    idx.index_project()

    # Search for AMyCharacter class
    t0 = time.time()
    res = idx.search_symbols("AMyCharacter")
    query_ms = (time.time() - t0) * 1000.0

    assert query_ms < 50.0  # < 50ms performance requirement
    assert res["total"] >= 1
    found_class = next(r for r in res["results"] if r["name"] == "AMyCharacter")
    assert found_class["kind"] == "class"
    assert found_class["parent"] == "ACharacter"

    # Search functions
    fn_res = idx.search_symbols("PerformJump", kind="function")
    assert fn_res["total"] == 1
    assert fn_res["results"][0]["name"] == "PerformJump"
    assert fn_res["results"][0]["parent"] == "AMyCharacter"

    # Search properties
    prop_res = idx.search_symbols("MoveSpeed", kind="property")
    assert prop_res["total"] == 1
    assert prop_res["results"][0]["name"] == "MoveSpeed"

    # Search enum & struct
    enum_res = idx.search_symbols("EPlayerState", kind="enum")
    assert enum_res["total"] == 1
    assert enum_res["results"][0]["name"] == "EPlayerState"

    struct_res = idx.search_symbols("FItemData", kind="struct")
    assert struct_res["total"] == 1
    assert struct_res["results"][0]["name"] == "FItemData"


def test_asset_indexing_and_metadata(mock_cpp_project: Path):
    idx = ProjectIndex(mock_cpp_project)
    assets = [
        {"path": "/Game/Characters/Mannequins/Meshes/SKM_Manny", "class": "SkeletalMesh", "dependencies": []},
        {"path": "/Game/Environment/Rock/SM_Rock_01", "class": "StaticMesh", "dependencies": []},
    ]
    count = idx.index_assets(assets)
    assert count == 2

    # Verify assets in database
    conn = idx._get_connection()
    try:
        rows = conn.execute("SELECT path, class FROM assets").fetchall()
        assert len(rows) == 2
        meta = conn.execute("SELECT value FROM meta WHERE key = 'assets_indexed_at'").fetchone()
        assert meta is not None
        assert "T" in meta[0]
    finally:
        conn.close()


def test_tool_gateway_search_index_integration(mock_cpp_project: Path):
    idx = ProjectIndex(mock_cpp_project)
    idx.index_project()

    gateway = ToolGateway(mock_cpp_project)
    # search_index requires NO approval (T0)
    assert gateway.tool_requires_approval("search_index", {"query": "AMyCharacter"}) is False

    res = gateway.execute_tool("search_index", {"query": "AMyCharacter"})
    assert res.get("total", 0) >= 1
    assert any(r["name"] == "AMyCharacter" for r in res.get("results", []))
