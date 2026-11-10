"""Independent dataset provenance & leakage audit for GameForge models."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_BENCHMARK_PATH = REPO_ROOT / "reports" / "gameforge-27b" / "baseline_benchmark.json"
DEFAULT_REGISTER_PATH = REPO_ROOT / "configs" / "dataset_source_register.json"


def _write_atomic_json(target_path: Path, data: Any) -> None:
    """Atomically write JSON data to file using a temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, target_path)


def resolve_dataset_file(name: str, explicit: Optional[Path] = None) -> Path:
    """Resolve dataset file path from explicit override, E: drive, or repository datasets directory."""
    if explicit:
        return explicit
    candidates = [
        Path(rf"E:\GameForge\datasets\gameforge-27b\{name}"),
        REPO_ROOT / "datasets" / "gameforge-27b" / name,
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return candidates[0]


def resolve_output_file(explicit: Optional[Path] = None) -> Path:
    """Resolve audit report output path."""
    if explicit:
        return explicit
    e_path = Path(r"E:\GameForge\reports\gameforge-27b\acceptance\dataset_independent_audit.json")
    if e_path.parent.parent.exists():
        return e_path
    return REPO_ROOT / "reports" / "gameforge-27b" / "acceptance" / "dataset_independent_audit.json"


def normalize_text(text: str) -> str:
    """Normalize whitespace and case for text comparison."""
    return re.sub(r"\s+", " ", text.lower().strip())


def extract_ngrams(text: str, n: int = 5) -> Set[str]:
    """Extract word n-grams from text for Jaccard similarity comparison."""
    words = normalize_text(text).split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard_similarity(s1: Set[str], s2: Set[str]) -> float:
    """Calculate Jaccard similarity coefficient between two n-gram sets."""
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def audit_datasets(
    train_path: Optional[Path] = None,
    val_path: Optional[Path] = None,
    benchmark_path: Optional[Path] = None,
    register_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    print("=" * 80)
    print(" INDEPENDENT DATASET PROVENANCE & LEAKAGE AUDIT")
    print("=" * 80)

    train_file = resolve_dataset_file("gameforge_27b_train.jsonl", train_path)
    val_file = resolve_dataset_file("gameforge_27b_val.jsonl", val_path)
    bench_file = benchmark_path or DEFAULT_BENCHMARK_PATH
    reg_file = register_path or DEFAULT_REGISTER_PATH
    man_file = resolve_dataset_file("manifest.json", manifest_path)
    out_file = resolve_output_file(output_path)

    missing = [str(p) for p in [train_file, val_file, bench_file, reg_file] if not p.is_file()]
    if missing:
        print(f"Warning: missing required audit input files: {missing}")
        audit_result: Dict[str, Any] = {
            "status": "BLOCKED",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "missing_files": missing,
            "train_samples_count": 0,
            "val_samples_count": 0,
            "benchmark_tasks_count": 0,
        }
        _write_atomic_json(out_file, audit_result)
        return audit_result

    # 1. Load Train and Val
    train_records: List[Dict[str, Any]] = []
    with open(train_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                train_records.append(json.loads(line))

    val_records: List[Dict[str, Any]] = []
    with open(val_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                val_records.append(json.loads(line))

    # 2. Load Benchmark
    with open(bench_file, "r", encoding="utf-8") as f:
        benchmark_tasks = json.load(f)

    print(f"Train samples: {len(train_records)} (from {train_file})")
    print(f"Val samples:   {len(val_records)} (from {val_file})")
    print(f"Benchmark tasks: {len(benchmark_tasks)} (from {bench_file})")

    # 3. Check for Train-Val Overlap
    train_prompts = [normalize_text(r["messages"][0]["content"]) for r in train_records if r.get("messages")]
    val_prompts = [normalize_text(r["messages"][0]["content"]) for r in val_records if r.get("messages")]

    train_val_exact = set(train_prompts) & set(val_prompts)
    print(f"Exact Train-Val prompt overlaps: {len(train_val_exact)}")

    # 4. Check for Train-Benchmark Leakage
    leakage_records: List[Dict[str, Any]] = []
    for t_idx, t_rec in enumerate(train_records):
        msgs = t_rec.get("messages", [])
        if not msgs:
            continue
        t_prompt = msgs[0].get("content", "")
        t_ngrams = extract_ngrams(t_prompt, n=4)

        for b_task in benchmark_tasks:
            b_id = b_task.get("id", "unknown")
            b_prompt = b_task.get("prompt", "")
            b_ngrams = extract_ngrams(b_prompt, n=4)
            sim = jaccard_similarity(t_ngrams, b_ngrams)

            if sim > 0.4 or (b_prompt and b_prompt.lower() in t_prompt.lower()) or (t_prompt and t_prompt.lower() in b_prompt.lower()):
                leakage_records.append({
                    "train_idx": t_idx,
                    "benchmark_id": b_id,
                    "jaccard_similarity": round(sim, 4),
                    "train_prompt": t_prompt[:120],
                    "benchmark_prompt": b_prompt[:120],
                })

    print(f"Direct/Near Leakage between Train and Benchmark: {len(leakage_records)}")

    # 5. Check Quarantined Pilot Sources in Register
    with open(reg_file, "r", encoding="utf-8") as f:
        reg = json.load(f)

    quarantined_sources = [
        s for s in reg.get("registered_sources", [])
        if s.get("review_status") == "REVIEW_REQUIRED" or not s.get("permitted_uses", {}).get("training", False)
    ]
    quarantined_ids = [s["source_id"] for s in quarantined_sources]
    print(f"Quarantined/Restricted source IDs in register: {quarantined_ids}")

    # Check if dataset manifest references any quarantined sources
    active_source_id = "unknown"
    is_quarantined_source = False
    if man_file.is_file():
        with open(man_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        active_source_id = manifest_data.get("source_id", "unknown")
        print(f"Dataset active source ID: {active_source_id}")
        is_quarantined_source = active_source_id in quarantined_ids

    status = "CLEAN_NO_LEAKAGE" if len(leakage_records) == 0 and not is_quarantined_source else "LEAKAGE_DETECTED"

    audit_result = {
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "train_samples_count": len(train_records),
        "val_samples_count": len(val_records),
        "benchmark_tasks_count": len(benchmark_tasks),
        "train_val_exact_overlap_count": len(train_val_exact),
        "benchmark_leakage_count": len(leakage_records),
        "leakage_records": leakage_records,
        "active_source_id": active_source_id,
        "is_quarantined_source_ingested": is_quarantined_source,
        "quarantined_sources_in_register": quarantined_ids,
    }

    _write_atomic_json(out_file, audit_result)
    print(f"Saved dataset audit to {out_file} -> [{status}]")
    return audit_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit dataset provenance and leakage")
    parser.add_argument("--train", type=Path, default=None, help="Train JSONL path")
    parser.add_argument("--val", type=Path, default=None, help="Validation JSONL path")
    parser.add_argument("--benchmark", type=Path, default=None, help="Benchmark JSON path")
    parser.add_argument("--register", type=Path, default=None, help="Dataset register JSON path")
    parser.add_argument("--manifest", type=Path, default=None, help="Dataset manifest JSON path")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args()

    result = audit_datasets(
        train_path=args.train,
        val_path=args.val,
        benchmark_path=args.benchmark,
        register_path=args.register,
        manifest_path=args.manifest,
        output_path=args.output,
    )

    status = result.get("status")
    if status == "CLEAN_NO_LEAKAGE":
        return 0
    elif status == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
