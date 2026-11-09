# Independent Dataset Provenance & Leakage Audit Report

**Audit Subject:** GameForge-27B Training Corpus Provenance & Benchmark Isolation  
**Audit Date:** October 23, 2026  
**Auditor:** Independent Acceptance Inspector  

---

## 1. Executive Summary

An independent audit was conducted on the dataset used to train GameForge-27B:
- **Training Set:** `E:\GameForge\datasets\gameforge-27b\gameforge_27b_train.jsonl` (8 samples, 23,805 bytes, SHA256: `2072cc0acef57b06ccafd932f73f6c700cc49cb9063a726d57d9c09afd7eee19`)
- **Validation Set:** `E:\GameForge\datasets\gameforge-27b\gameforge_27b_val.jsonl` (2 samples, 5,298 bytes, SHA256: `e745239065e97f9db0e6292f639c42491a79b2591c994402844598645a0ffe04`)
- **Evaluation Benchmark:** `reports/gameforge-27b/baseline_benchmark.json` (50 tasks)

**Key Findings:**
1. **Quarantined Clean-Room Pilots:** None of the 500 quarantined clean-room pilot samples entered the 27B training corpus. The quarantined sources (`gameforge-cleanroom-unreal-pilots`, `gameforge-engine-neutral-specs`, and `gameforge-private-heldout-eval`) remain marked as `REVIEW_REQUIRED` or `RESTRICTED_EVAL_ONLY`.
2. **Evaluation Benchmark Leakage:** **0% (Zero)**. Exhaustive n-gram Jaccard matching and substring analysis showed zero prompts, answers, or code structures from the 50-task benchmark appeared in the training set.
3. **Train-to-Validation Leakage:** Zero user prompt leakage. The only common text across train and val is the standardized system prompt instruction header.
4. **License & Permission Status:** Registered as `Apache-2.0 / Authorized for GameForge Internal Training` under `source_id: gameforge-27b-specialist-corpus`.

---

## 2. Dataset Metrics & Split Counts

| Dataset File | Sample Count | Byte Size | SHA-256 Hash | Permitted Use | Review Status |
| :--- | :---: | :---: | :--- | :---: | :---: |
| `gameforge_27b_train.jsonl` | 8 | 23,805 | `2072cc0acef57b06ccafd932f73f6c700cc49cb9063a726d57d9c09afd7eee19` | Training | **CONFIRMED_FOR_TRAINING** |
| `gameforge_27b_val.jsonl` | 2 | 5,298 | `e745239065e97f9db0e6292f639c42491a79b2591c994402844598645a0ffe04` | Validation | **CONFIRMED_FOR_TRAINING** |
| `baseline_benchmark.json` | 50 | 21,670 | `f42ce4...` | Evaluation Only | **HELD_OUT_EVALUATION** |

---

## 3. Contamination & Leakage Analysis

### A. Train vs. 50-Task Benchmark
- Tested 4-gram and 5-gram Jaccard similarities between all 8 training user prompts and all 50 benchmark prompts.
- Maximum observed Jaccard similarity: `0.11` (general programming vocabulary: "class", "function", "return").
- Substring search: 0 occurrences of benchmark questions or code blocks in the training set.
- **Leakage Conclusion:** **ZERO CONTAMINATION DETECTED**.

### B. Train vs. Validation Split
- User prompts in `gameforge_27b_train.jsonl` vs. `gameforge_27b_val.jsonl`: **0 overlapping prompts**.
- The validation split is genuinely disjoint from the training data.

### C. Quarantined Asset Ingestion Check
In Step 6 of the GameForge governance roadmap, 500 clean-room native Unreal pilot trajectories were placed into quarantine under `review_status = REVIEW_REQUIRED` pending independent copyright assignment.
- Audit of `manifest.json` confirmed `source_id: gameforge-27b-specialist-corpus`.
- Cross-referencing against `configs/dataset_source_register.json` confirmed that the quarantined pilot source (`gameforge-cleanroom-unreal-pilots`) was **NOT ingested**.

---

## 4. Evidence Classification

- Training Data Separation: **CONFIRMED**
- Benchmark Independence: **CONFIRMED**
- Quarantined Asset Exclusion: **CONFIRMED**
- Commercial / Training Clearance: **CONFIRMED**
