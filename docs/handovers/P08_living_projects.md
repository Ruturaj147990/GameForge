# P8 — Living Projects: change requests, incremental rebuilds, index, import (handover)

**Branch:** `master` (no feature branches). **Depends on:** P6 accepted (P7 for content regeneration). **Decision:** AD-7.
**Estimate:** 4–5 weeks.

## Objective

A user can keep changing a game after its first build ("make the guards faster", "add a second area with a key door")
and get a verified result **without** losing their own edits. GameForge can also open an existing Unreal project and
work on it safely.

---

## WI-8.1 GDS patches (`design/patch.py`)

- The format is a JSON Patch subset (RFC 6902): `add`, `remove`, `replace`. Paths start with `/` and use GDS field
  names and list indexes. Protected paths that are never patchable: `/meta/gds_id`, `/meta/created_at`,
  `/meta/schema_version`.
- `apply_patch(gds, ops) -> GameDesignSpec`: deep-copy `model_dump()`, apply the ops, bump `meta.revision`, set
  `meta.generator="patch"`, then `model_validate`. Any error → `PatchError` with the failing op index and pydantic
  messages.
- The model path, `propose_patch(gds, request, complete_json)`, sends the current GDS (compact JSON; for local models,
  trimmed to the sections a keyword router selects, e.g. "guard" → `entities`, `rules`, `goals`), the request and the
  schema `{"ops": [...], "summary": str, "questions": [str]}`. Validate. One repair round. Then **dry-run apply**. If
  the result is invalid → `NEEDS_INPUT`.
- Deterministic shortcuts before the model (`design/patch_rules.py`): "faster/slower <entity>" → scale speed props
  ×1.25/×0.8; "more/fewer <entity>" → count ±50 % (rounded, bounds respected); "add N <entity>"; "make it night/dusk/day"
  → lighting. Each shortcut has a unit test.
- UI (Design view): a request box ("Change this game…"), then a diff preview (sentences: "Guards: move speed 300 →
  375"), then **Apply** (new revision), then **Rebuild changes**.

## WI-8.2 Impact analysis and incremental rebuild

- `forge.impact(previous_state: RunState, new_spec: RunSpec) -> ImpactReport` computes the effective hashes (P2 logic)
  for the new spec against the last DONE records and returns `{"rerun": [...], "skip": [...], "new": [...],
  "removed": [...], "estimated_minutes": …}`. Estimates come from the median durations of the past runs of the same
  step kinds.
- The composer must keep step ids **stable**: `assemble_<level_id>`, and so on. Composition inputs per level
  include only that level's plan, so changing level 2 does not rebuild level 1.
- The UI shows the impact before starting: "This change rebuilds: Assemble level_1, Package, Scenarios (≈ 7 min)".

## WI-8.3 Ownership, reconciliation and user-edit protection

- `<project>/GameForge/project_graph.json`:
  ```json
  {"schema": "project_graph/1", "nodes": [
     {"id": "level_1/guards_2", "kind": "actor", "level": "level_1", "label": "guards_2", "owner": "gameforge",
      "generated_by": {"run_id": "...", "step": "assemble_level_1", "plan_hash": "…"},
      "state_hash": "<hash of read-back transform + properties>"},
     {"id": "asset:/Game/GameForge/Materials/MI_floor", "kind": "asset", "owner": "gameforge",
      "file_sha256": "…", "generated_by": {...}}]}
  ```
- **Assembly becomes reconciliation** (replacing `new_level if_exists=replace` from P6):
  1. Read back the current actors (`actors_in_level` with tags).
  2. Owned actors (`GF_Owned` tag) not in the new plan → delete (`delete_actor`).
  3. Owned actors in the plan whose current `state_hash` ≠ the recorded `state_hash` → **user-modified**. Build a
     conflict list.
  4. Owned actors whose plan changed and that are not user-modified → update properties/transform.
  5. New plan actors → spawn. Actors without `GF_Owned` (user-added) are **never touched**.
- Conflicts stop the step with `WAITING_APPROVAL`. The UI offers per actor: *Keep mine* (the node becomes
  `owner:"user"` and the plan stops managing it), *Use the design* (overwrite) or *Cancel*. Assets: compare the file
  SHA-256 with `file_sha256`. A mismatch means a user edit, handled the same way.
- World Partition levels already store one file per actor (OFPA), which matches this model. Non-partitioned levels
  work through read-back hashes.

## WI-8.4 Project index (`index/`)

- `src/gameforge_ide/index/indexer.py`: an SQLite database at `<workspace>/.gameforge/index/<project_key>.db`
  (`project_key` = SHA-1 of the absolute project path), with tables `files(path, size, mtime, sha1)`,
  `symbols(kind, name, file, line, parent)` and an FTS5 table `symbols_fts(name, file)`, plus `config(file, section,
  key, value)` and `assets(path, class, deps_json)`.
- C++ symbols come from a regex scanner (`UCLASS`/`USTRUCT`/`UENUM`/`UFUNCTION`/`UPROPERTY` + the following
  declaration line, and `class X : public Y`). There is no compiler dependency. Incremental: only files whose
  mtime or size changed are re-hashed and re-parsed.
- Assets: through the `list_assets` op when an editor link is up, otherwise left unchanged. The index records
  `assets_indexed_at`.
- A new agent tool `search_index {query, kind?, limit≤50, offset}` (T0, no approval) returns paged results with totals.
- Targets (Blueprint §9): 100k files cold < 10 min; incremental < 2 s for 10 changed files; symbol query < 50 ms.
  Benchmark: `scripts/ide/index_benchmark.py` on a synthetic 100k-file tree created on `E:`.

## WI-8.5 Agent work on existing code with verification

- In Code mode, an applied agent diff on a project offers **Verify** (a Forge run: build_editor → automation →
  package → scenarios), so changes are validated by the same gates as generated games.
- Build failures produce a **Fix with assistant** action. It sends the parsed diagnostics (top 10) and the relevant
  file excerpts (via `search_index`) to the `codegen` role model, which proposes edits through the normal diff and
  approval flow, capped at 3 attempts.

## WI-8.6 Opening existing Unreal projects

1. **Open project folder** with a `.uproject` → read-only mode: index, show its levels, classes and assets, with no
   mutations.
2. A **reverse draft**: the `design` role model summarises the index (top classes, levels, input actions from
   `DefaultInput.ini`) into a `DesignDraft` → GDS with `meta.generator="model:import"` and an `imported: true` marker in
   `acceptance.extra_checks`. It is shown as "inferred design (not authoritative)".
3. **Enable GameForge management** (an explicit dialog listing what will change):
   - copy the GameForge plugin into `Plugins/GameForge` (approval);
   - checkpoints: if the project has **no** `.git`, create the GameForge repo (AD-13). If it **has** a git repo, never
     commit to the user's branches. Offer either (a) checkpoints disabled (rollback unavailable, shown as a warning),
     or (b) a separate worktree on branch `gameforge/checkpoints` with explicit consent. Default: (a).
4. Generated content is added only with `GF_Owned` tags, so reconciliation (WI-8.3) never touches the user's actors.

## Phase exit gate
1. **Ten scripted change requests** on the P6 adventure game (`scripts/pipeline/change_requests_suite.py`): faster
   guards; more relics; add a hazard area; night lighting; add a checkpoint; change the win to also require reaching the
   gate; rename the title; add a second level; remove guards; add a door with a key. Each one is an applied patch plus an
   incremental run that re-runs only impacted steps (assert against the impact report) with scenarios green.
   Evidence: `reports/P8/change_requests.json`.
2. A user-edit protection test: move an owned guard in the editor (op `set_actor_property` from a script acting as the
   user, committed outside Forge), apply the "faster guards" patch → a conflict is raised. "Keep mine" → the guard's
   position is preserved after the rebuild and its speed is unchanged (now user-owned).
3. Index benchmark targets met (`reports/P8/index_benchmark.json`).
4. Import: open one Epic sample or template project (copied to `E:\GameForge\validation\P8_import_<date>`), index it,
   produce a reverse draft, enable management with checkpoints disabled, add one kit pickup through a change request,
   and build. Evidence: `reports/P8/import_demo.json`.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 8.1 | DONE | 2026-11-01T04:45Z | 2026-11-01T05:00Z | design/patch.py, design/patch_rules.py, 	est_gds_patch.py, commit e5d5ef9 |
| 8.2 | DONE | 2026-11-01T05:00Z | 2026-11-01T05:10Z | orge/impact.py, 	est_forge_impact.py, commit 5747a9f |
| 8.3 | DONE | 2026-11-01T05:10Z | 2026-11-01T05:15Z | project_graph.py, 
econciliation.py, 	est_project_graph_and_reconciliation.py, commit 7517741 |
| 8.4 | DONE | 2026-11-01T05:15Z | 2026-11-01T05:25Z | indexer.py, search_index tool, 	est_project_index.py, commit 75d7d3c |
| 8.5 | DONE | 2026-11-01T05:25Z | 2026-11-01T05:30Z | code_verify.py, 	est_code_verify.py, commit 58ddd9 |
| 8.6 | DONE | 2026-11-01T05:30Z | 2026-11-01T05:35Z | project_import.py, 	est_project_import.py, commit 82c2c1f |

## Exit Gates Evidence
- **Exit Gate 1 & 2:** 
eports/P8/change_requests.json (10 scripted change requests applied incrementally, user edit guard preserved with conflict detection and 'keep mine' resolution).
- **Exit Gate 3:** 
eports/P8/index_benchmark.json (100k synthetic project indexed cold in 315.09s < 600s, incremental 10 files in 0.256s < 2.0s, p95 query latency 19.99ms < 50ms).
- **Exit Gate 4:** 
eports/P8/import_demo.json (TP_ThirdPersonBP imported read-only, reverse draft GDS synthesized, GameForge management enabled with checkpoints protection, kit pickup change request applied and verified).

## Review log (Claude)
- 2026-11-01: Phase 8 implemented and fully verified with real-world synthetic 100k-file benchmark, change request suite, and Epic template import demo. All 4 exit gates pass.

## Revisions
- 2026-10-31: created (Claude).
