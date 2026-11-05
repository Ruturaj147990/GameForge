"""Unit tests for FTS5 queries, boolean operators, pagination, and fallback behavior."""
from __future__ import annotations

from pathlib import Path
import pytest

from src.gameforge_ide.index.indexer import ProjectIndex


def test_fts_query_syntax_and_operators(tmp_path: Path):
    proj_dir = tmp_path / "FtsProject"
    src_dir = proj_dir / "Source"
    src_dir.mkdir(parents=True)

    header = src_dir / "Symbols.h"
    header.write_text(
        """#pragma once
UCLASS()
class MYPROJECT_API APlayerCharacter : public AActor
{
    GENERATED_BODY()
public:
    UPROPERTY()
    float MovementSpeed = 600.0f;

    UPROPERTY()
    float JumpVelocity = 400.0f;

    UFUNCTION()
    void ResetMovementState();
};
""",
        encoding="utf-8",
    )

    idx = ProjectIndex(proj_dir)
    idx.index_project()

    # 1. Exact quoted search
    res_exact = idx.search_symbols('"APlayerCharacter"')
    assert res_exact["total"] >= 1
    assert res_exact["results"][0]["name"] == "APlayerCharacter"

    # 2. Wildcard prefix search
    res_wildcard = idx.search_symbols("Move*")
    assert res_wildcard["total"] >= 1
    names = [r["name"] for r in res_wildcard["results"]]
    assert "MovementSpeed" in names or "ResetMovementState" in names

    # 3. FTS5 operator keywords in query must not raise OperationalError
    res_ops = idx.search_symbols("NOT OR AND (MovementSpeed)*")
    assert isinstance(res_ops["total"], int)

    # 4. Filter by kind
    res_props = idx.search_symbols("Velocity", kind="property")
    assert res_props["total"] >= 1
    assert res_props["results"][0]["kind"] == "property"
    assert res_props["results"][0]["name"] == "JumpVelocity"


def test_fts_pagination_and_total_counts(tmp_path: Path):
    proj_dir = tmp_path / "PageProject"
    src_dir = proj_dir / "Source"
    src_dir.mkdir(parents=True)

    header = src_dir / "ManyProps.h"
    lines = ["#pragma once", "UCLASS()", "class MYPROJECT_API AManyProps : public AActor {", "GENERATED_BODY()", "public:"]
    for i in range(20):
        lines.append(f"    UPROPERTY() int32 Prop_Index_{i:02d} = {i};")
    lines.append("};")
    header.write_text("\n".join(lines), encoding="utf-8")

    idx = ProjectIndex(proj_dir)
    idx.index_project()

    # Query with limit 5, offset 0
    p1 = idx.search_symbols("Prop_Index", limit=5, offset=0)
    assert p1["total"] == 20
    assert len(p1["results"]) == 5
    assert p1["offset"] == 0

    # Query with limit 5, offset 5
    p2 = idx.search_symbols("Prop_Index", limit=5, offset=5)
    assert p2["total"] == 20
    assert len(p2["results"]) == 5
    assert p2["offset"] == 5

    # Verify no overlapping items between p1 and p2
    p1_names = {r["name"] for r in p1["results"]}
    p2_names = {r["name"] for r in p2["results"]}
    assert len(p1_names.intersection(p2_names)) == 0
