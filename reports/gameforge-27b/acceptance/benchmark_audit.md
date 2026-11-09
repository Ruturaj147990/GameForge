# Independent Benchmark Recalculation & Audit Report

**Subject:** Verification of the Reported 50-Task Multi-Engine Benchmark Results  
**Audit Date:** October 23, 2026  
**Auditor:** Independent Acceptance Inspector  

---

## 1. Executive Summary

The reported benchmark results for the four models evaluated on the **GameForge 50-Task Multi-Engine Evaluation Suite** were subjected to an independent arithmetic, structural, and evidentiary audit.

**Audit Determinations:**
1. **Mathematical Consistency:** **CONFIRMED**. The reported point totals (372, 394, 312, 468) equal the exact sum of their respective domain scores across all seven categories. The maximum point total sums to exactly 500 points.
2. **Rubric & Task Contract:** **CONFIRMED**. All 50 task prompts, categories, and scoring criteria are formally specified in `baseline_benchmark.json`.
3. **Raw Output Availability:** **AGGREGATED**. The domain scores and error rates were aggregated at the category level in `model_comparison.json`. To substantiate these findings with active, runnable evidence, an independent 15-task regression suite was executed directly against both models.

---

## 2. Mathematical Recalculation Table

| Model | Domain Breakdown (UE5.7 / Unity / Godot / Roblox / Verse / Bevy / Math) | Reported Score | Recalculated Sum | Denominator | Accuracy |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`qwen3.8:27b-q4_K_M`** | 218 + 31 + 28 + 22 + 20 + 23 + 30 | 372 | **372** | 500 | **74.4%** |
| **`gameforge-v1`** | 236 + 32 + 30 + 24 + 22 + 24 + 26 | 394 | **394** | 500 | **78.8%** |
| **`gameforge-v2`** | 182 + 26 + 25 + 21 + 16 + 18 + 24 | 312 | **312** | 500 | **62.4%** |
| **`gameforge-27b`** | 284 + 38 + 38 + 28 + 27 + 28 + 25 | 468 | **468** | 500 | **93.6%** |

All point allocations and percentage ratios are arithmetically exact.
