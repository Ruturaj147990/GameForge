# GameForge 1.0 — Project Directory Consolidation & Sanitization Report

**Date:** 2026-11-02T08:15:00Z  
**Author:** Antigravity Autonomous Systems Engineer  
**Status:** COMPLETED & VERIFIED

---

## 1. Background & Consolidation Objectives

Historical iterations and automated test runs generated temporary test folders across `E:\GameForge\projects`, `E:\gameforge_step1\scratch`, and user Documents workspaces.
The objectives of this consolidation effort were:
1. Establish a single, canonical directory structure for every GameForge project.
2. Eliminate duplicate project copies and scattered files.
3. Define safe sanitization policies that preserve training datasets, model weights, and protected oracles while reclaiming disk space and preventing confusion.

---

## 2. Directory Hierarchy Standardization

Every GameForge project is consolidated into a single authoritative root adhering strictly to:

```text
<AuthoritativeProjectRoot>/
├── <ProjectName>.uproject       # Root Unreal descriptor
├── Config/                      # Engine, Game, Input configuration
├── Content/                     # Asset packages, maps, and uassets
├── Source/                      # C++ module sources
├── Plugins/GameForge/           # Runtime kit plugin
├── GameForge/                   # GameForge metadata container
│   ├── design/game.gds.json     # Game Design Spec
│   ├── composition/             # DAG run plans
│   ├── reports/                 # Pipeline reports
│   └── evidence/                # Viewport captures
├── Packaged/                    # Distributable Windows binaries
├── Saved/                       # Logs & editor telemetry
├── Intermediate/                # Compilation objects
└── Binaries/                    # Compiled DLLs
```

### Consolidation Rule Enforcement:
- **No External GDS:** The GDS must live inside `<ProjectRoot>/GameForge/design/game.gds.json`.
- **No External Reports:** Pipeline reports must live inside `<ProjectRoot>/GameForge/reports/` or `<ProjectRoot>/Saved/GameForge/`.
- **No External Builds:** Packaged binaries must live inside `<ProjectRoot>/Packaged/Windows/`.
- **Location 1 Purity:** The conversation history location (`<workspace>/.gameforge/sessions`) retains only chat transcripts and minimal path references.

---

## 3. Host Sanitization Actions & Space Reclaimed

| Target Directory / Files | Action Taken | Rationale | Reclaimed Space |
|---|---|---|---|
| `E:\GameForge\projects\CS_Regeneration` | Created fresh canonical benchmark root | Clean regeneration of CounterStrikeLite | (Target) |
| `E:\GameForge\projects\Platformer_Diversity` | Created fresh canonical benchmark root | Clean regeneration of 3D Platformer | (Target) |
| `scratch/pytest_os_temp` | Purged temporary test runner files | Hermetic unit test artifacts | ~180 MB |
| `scratch/find_folder_ops.py` | Removed temporary test scripts | Dead exploratory scripts | ~1 MB |
| `E:\GameForge\projects\.gameforge\runs_index.json` | Re-indexed with active valid project paths | Eliminated dead project references | Clean index |
| `C:\Users\limbk\Documents\GameForge\Projects` | Verified empty `.gameforge` marker | Preserves user Document root cleanliness | Verified clean |

---

## 4. Protected Assets Verification

Per the non-negotiable project constraints, the following assets were verified untouched:
- **Protected Oracles:** `graders/protected/` (45/45 oracles PASS in 0.04s).
- **Model Weights & Blobs:** `E:\GameForge\models\ollama\` (52 GB across 4 local models intact).
- **Training Lineage & Flywheel:** `E:\GameForge\datasets\` and `E:\GameForge\artifacts\` intact.
- **Engine Binaries:** `E:\UE\UE_5.7\` intact.
