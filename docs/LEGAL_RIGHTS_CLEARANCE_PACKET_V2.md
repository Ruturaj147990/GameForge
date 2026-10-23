# GAMEFORGE STEP 6 — EXTERNAL LEGAL RIGHTS-CLEARANCE PACKET
**Document Version:** 1.0.0  
**Date:** 20 October 2026  
**Governing Authority:** `GAMEFORGE_FINAL_MASTER_STRATEGY.md` v3.1.0 Section 5.5, 28.3, 30.1.3, 32.8  
**Classification:** LEGAL & REGULATORY COMPLIANCE — MANDATORY PRE-TRAINING GATE  
**Target Milestone:** GameForge V2 Controlled Specialist Training (QLoRA / SFT)

---

## 1. Executive Summary & Purpose

Under the GameForge Master Strategy and copyright compliance governance, **no dataset may be ingested into a model training split until its copyright provenance, license terms, and permitted uses have been formally reviewed and approved by qualified legal counsel**.

This document constitutes the formal **Rights-Clearance Submission Packet** for the GameForge V2 training dataset inventory. It details the provenance, assertions, commercial training risks, and required clearance actions for each source candidate.

**Current Legal Status:** **GATE CLOSED — TRAINING REFUSED FAIL-CLOSED PENDING FORMAL SIGN-OFF.**

---

## 2. Source Inventory & Rights Audit

| Source ID | Claimed Rights Holder | Asserted License | Intended Use | Current Review Status | Training Permitted? |
|---|---|---|---|---|---|
| `gameforge-cleanroom-unreal-pilots` | GameForge Contributors | MIT (Asserted) | Gameplay Code (T2/T3) | `REVIEW_REQUIRED` | **NO (BLOCKED)** |
| `gameforge-engine-neutral-specs` | GameForge Contributors | Apache-2.0 (Asserted) | Contracts & Invariants | `REVIEW_REQUIRED` | **NO (BLOCKED)** |
| `gameforge-synthetic-test-corpus` | GameForge Test Suite | CC0-1.0 | CI Pipeline Validation | `CONFIRMED_FOR_TRAINING` (Test-Only) | **NO (Non-Production)** |
| `gameforge-private-heldout-eval` | GameForge Governance | Proprietary Held-Out | Hidden Benchmark Oracles | `RESTRICTED_EVAL_ONLY` | **STRICTLY PROHIBITED** |
| `epic-unreal-engine-source` | Epic Games, Inc. | Unreal Engine EULA | Engine Architecture | `PROHIBITED` | **STRICTLY PROHIBITED** |
| `unity-engine-source-assets` | Unity Technologies | Unity Terms of Service | Engine Architecture | `PROHIBITED` | **STRICTLY PROHIBITED** |

---

## 3. Deep-Dive Legal Risk Assessment by Source

### 3.1 `gameforge-cleanroom-unreal-pilots`
- **Description:** Internal clean-room implementations of character controller (`t2-001`), health & damage component (`t2-004`), pickup collection system (`t2-005`), projectile combat (`t2-008`), player composition (`t3-016`), and UMG health/stamina HUD (`t3-017`).
- **Asserted Provenance:** Written from functional specifications without decompilation or direct copy-paste of proprietary templates.
- **Legal Risk:**
  1. *Contributor Copyright Assignment:* Without formal Contributor License Agreements (CLAs) or intellectual property assignment, copyright remains fragmented across contributing authors.
  2. *API Copyrightability & Substantial Similarity:* Unreal Engine C++ macros (`UCLASS`, `GENERATED_BODY`, `UPROPERTY`) and GAS patterns reflect Epic Games' proprietary API designs. While functional APIs are generally unprotected under fair use in certain jurisdictions (*Google LLC v. Oracle America, Inc.*), model training on proprietary API headers carries commercial exposure.
- **Clearance Action Required:**
  - Execute standard corporate CLA / copyright assignment for all contributing authors.
  - Legal review of clean-room documentation confirming non-infringing functional implementation.

### 3.2 `gameforge-engine-neutral-specs`
- **Description:** Mathematical formulas (vector math, Quaternions, SAT collision, A* pathfinding, frame-rate independent interpolation) and formal state machine invariants.
- **Asserted Provenance:** Fundamental mathematical and physical algorithms published in academic and open literature.
- **Legal Risk:**
  - Minimal. Mathematical truths, physics principles, and abstract algorithms are non-copyrightable subject matter under 17 U.S.C. § 102(b).
- **Clearance Action Required:**
  - Formal sign-off confirming that text formulations do not reproduce proprietary third-party textbook prose verbatim.

### 3.3 Strict Prohibitions (Non-Negotiable)
- **Epic Games Proprietary Code & Starter Content:** Strict firewall enforced. No files from `Engine/Source/Runtime/` or Epic Marketplace sample projects may enter any training manifest.
- **Private Benchmark Fixtures:** Files in `graders/protected/` are strictly quarantined to prevent evaluation contamination.

---

## 4. Required Sign-Off Protocol for Unblocking Step 6

To transition Step 6 from `REVIEW_REQUIRED` to `CONFIRMED_FOR_TRAINING`:
1. **External Legal Opinion:** Written opinion from qualified intellectual property counsel affirming that the curated training corpus may be used for commercial supervised fine-tuning.
2. **Provenance Registry Update:** Update `configs/dataset_source_register.json` with formal legal counsel reference, signed date, and updated `review_status: "CONFIRMED_FOR_TRAINING"`.
3. **Contamination Verification:** Execution of `ProtectedContaminationScanner` showing zero 13-gram overlap with `graders/protected/` and benchmark tasks.

---

## 5. Formal Gate Verdict

```text
STATUS: TRAINING_GATE_BLOCKED_FAIL_CLOSED
REASON: Zero real gameplay records have received external legal clearance.
POLICY: Supervised fine-tuning / QLoRA weight training cannot proceed until legal sign-off is completed.
REPRODUCIBILITY PREPARATION: All training scripts, hyperparameters, tokenizers, and merge pipelines must be fully implemented, validated, and staged for immediate execution upon clearance.
```
