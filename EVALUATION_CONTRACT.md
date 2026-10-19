# GameForge evaluation contract v0.1

## Principle
A task is not passed merely because the model produced plausible text or the project compiles. Grade in layers and record the first failing layer, while still preserving later diagnostics when safely possible.

## Required layers
1. **Clean-start verification:** restore a known project snapshot; record engine, project, dependency, runner, and hardware versions.
2. **Policy/static checks:** enforce allowed write paths; reject test/grader tampering, disabling tests, forbidden settings changes, and unauthorized network use.
3. **Build/import:** capture exit code, compiler/import errors, duration, and relevant logs.
4. **Automated tests:** run defined visible and hidden unit/integration tests; hidden tests never enter the model workspace.
5. **Behavior probes:** replay specified input traces; capture relevant state/time-series; apply task-specific tolerances.
6. **Saved-asset checks:** inspect assets using engine-supported APIs/commandlets where needed; verify component presence, references, state/graph configuration, and absence of missing scripts/assets.
7. **Performance checks:** apply only the task's declared budgets on a declared reference machine class.
8. **Regression checks:** rerun affected existing tests and task-specific baseline behavior.
9. **Visual/gameplay review:** only where needed; any vision-model score must be calibrated against a documented human-labelled sample and reported separately from deterministic results.

## Result vocabulary
- `PASS`: all mandatory layers passed.
- `PARTIAL_BUILD`: build passed but one or more required later layers failed.
- `FAIL_BUILD`: build/import failed.
- `POLICY_FAIL`: policy violation, including grader/test tampering.
- `HARNESS_INVALID`: the task/runner failed independently of the model.
- `FLAKY_QUARANTINED`: repeated results vary beyond the defined tolerance; exclude from headline score until fixed or explicitly report as unresolved.

## Controller probe guidance
Use fixed timestep/seed where possible and tolerance bands rather than exact equality. Example checks include jump apex, time to apex, speed cap, acceleration response, stop distance, slope/step handling, coyote time, jump buffering, camera collision, and input response latency. Each threshold must come from the task specification or reviewed reference measurements—not be guessed after seeing a model result.

## Required per-run record
Benchmark/task version; logical task ID and engine variant; engine/toolchain versions; model ID/version; harness/tool list; prompt/context policy; tool/token/step/time budget; seed and timestep; build/test/probe/asset/performance outcomes; regression result; final diff; trace/log references; estimated cost; run status; known harness warnings.

## Baseline fairness
Use identical tasks, starter projects, allowed tools, time/tool budgets, and scoring. Publish the harness card. Repeat selected tasks to estimate run-to-run variance. Never compare a tool-rich agent against a tool-poor model without labeling the difference.
