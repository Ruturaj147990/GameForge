# Testing, Verification and Evidence

**Owner:** Claude. **Consolidated:** 2026-10-31 from `ANTIGRAVITY_HANDOFF.md` (verification commands),
`GAMEFORGE_INTEGRATION_TEST_REPORT.md` and `GAMEFORGE_PERFORMANCE_REPORT.md`. Both reports were moved to
`docs/history/`, where the full execution history stays.

## 1. Evidence rules

1. A capability is PASS only with an evidence file **produced by a real run** (engine, packaged game, or the real IDE)
   in `reports/`. Unit tests are necessary but never sufficient for engine capabilities.
2. Nothing under `tests/doubles/` or marked `simulated: True` is evidence.
3. Every check must be able to fail. Add a control when a pass could happen by chance (examples: the dense PCG
   exclusion control in the M8 v2 village; the P3 teleport and impossible-expectation controls).
4. Read state from the live object or subsystem (read-back ops, `pie_actor_state`, scenario result files), never from
   the return value of the op that caused the change.
5. Evidence files follow the shape `{"checks": {...}, "steps": {...}, "finished": ISO, "project": path, ...}`, with
   failures preserved. A failed run's evidence is kept (renamed `*_runN.json`) when it explains a fix.
6. Statuses: `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, `NOT VERIFIED`, `EXPERIMENTAL`, `PLANNED`.

## 2. Test layers

| Layer | What | Where | When |
|---|---|---|---|
| Unit | pure Python logic, schemas, adapters, UI widgets with `qapp` | `tests/unit/` (494 tests on 2026-10-31) | every change |
| Protected oracles | benchmark graders (never edited) | `graders/protected/` (45 tests) | every change |
| Engine contract | the live editor link (16 checks) | `scripts/engine/live_editor_contract_test.py` | any change to `unreal/`, ops or the plugin |
| Engine demos | one capability each, on disposable probe copies | `scripts/engine/demo_*.py` → `reports/*.json` | changes to that capability |
| In-engine automation | C++ automation tests (`GameForge.<Game>.*`, `GameForge.Kit.*`) | generated projects, kit testbed | every build run |
| Scenarios (from P3) | injected-input playtests in packaged builds | `qa/runner.py`, Forge `scenario` step | every build run |
| Packaged real input | Win32 SendInput smoke (secondary) | `scripts/engine/verify_real_input_packaged.py` | release checks |
| IDE budgets | start time, RAM, CPU, child processes | `scripts/ide/ide_resource_benchmark.py` | UI changes |
| Usability walk (from P4) | scripted Studio flow | `tests/integration/test_studio_walk.py` | UI changes |
| Evals (from P9) | model performance on GameForge tasks | `src/gameforge_ide/evals/` | model or prompt changes |

## 3. Commands

```powershell
# Every session (the sandbox may deny C: temp)
New-Item -ItemType Directory -Force E:\gameforge_step1\scratch\pytest_os_temp | Out-Null
$env:TEMP="E:\gameforge_step1\scratch\pytest_os_temp"; $env:TMP=$env:TEMP

python -m pytest tests/unit/ -q -p no:cacheprovider          # expect: all pass (494 on 2026-10-31)
python -m pytest graders/protected/ -q -p no:cacheprovider   # expect: 45 passed

# After P0: one command for every gate
powershell -File scripts\verify_all.ps1 -Quick               # unit + protected + op catalogue drift
powershell -File scripts\verify_all.ps1                      # + live contract + demo + IDE benchmark

# Engine and pipeline checks (paths after P0 WI-0.11; before P0 they live directly under scripts\)
python scripts\engine\live_editor_contract_test.py --disposable          # 16/16, graceful stop
python scripts\pipeline\run_game_pipeline.py --prompt "create a tic tac toe game"
python scripts\pipeline\ide_prompt_to_game_e2e.py --workspace E:\GameForge\ide_e2e_ws
python scripts\ide\ide_resource_benchmark.py --workspace E:\GameForge\ide_bench_ws
python scripts\ide\native_tool_selftest.py                               # 4/4 SELF_TEST_PASSED (needs Ollama)
```

Automation that closes the IDE must set `win.confirm_on_close = False` before `win.close()`.

## 4. Baselines (latest measured)

| Metric | Value | Date | Source |
|---|---|---|---|
| Unit / protected tests | 494 / 45 pass | 2026-10-31 | this audit |
| IDE cold start | 0.81–1.66 s (budget < 2.5 s) | 2026-10-27 | `reports/ide_resource_benchmark.json` |
| IDE idle private RAM | ~90 MB (budget ≤ 300 MB) | 2026-10-27 | same |
| IDE idle CPU | 0.21–0.57 % (budget < 1 %) | 2026-10-31 | context log |
| Explorer worst stall on a 30k-file folder | 37 ms | 2026-10-27 | context log |
| Village PIE frame time | 8.34 ms mean / 8.97 p95 (GT 3.70, GPU 2.00) | 2026-10-30 | `reports/m19_perf_village.json` |
| Development package size | ~860 MB per game | 2026-10-28 | milestone reports |
| Prompt → packaged tic-tac-toe in the IDE | 102 s | 2026-10-27 | context log |

## 5. Disposable projects

Engine runs use copies under `E:\GameForge\validation\<phase>_<topic>_<yyyymmdd>\` (`_harness.disposable_probe` after
P0). They are disposable: delete them when their evidence is recorded and the user has not asked to keep them. Never
run destructive checks against `GFProbe` itself or against a user project.
