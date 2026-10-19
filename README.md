# GameForge Step 1 Starter Pack

This bundle starts Phase 0 from the master blueprint. It defines the charter, task schema, grading contract, first 30 logical tasks, and six pilot-task drafts.

## Contents
- `PROJECT_CHARTER.md` — mission, scope, operating definition of success, acceptance gate.
- `TASK_SCHEMA.yaml` — proposed machine-readable task format; illustrative and not yet schema-validated.
- `TASK_INVENTORY.csv` — 30 logical T2/T3 task specifications.
- `EVALUATION_CONTRACT.md` — grading layers, result vocabulary, per-run report fields, baseline fairness.
- `DECISION_LOG.csv` — open technical/legal choices.
- `pilot_tasks/` — six task-spec drafts to be turned into clean engine fixtures and hidden graders.

## Important status
These are specifications only. Engine-specific starter projects, hidden graders, reference solutions, probes, license reviews, and repeatability tests have not been implemented. Engine versions are intentionally not pinned until actual runner availability and license/CI constraints are checked.

## Recommended next action
Implement the *harness skeleton* and choose one pilot task to validate end-to-end in one engine before scaling out to all variants. Record runner flakiness separately from model failure.

---

# GameForge-Bench Implementation & Execution Guide (Step 1)

## 1. Quick Setup

```powershell
# Set Python path to include source root
$env:PYTHONPATH = "src"

# Install dependencies (if needed)
pip install -r requirements.txt
```

## 2. Benchmark Tooling Commands

### Environment and Engine Audit (`doctor`)
Inspects Python, .NET, MSVC, MSBuild, Git, and auto-discovers installed Unreal and Unity game engines:
```powershell
python -m gameforge_bench.cli doctor
python -m gameforge_bench.cli doctor --json
```

### Validate Benchmark Specifications (`validate-specs`)
Validates logical inventory (`TASK_INVENTORY.csv`), pilot drafts (`pilot_tasks/`), formal schemas, and reports discrepancies:
```powershell
python -m gameforge_bench.cli validate-specs
```

### List Logical Tasks (`list-tasks`)
Lists all 30 logical tasks with tiers, categories, and matching engine pilot variants:
```powershell
python -m gameforge_bench.cli list-tasks
```

### Execute Benchmark Task Runner (`run`)
Runs the 15-step grading pipeline on a task against an engine and candidate project:
```powershell
# Run reference solution for third-person player controller on Unreal Engine 5:
python -m gameforge_bench.cli run --task-id t2-001-third-person-controller --engine unreal --candidate-dir graders/reference_solutions/unreal/t2_001_controller

# Run controlled fault candidate (demonstrates partial build / defect detection):
python -m gameforge_bench.cli run --task-id t2-001-third-person-controller --engine unreal --candidate-dir graders/reference_solutions/unreal/t2_001_failing_speed --candidate-id defective_speed_candidate

# Run reference solution for health/damage system (Pilot 2) on Unreal Engine 5:
python -m gameforge_bench.cli run --task-id t2-004-health-damage --engine unreal --candidate-dir graders/reference_solutions/unreal/t2_004_health

# Run reference solution for pickup collection system (Step 3 Task 1):
python -m gameforge_bench.cli run --task-id t2-005-pickup-collection --engine unreal --candidate-dir graders/reference_solutions/unreal/t2_005_pickup

# Run reference solution for player character composition (Step 3 Task 2):
python -m gameforge_bench.cli run --task-id t3-016-player-composition --engine unreal --candidate-dir graders/reference_solutions/unreal/t3_016_composition
```

### Summarize Benchmark Runs (`summarize`)
Aggregates machine-readable evaluation reports across runs:
```powershell
python -m gameforge_bench.cli summarize --report-dir reports
```

## 3. Running Automated Tests

```powershell
# Unit tests (harness, policy, discovery, adapters, reporting, isolation provider)
pytest tests/unit -v

# Hidden grader oracles (isolated tests for temporal and event contracts)
pytest graders/protected -v

# Real-engine integration tests:
# Pilot 1: Third-person movement & camera
pytest tests/integration/test_pipeline_execution.py -v

# Pilot 2: Health and damage, invulnerability window, and exactly-once death
pytest tests/integration/test_health_damage_pipeline.py -v

# Step 3 Task 1: Pickup collection, health/stamina effects, exactly-once events
pytest tests/integration/test_pickup_pipeline.py -v

# Step 3 Task 2: Player composition, scene integration, kinematics and health parity
pytest tests/integration/test_composition_pipeline.py -v

# Run entire test suite
pytest -v
```

## 4. Discovered Environment Status
- **Operating System:** Windows 11 Build 10.0.26100 (x64)
- **Python:** 3.14.6
- **Unreal Engine:** 5.7.4 installed at `E:\UE\UE_5.7` (verified runnable with `UnrealEditor-Cmd.exe` and `PythonScriptPlugin`)
- **Unity Engine:** Not installed locally in standard locations (adapter implemented and unit-tested; real-engine execution marked UNVERIFIED).
- **GitHub Remote:** `https://github.com/Ruturaj147990/GameForge.git`


