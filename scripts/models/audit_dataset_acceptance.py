import json
import re
from pathlib import Path
from typing import Set

TRAIN_PATH = Path(r"E:\GameForge\datasets\gameforge-27b\gameforge_27b_train.jsonl")
VAL_PATH = Path(r"E:\GameForge\datasets\gameforge-27b\gameforge_27b_val.jsonl")
BENCHMARK_PATH = (Path(__file__).resolve().parents[1] / r"reports\gameforge-27b\baseline_benchmark.json")
REGISTER_PATH = (Path(__file__).resolve().parents[1] / r"configs\dataset_source_register.json")

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())

def extract_ngrams(text: str, n: int = 5) -> Set[str]:
    words = normalize_text(text).split()
    if len(words) < n:
        return {" ".join(words)}
    return {" ".join(words[i:i+n]) for i in range(len(words) - n + 1)}

def jaccard_similarity(s1: Set[str], s2: Set[str]) -> float:
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)

def audit_datasets():
    print("=" * 80)
    print(" INDEPENDENT DATASET PROVENANCE & LEAKAGE AUDIT")
    print("=" * 80)

    # 1. Load Train and Val
    train_records = []
    with open(TRAIN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                train_records.append(json.loads(line))

    val_records = []
    with open(VAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                val_records.append(json.loads(line))

    # 2. Load Benchmark
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        benchmark_tasks = json.load(f)

    print(f"Train samples: {len(train_records)}")
    print(f"Val samples:   {len(val_records)}")
    print(f"Benchmark tasks: {len(benchmark_tasks)}")

    # 3. Check for Train-Val Overlap
    train_prompts = [normalize_text(r["messages"][0]["content"]) for r in train_records]
    val_prompts = [normalize_text(r["messages"][0]["content"]) for r in val_records]

    train_val_exact = set(train_prompts) & set(val_prompts)
    print(f"Exact Train-Val prompt overlaps: {len(train_val_exact)}")

    # 4. Check for Train-Benchmark Leakage
    leakage_records = []
    for t_idx, t_rec in enumerate(train_records):
        t_prompt = t_rec["messages"][0]["content"]
        t_response = t_rec["messages"][1]["content"] if len(t_rec["messages"]) > 1 else ""
        t_ngrams = extract_ngrams(t_prompt, n=4)

        for b_task in benchmark_tasks:
            b_id = b_task["id"]
            b_prompt = b_task["prompt"]
            b_ngrams = extract_ngrams(b_prompt, n=4)
            sim = jaccard_similarity(t_ngrams, b_ngrams)

            if sim > 0.4 or b_prompt.lower() in t_prompt.lower() or t_prompt.lower() in b_prompt.lower():
                leakage_records.append({
                    "train_idx": t_idx,
                    "benchmark_id": b_id,
                    "jaccard_similarity": sim,
                    "train_prompt": t_prompt[:120],
                    "benchmark_prompt": b_prompt[:120]
                })

    print(f"Direct/Near Leakage between Train and 50-Task Benchmark: {len(leakage_records)}")

    # 5. Check Quarantined Pilot Sources in Register
    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        reg = json.load(f)

    quarantined_sources = [
        s for s in reg.get("registered_sources", [])
        if s.get("review_status") == "REVIEW_REQUIRED" or not s.get("permitted_uses", {}).get("training", False)
    ]
    quarantined_ids = [s["source_id"] for s in quarantined_sources]
    print(f"Quarantined/Restricted source IDs in register: {quarantined_ids}")

    # Check if 27B dataset manifest references any quarantined sources
    manifest_path = Path(r"E:\GameForge\datasets\gameforge-27b\manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    active_source_id = manifest_data.get("source_id")
    print(f"27B Dataset active source ID: {active_source_id}")
    is_quarantined_source = active_source_id in quarantined_ids

    audit_result = {
        "train_samples_count": len(train_records),
        "val_samples_count": len(val_records),
        "benchmark_tasks_count": len(benchmark_tasks),
        "train_val_exact_overlap_count": len(train_val_exact),
        "benchmark_leakage_count": len(leakage_records),
        "leakage_records": leakage_records,
        "active_source_id": active_source_id,
        "is_quarantined_source_ingested": is_quarantined_source,
        "quarantined_sources_in_register": quarantined_ids,
        "status": "CLEAN_NO_LEAKAGE" if len(leakage_records) == 0 and not is_quarantined_source else "LEAKAGE_DETECTED"
    }

    out_file = Path(r"E:\GameForge\reports\gameforge-27b\acceptance\dataset_independent_audit.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(audit_result, indent=2))
    print(f"Saved dataset audit to {out_file}")

if __name__ == "__main__":
    audit_datasets()
