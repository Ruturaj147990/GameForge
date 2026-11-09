"""Benchmark for GameForge Project Indexer (WI-8.4, Exit Gate 3).

Creates a synthetic 100,000-file project tree on E:, benchmarks:
1. Cold indexing throughput (target: < 10 min).
2. Incremental indexing of 10 modified files (target: < 2 s).
3. Symbol query latency p50 and p95 (target: < 50 ms).

Results are written to reports/P8/index_benchmark.json.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.gameforge_ide.index.indexer import ProjectIndex


def generate_synthetic_project(root: Path, total_files: int = 100000) -> None:
    """Generate total_files C++ files across structured subdirectories."""
    source_dir = root / "Source" / "BenchProject"
    config_dir = root / "Config"
    source_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "DefaultGame.ini").write_text(
        "[/Script/EngineSettings.GeneralProjectSettings]\nProjectName=BenchProject\n",
        encoding="utf-8",
    )

    files_per_dir = 1000
    num_dirs = (total_files // files_per_dir) or 1

    header_template = (
        '#pragma once\n'
        '#include "CoreMinimal.h"\n'
        'UCLASS()\n'
        'class BENCH_API ABenchActor_{idx} : public AActor {{\n'
        '    GENERATED_BODY()\n'
        'public:\n'
        '    UPROPERTY(EditAnywhere)\n'
        '    float Health_{idx} = 100.0f;\n'
        '    UFUNCTION(BlueprintCallable)\n'
        '    void PerformAction_{idx}();\n'
        '}};\n'
    )

    cpp_template = (
        '#include "BenchActor_{idx}.h"\n'
        'void ABenchActor_{idx}::PerformAction_{idx}() {{}}\n'
    )

    created = 0
    t_start = time.time()
    print(f"Creating {total_files} synthetic files in {source_dir}...", flush=True)

    for d in range(num_dirs):
        sub = source_dir / f"Dir_{d:03d}"
        sub.mkdir(exist_ok=True)
        # 500 headers + 500 cpps = 1000 files
        for f in range(files_per_dir // 2):
            idx = d * (files_per_dir // 2) + f
            h_path = sub / f"BenchActor_{idx}.h"
            cpp_path = sub / f"BenchActor_{idx}.cpp"
            h_path.write_text(header_template.format(idx=idx), encoding="utf-8")
            cpp_path.write_text(cpp_template.format(idx=idx), encoding="utf-8")
            created += 2

    # Remaining files if any
    rem_idx = created
    while created < total_files:
        p = source_dir / f"ExtraActor_{rem_idx}.h"
        p.write_text(header_template.format(idx=rem_idx), encoding="utf-8")
        created += 1
        rem_idx += 1

    print(f"Created {created} files in {time.time() - t_start:.2f}s")


def run_benchmark() -> dict:
    from src.gameforge_ide.core.settings import get_settings
    bench_dir = get_settings().validation_root / "bench_100k"
    if bench_dir.exists():
        shutil.rmtree(bench_dir, ignore_errors=True)
    bench_dir.mkdir(parents=True, exist_ok=True)

    report_path = Path("reports/P8/index_benchmark.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        total_files = 100000
        generate_synthetic_project(bench_dir, total_files=total_files)

        idx = ProjectIndex(bench_dir)

        # ── Test 1: Cold indexing ───────────────────────────────────────────
        print("Starting cold indexing benchmark...", flush=True)
        t_cold_start = time.time()
        cold_res = idx.index_project(force=True)
        cold_duration_s = time.time() - t_cold_start
        print(f"Cold indexing complete: {cold_duration_s:.2f}s ({cold_res})", flush=True)
        assert cold_duration_s < 600.0, f"Cold indexing took {cold_duration_s}s, exceeding 600s limit"

        # ── Test 2: Incremental indexing (10 modified files) ────────────────
        print("Modifying 10 files for incremental benchmark...", flush=True)
        source_dir = bench_dir / "Source" / "BenchProject"
        modified_files = []
        for i in range(10):
            target = source_dir / "Dir_000" / f"BenchActor_{i}.h"
            if target.is_file():
                target.write_text(target.read_text(encoding="utf-8") + "\n// modified\n", encoding="utf-8")
                modified_files.append(str(target))

        t_inc_start = time.time()
        inc_res = idx.index_project(force=False)
        inc_duration_s = time.time() - t_inc_start
        print(f"Incremental indexing complete: {inc_duration_s:.3f}s ({inc_res})", flush=True)
        assert inc_duration_s < 2.0, f"Incremental indexing took {inc_duration_s}s, exceeding 2.0s limit"
        assert inc_res["indexed_files"] == 10, f"Expected 10 files indexed, got {inc_res['indexed_files']}"

        # ── Test 3: Symbol query latency ────────────────────────────────────
        print("Measuring symbol query latency over 20 queries...", flush=True)
        query_latencies_ms = []
        for q_idx in range(20):
            target_symbol = f"ABenchActor_{q_idx * 2000}"
            t0 = time.time()
            s_res = idx.search_symbols(target_symbol)
            lat_ms = (time.time() - t0) * 1000.0
            query_latencies_ms.append(lat_ms)
            assert s_res["total"] >= 1, f"Expected to find symbol {target_symbol}"

        query_latencies_ms.sort()
        p50 = query_latencies_ms[len(query_latencies_ms) // 2]
        p95 = query_latencies_ms[int(len(query_latencies_ms) * 0.95)]
        print(f"Query latency: p50={p50:.2f}ms, p95={p95:.2f}ms")
        assert p95 < 50.0, f"p95 query latency {p95:.2f}ms exceeded 50ms limit"

        benchmark_result = {
            "status": "PASS",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_files": total_files,
            "cold_indexing": {
                "duration_seconds": round(cold_duration_s, 2),
                "target_seconds": 600.0,
                "pass": cold_duration_s < 600.0,
            },
            "incremental_indexing": {
                "duration_seconds": round(inc_duration_s, 3),
                "files_modified": 10,
                "files_indexed": inc_res["indexed_files"],
                "target_seconds": 2.0,
                "pass": inc_duration_s < 2.0,
            },
            "query_latency_ms": {
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "target_ms": 50.0,
                "pass": p95 < 50.0,
            },
        }

        report_path.write_text(json.dumps(benchmark_result, indent=2), encoding="utf-8")
        print(f"Benchmark results saved to {report_path}")
        return benchmark_result

    finally:
        print("Cleaning up synthetic benchmark directory...")
        shutil.rmtree(bench_dir, ignore_errors=True)


if __name__ == "__main__":
    run_benchmark()
