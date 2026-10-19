# GAMEFORGE — STEP 6 EXTERNAL RIGHTS REVIEW PACKET
## Formal Legal & Licensing Review Dossier for Dataset Governance and Training Gate Clearance

**Date:** 2026-10-19  
**Review Target:** Step 6 Data Factory Ingestion Sources, Provenance, and Copyright Governance  
**Governing Authority:** `GAMEFORGE_FINAL_MASTER_STRATEGY.md` v3.1.0 (Sections 5.5, 28.3, 30.1, 32.8)  
**Document Classification:** External Legal Review Dossier & Rights Clearance Prerequisite  
**Milestone Gate Status:** **TRAINING GATE CLOSED — 0 REAL GAMEPLAY EXAMPLES CLEARED FOR TRAINING**

---

## 1. Purpose and Notice to Legal Counsel

This review packet establishes the provenance, licensing basis, intended uses, and risk boundaries of all code, trajectory, and specification sources registered within the GameForge Data Factory.

**MANDATORY DIRECTIVE:** Under Section 28.3 of `GAMEFORGE_FINAL_MASTER_STRATEGY.md`, **no model training (continued pre-training, supervised fine-tuning, or RL) may commence until this review packet is formally executed and signed off by authorized legal counsel or rights holders.**

Public availability on GitHub or other platforms does not constitute training authorization. Clean-room claims require explicit copyright assignment documentation.

---

## 2. Dataset Source Register Overview

The governing register is maintained at `configs/dataset_source_register.json` (v1.1.0).

| Source ID | Name | Stated Provenance | Rights Holder | Asserted License | Intended Uses | Current Rights State | Permitted for Model Training? |
|---|---|---|---|---|---|---|---|
| `gameforge-cleanroom-unreal-pilots` | GameForge Clean-Room Native Unreal Pilots | Internally authored clean-room C++ implementation of T2/T3 gameplay tasks in Unreal Engine | GameForge Authors / Pending Legal Review | MIT (Asserted, rights unreviewed for training use) | EVALUATION, BENCHMARK_FIXTURE | `REVIEW_REQUIRED` | **NO (BLOCKED)** |
| `gameforge-engine-neutral-specs` | GameForge Engine-Neutral Semantic Specifications | Mathematical invariants, event timing contracts, and formal behavioral rubrics | GameForge Authors / Pending Legal Review | Apache-2.0 (Asserted, rights unreviewed for training use) | EVALUATION, SPECIFICATION | `REVIEW_REQUIRED` | **NO (BLOCKED)** |
| `gameforge-synthetic-test-corpus` | GameForge Synthetic Test Corpus | Generated in-memory/in-test for automated pipeline validation | GameForge Test Suite | CC0-1.0 | TRAINING_TEST, EVALUATION_TEST | `CONFIRMED_FOR_TRAINING` | **YES (Unit Testing Only)** |
| `gameforge-private-heldout-eval` | GameForge Private Held-Out Benchmark Split | Held-out acceptance tasks and hidden test oracles | GameForge Governance | PROPRIETARY_HELD_OUT | PRIVATE_EVALUATION | `RESTRICTED_EVAL_ONLY` | **NO (STRICTLY PROHIBITED)** |

---

## 3. Provenance and Ownership Evidence for Internally Authored Fixtures

### Source 1: `gameforge-cleanroom-unreal-pilots`
- **Location in Repository:** `fixtures/unreal/` (including `t2_001_controller`, `t2_004_health_damage`, `t2_005_pickup_collection`, `t2_008_projectile_collision`, `t3_016_player_composition`, `t3_017_health_hud`).
- **Nature of Content:** Unreal Engine 5 C++ classes (`UActorComponent`, `APawn`, `AActor`, `UUserWidget`), `.uproject` files, and basic configuration files (`DefaultEngine.ini`, `DefaultInput.ini`).
- **Current Legal Question:**
  1. Do these classes incorporate or derive from Epic Games' proprietary sample projects (e.g. Third Person Template, Lyra, Action RPG)?
  2. Does the contributor who authored these files possess exclusive copyright, and has a Contributor License Agreement (CLA) or Copyright Assignment Agreement been executed to GameForge?
  3. Does training an AI model on Unreal Engine C++ header files (`CoreMinimal.h`, macro definitions) violate Epic Games' Unreal Engine EULA?
- **Required Approval:** Written legal counsel opinion confirming copyright assignment and verifying compliance with the Epic Games EULA regarding AI training.

---

### Source 2: `gameforge-engine-neutral-specs`
- **Location in Repository:** `benchmark_tasks/engine_neutral/` and `TASK_INVENTORY.csv`.
- **Nature of Content:** Natural language task specifications, state-transition rules, and mathematical invariance bounds.
- **Current Legal Question:**
  1. Are any gameplay rules derived verbatim from published game rulebooks, commercial patents, or copyrighted game design documents?
  2. Does the Apache-2.0 grant cover synthetic dataset transformation into tokenized model weights?
- **Required Approval:** Confirmation of original authorship and non-infringement clearance.

---

### Source 3: `gameforge-private-heldout-eval`
- **Location in Repository:** `graders/protected/` (45 hidden test oracles and 16 runtime probes).
- **Governance Requirement:** **PERMANENT TRAINING EXCLUSION.**
- **Enforcement Mechanism:**
  - Automated contamination scanning (`ProtectedContaminationScanner` in `src/gameforge_bench/data_factory.py`) enforces strict 8-gram and hash isolation.
  - Any ingestion attempt of files matching this source triggers an immediate pipeline abort.

---

## 4. Contamination, Deduplication, and Tombstone Governance

1. **Group-Aware Splitting:**
   - Samples are grouped by project/task family to guarantee that revisions of the same code never appear in both `train` and `dev` splits.
2. **Deduplication:**
   - Exact duplicates are rejected deterministically via SHA-256 fingerprinting.
   - Near-duplicates (difflib ratio >= 0.85) are flagged for human review without silent loss of provenance.
3. **Tombstone Lineage:**
   - Any source revoked by copyright notice or licensing determination is recorded in `configs/tombstones.json`.
   - The data factory automatically purges tombstoned hashes and prevents re-ingestion.

---

## 5. Formal Legal Sign-Off Checklist

Before any source state is changed from `REVIEW_REQUIRED` to `CONFIRMED_FOR_TRAINING`:

- [ ] **Contributor Assignment:** Executed CLA / Copyright Assignment for all internal fixtures.
- [ ] **EULA Compliance Review:** Written verification of Epic Games UE 5.7.4 EULA terms regarding AI model training on code referencing engine APIs.
- [ ] **Third-Party Dependency Audit:** Verification that no GPL, AGPL, or unapproved copyleft libraries are linked or included.
- [ ] **Proprietary Asset Scrubbing:** 100% confirmation that no Epic Marketplace binary uassets or commercial meshes/textures are present in training manifests.
- [ ] **PII and Secret Scanning:** Verified that zero API keys, personal emails, or credentials exist in candidate trajectories.

**Counsel Signature:** ____________________________________  
**Date:** ________________________  
**Approved Sources:** ____________________________________  
