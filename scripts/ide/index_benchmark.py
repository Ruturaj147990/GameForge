"""Benchmark for GameForge Project Indexer (WI-8.4, Exit Gate 3).

Creates a synthetic project tree, benchmarks:
1. Cold indexing throughput (target: < 10 min for 100k files).
2. Incremental indexing of 10 modified files (target: < 2 s).
3. Symbol query latency p50 and p95 (target: < 50 ms).

Results are written to reports/P8/index_benchmark.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.index.indexer import ProjectIndex  # noqa: E402


def _get_bench_dir() -> Path:
    try:
        val_root = getattr(get_settings(), "validation_root", None)
        if val_root:
            return Path(val_root) / "bench_100k"
    except Exception:
        pass
    return REPO_ROOT / "scratch" / "validation" / "bench_100k"


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

    files_per_dir = min(1000, total_files)
    num_dirs = max(1, total_files // files_per_dir)

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
    t_start = time.perf_counter()
    print(f"Creating {total_files} synthetic files in {source_dir}...", flush=True)

    for d in range(num_dirs):
        if created >= total_files:
            break
        sub = source_dir / f"Dir_{d:03d}"
        sub.mkdir(exist_ok=True)
        pairs_to_create = min(files_per_dir // 2, (total_files - created) // 2)
        for f in range(pairs_to_create):
            idx = d * (files_per_dir // 2) + f
            h_path = sub / f"BenchActor_{idx}.h"
            cpp_path = sub / f"BenchActor_{idx}.cpp"
            h_path.write_text(header_template.format(idx=idx), encoding="utf-8")
            cpp_path.write_text(cpp_template.format(idx=idx), encoding="utf-8")
            created += 2

    # Remaining odd files if any
    rem_idx = created
    while created < total_files:
        p = source_dir / f"ExtraActor_{rem_idx}.h"
        p.write_text(header_template.format(idx=rem_idx), encoding="utf-8")
        created += 1
        rem_idx += 1

    dur = time.perf_counter() - t_start
    print(f"Created {created} files in {dur:.2f}s", flush=True)


def run_benchmark(total_files: int = 100000, report_path: Optional[Path] = None) -> Dict[str, Any]:
    bench_dir = _get_bench_dir()
    if bench_dir.exists():
        shutil.rmtree(bench_dir, ignore_errors=True)
    bench_dir.mkdir(parents=True, exist_ok=True)

    out_path = report_path or (REPO_ROOT / "reports" / "P8" / "index_benchmark.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        generate_synthetic_project(bench_dir, total_files=total_files)

        idx = ProjectIndex(bench_dir)

        # ── Test 1: Cold indexing ───────────────────────────────────────────
        print("Starting cold indexing benchmark...", flush=True)
        t_cold_start = time.perf_counter()
        cold_res = idx.index_project(force=True)
        cold_duration_s = time.perf_counter() - t_cold_start
        print(f"Cold indexing complete: {cold_duration_s:.2f}s ({cold_res})", flush=True)
        # Scaled cold target: up to 600s for 100k files
        max_cold_allowed = max(30.0, 600.0 * (total_files / 100000.0))
        cold_pass = cold_duration_s < max_cold_allowed

        # ── Test 2: Incremental indexing (10 modified files) ────────────────
        print("Modifying 10 files for incremental benchmark...", flush=True)
        source_dir = bench_dir / "Source" / "BenchProject"
        modified_files: List[str] = []
        for i in range(min(10, total_files)):
            target = source_dir / "Dir_000" / f"BenchActor_{i}.h"
            if not target.is_file():
                # fallback to any file
                candidates = list(source_dir.rglob("*.h"))
                if candidates:
                    target = candidates[i % len(candidates)]
            if target.is_file():
                target.write_text(target.read_text(encoding="utf-8") + "\n// modified\n", encoding="utf-8")
                modified_files.append(str(target))

        t_inc_start = time.perf_counter()
        inc_res = idx.index_project(force=False)
        inc_duration_s = time.perf_counter() - t_inc_start
        print(f"Incremental indexing complete: {inc_duration_s:.3f}s ({inc_res})", flush=True)
        files_indexed = inc_res.get("indexed_files", 0)
        inc_pass = inc_duration_s < 2.0 and files_indexed == len(modified_files)

        # ── Test 3: Symbol query latency ────────────────────────────────────
        print("Measuring symbol query latency over 20 queries...", flush=True)
        query_latencies_ms: List[float] = []
        step_stride = max(1, total_files // 25)
        for q_idx in range(20):
            target_symbol = f"ABenchActor_{q_idx * step_stride}"
            t0 = time.perf_counter()
            s_res = idx.search_symbols(target_symbol)
            lat_ms = (time.perf_counter() - t0) * 1000.0
            query_latencies_ms.append(lat_ms)

        query_latencies_ms.sort()
        p50 = query_latencies_ms[len(query_latencies_ms) // 2]
        p95 = query_latencies_ms[int(len(query_latencies_ms) * 0.95)]
        print(f"Query latency: p50={p50:.2f}ms, p95={p95:.2f}ms")
        query_pass = p95 < 50.0

        all_passed = cold_pass and inc_pass and query_pass
        benchmark_result: Dict[str, Any] = {
            "status": "PASS" if all_passed else "FAIL",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_files": total_files,
            "cold_indexing": {
                "duration_seconds": round(cold_duration_s, 2),
                "target_seconds": round(max_cold_allowed, 1),
                "pass": cold_pass,
            },
            "incremental_indexing": {
                "duration_seconds": round(inc_duration_s, 3),
                "files_modified": len(modified_files),
                "files_indexed": files_indexed,
                "target_seconds": 2.0,
                "pass": inc_pass,
            },
            "query_latency_ms": {
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "target_ms": 50.0,
                "pass": query_pass,
            },
        }

        tmp_out = out_path.with_suffix(".tmp")
        tmp_out.write_text(json.dumps(benchmark_result, indent=2), encoding="utf-8")
        tmp_out.replace(out_path)
        print(f"Benchmark results saved to {out_path}")
        return benchmark_result

    finally:
        print("Cleaning up synthetic benchmark directory...", flush=True)
        shutil.rmtree(bench_dir, ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="GameForge Project Indexer Benchmark")
    parser.add_argument("--files", type=int, default=100000, help="Total synthetic files to generate (default 100000)")
    parser.add_argument("--out", type=Path, default=None, help="Output JSON report path")
    args = parser.parse_args(argv)

    res = run_benchmark(total_files=args.files, report_path=args.out)
    return 0 if res.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
