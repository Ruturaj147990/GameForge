"""Investigation unit tests for ProjectIndex, FTS5 underscore tokenization, and thread safety."""
from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path
import pytest

from src.gameforge_ide.index.indexer import ProjectIndex, RE_FUNC_DECL, RE_PROP_DECL


def test_indexer_underscore_tokenization_and_uclass(tmp_path: Path):
    proj_dir = tmp_path / "MyProject"
    src_dir = proj_dir / "Source" / "Game"
    src_dir.mkdir(parents=True)

    header = src_dir / "Combat_Component_Base.h"
    header.write_text(
        """#pragma once
UCLASS(BlueprintType, Category = "Combat_System")
class MYPROJECT_API UCombat_Component_Base : public UActorComponent
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Stats")
    int32 Max_Hit_Points = 500;

    UFUNCTION(BlueprintCallable, Category = "Actions")
    void Apply_Damage_Multiplier(float Base_Damage);
};
""",
        encoding="utf-8",
    )

    idx = ProjectIndex(proj_dir)
    idx.index_project()

    # Verify underscore token preservation in FTS5
    res_comp = idx.search_symbols("Combat_Component_Base")
    assert res_comp["total"] >= 1
    assert res_comp["results"][0]["name"] == "UCombat_Component_Base"

    res_prop = idx.search_symbols("Max_Hit_Points")
    assert res_prop["total"] >= 1
    assert res_prop["results"][0]["name"] == "Max_Hit_Points"

    res_fn = idx.search_symbols("Apply_Damage_Multiplier")
    assert res_fn["total"] >= 1
    assert res_fn["results"][0]["name"] == "Apply_Damage_Multiplier"


def test_cpp_macro_regex_redos_immunity():
    """Verify that pathological / nested inputs do not cause catastrophic backtracking."""
    pathological = "int " * 100 + "foo; // no closing paren"
    t0 = time.time()
    RE_FUNC_DECL.search(pathological)
    RE_PROP_DECL.search(pathological)
    duration = time.time() - t0
    # Must evaluate in less than 0.1s (linear time)
    assert duration < 0.1


def test_indexer_thread_safety_concurrent_access(tmp_path: Path):
    """Verify thread-safe multi-threaded indexing and search without database lock errors."""
    proj_dir = tmp_path / "ConcurrentProject"
    src_dir = proj_dir / "Source"
    src_dir.mkdir(parents=True)

    for i in range(5):
        h = src_dir / f"Actor_{i}.h"
        h.write_text(
            f"""#pragma once
UCLASS()
class MYPROJECT_API AActor_{i} : public AActor {{
    GENERATED_BODY()
public:
    UPROPERTY()
    int32 Health_{i} = 100;
}};
""",
            encoding="utf-8",
        )

    idx = ProjectIndex(proj_dir)
    idx.index_project()

    errors = []

    def _worker(thread_id: int):
        try:
            for _ in range(5):
                res = idx.search_symbols(f"Actor_{thread_id % 5}")
                assert res["total"] >= 1
        except Exception as exc:
            errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker, t) for t in range(8)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0
