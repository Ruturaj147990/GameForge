# GAMEFORGE V2 — DATA PROVENANCE & RIGHTS FORENSIC AUDIT
## Complete Sample-Level Rights Audit of All 500 V2 SFT Pilot Examples

**Date:** 2026-10-20T06:47:53Z  
**Manifest File:** `configs\gameforge_v2_training_manifest.json`  
**Source Register:** `configs\dataset_source_register.json`  
**Governing Authority:** `GAMEFORGE_FINAL_MASTER_STRATEGY.md` Sections 5.5, 6.0, 28.3  

---

## 1. Executive Summary & Legal Gate Status

A forensic audit of all 500 examples in the GameForge V2 SFT pilot manifest was conducted against the registered dataset sources in `configs/dataset_source_register.json`.

### Core Findings:
1. **Zero Confirmed Commercial Training Records:** 100% of the 500 generated examples originate from `gameforge-cleanroom-unreal-pilots`. In `configs/dataset_source_register.json`, this source is explicitly registered as `review_status: REVIEW_REQUIRED` with `permitted_uses.training: false`.
2. **Rights-Cleared Terminology Inconsistency Resolved:** Previous narratives referred to the 500-sample pilot as 'rights-cleared' on the basis of synthetic clean-room generation and zero-contamination n-gram scans. Under governing policy Sections 5.5 and 28.3, **neither synthetic generation nor zero benchmark contamination constitutes legal copyright clearance or commercial training permission**.
3. **Complete Quarantine Action:** In compliance with the fail-closed governance rules, **all 500 samples are formally quarantined** from the training split until external legal counsel executes the clearance packet in `docs/LEGAL_RIGHTS_CLEARANCE_PACKET_V2.md`.
4. **Recomputed Eligible Training Count:** **0 samples** are eligible for gradient optimization at this time.

---

## 2. Recomputed Dataset Metrics

| Metric | Nominal Claimed | Recomputed Audited | Variance / Quarantine |
|---|---|---|---|
| Total Samples in Manifest | 500 | 500 | 0 |
| Eligible Training Split (`train`) | 449 | **0** | -449 (Quarantined) |
| Eligible Development Split (`dev`) | 51 | **0** | 0 (Dev evaluation only) |
| Quarantined Samples | 0 | **500** | +500 (100% Quarantined) |
| Effective Training Gate Status | `CONFIRMED` (historical text) | **`FAIL_CLOSED_GATED`** | Refuses training |

---

## 3. Sample-Level Provenance & Category Distribution

| Category | Target Allocation | Manifest Count | Source ID | Registered Status | Training Permitted? | Destination Split |
|---|---|---|---|---|---|---|
| `engine_independent` | 100 (20%) | 100 | `gameforge-cleanroom-unreal-pilots` | `REVIEW_REQUIRED` | **FALSE** | Quarantined |
| `unreal_engine` | 125 (25%) | 125 | `gameforge-cleanroom-unreal-pilots` | `REVIEW_REQUIRED` | **FALSE** | Quarantined |
| `unity_engine` | 75 (15%) | 75 | `gameforge-cleanroom-unreal-pilots` | `REVIEW_REQUIRED` | **FALSE** | Quarantined |
| `godot_engine` | 50 (10%) | 50 | `gameforge-cleanroom-unreal-pilots` | `REVIEW_REQUIRED` | **FALSE** | Quarantined |
| `other_engines` | 50 (10%) | 50 | `gameforge-cleanroom-unreal-pilots` | `REVIEW_REQUIRED` | **FALSE** | Quarantined |
| `cross_engine_trans` | 50 (10%) | 50 | `gameforge-cleanroom-unreal-pilots` | `REVIEW_REQUIRED` | **FALSE** | Quarantined |
| `debugging_repair` | 50 (10%) | 50 | `gameforge-cleanroom-unreal-pilots` | `REVIEW_REQUIRED` | **FALSE** | Quarantined |

---

## 4. Contamination & Group Leakage Verification

- **Protected Grader Collisions:** 0 collisions across 45 hidden test oracles in `graders/protected/`.
- **Evaluation Dataset Collisions:** 0 collisions across the 60-question evaluation dataset in `configs/gameforge_v1_eval_dataset.json`.
- **Group Leakage Status:** `FAIL_LEAKAGE_DETECTED` (Total groups: 51; 0 groups cross train/dev splits).
- **Legal Note:** Zero contamination confirms isolation from the evaluation oracles, but does not provide external copyright license to train.

---

## 5. Quarantined Samples Registry (Summary)

Total Quarantined Samples: **500**

| Quarantine Reason | Affected Sample Count | Action Taken |
|---|---|---|
| Source `gameforge-cleanroom-unreal-pilots` has `review_status: REVIEW_REQUIRED` & `permitted_uses.training: false` | 500 | Quarantined from training split; training pipeline entry point refuses execution |

---

## 6. Actionable Closure Requirements

To transition any sample from `QUARANTINED` to `ELIGIBLE_FOR_TRAINING`:
1. Author/contributor IP assignments must be formally signed.
2. External legal review packet (`docs/LEGAL_RIGHTS_CLEARANCE_PACKET_V2.md`) must be signed by qualified legal counsel.
3. `configs/dataset_source_register.json` must be updated with signed legal opinion reference and `permitted_uses.training: true`.
4. Training manifest must be cryptographically re-signed with updated sha256 digest.
