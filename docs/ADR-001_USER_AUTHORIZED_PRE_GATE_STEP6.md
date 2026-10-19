# ADR-001: User-Authorized Pre-Gate Implementation of Step 6 (Data Factory)

**Date:** 2026-10-19  
**Status:** APPROVED BY USER DIRECTION  
**Deciders:** Project Owner / Antigravity Agent  
**Governing Document:** `GAMEFORGE_FINAL_MASTER_STRATEGY.md` v3.1.0 (Section 30.1, Section 30.1.2)  

---

## 1. Context and Problem Statement

`GAMEFORGE_FINAL_MASTER_STRATEGY.md` defines a strict sequential milestone loop (Section 30.1, Requirement R-2, Constraint C-2) where each milestone acceptance gate must be satisfied with verifiable evidence before advancing to the subsequent milestone.

During the Step 5 review, several findings were identified by external reviewers:
1. `pytest` default configuration in `pyproject.toml` had restricted discovery to `tests/unit`, inadvertently omitting `tests/integration`.
2. Candidate patch application and baseline scorecard consistency required deeper investigation.
3. Total unique automated tests and candidate diffs required reconciliation.

Consequently, the Step 5 acceptance gate could not be marked as independently verified or passed. However, the user issued an explicit directive:
> *"The user has explicitly directed that Step 6 work begin now. Start useful Step 6 implementation despite the unresolved Step 5 review. Treat this as a documented, user-authorized pre-gate implementation branch, not proof that Step 5 passed or that the formal sequential gate has been satisfied."*

## 2. Decision

1. **Pre-Gate Implementation Authorization:**
   Authorize beginning concrete, testable implementation of Step 6 (Rights-Aware Data Factory, Schema, Ingestion, Deduplication, Contamination Scanning, and Tombstone Lineage) in the live workspace.

2. **No Waiver of Gates:**
   This exception authorizes implementation work only. It **does NOT**:
   - Certify or mark Step 5 as accepted, verified, or passed.
   - Authorize model training, fine-tuning, or specialist data synthesis.
   - Waive source rights reviews, license gates, or held-out evaluation contamination protections.
   - Authorize modifying frozen acceptance criteria or baseline metric denominators.

3. **Truthful Record Integrity:**
   - Step 5 status is recorded in the master ledger (`GAMEFORGE_FINAL_MASTER_STRATEGY.md` Sections 16.1, 30.1.3, 32.3) and `GAMEFORGE_ROADMAP.csv` as:
     `UNRESOLVED / NOT ACCEPTED — EVIDENCE INTEGRITY AND TEST GATE OPEN`.
   - Step 6 status is recorded as:
     `USER-AUTHORIZED PRE-GATE IMPLEMENTATION IN PROGRESS — NOT ACCEPTED`.
   - Historical Step 5 raw artifacts and evaluation scorecards are preserved intact without fabrication.

4. **Test Gate Scope Restoration:**
   `pyproject.toml` test discovery path is restored from `tests/unit` to `tests` to ensure no tests are concealed from the full suite discovery.

## 3. Consequences

- **Positive:** Step 6 rights-aware infrastructure, schema validation, and deduplication capabilities can be built and verified against synthetic fixtures without idle waiting.
- **Guardrails Enforced:** Real training runs remain strictly blocked because the Dataset Source Register (`configs/dataset_source_register.json`) classifies all unreviewed internally authored gameplay code as `REVIEW_REQUIRED`.
- **Compliance:** Full compliance with non-negotiable constraints C-2, C-3, C-12, and Section 30.1.2.
