# GameForge — Project Charter (Step 1)

**Status:** Draft v0.1 — requires review by the project owner and game-engine reviewers.

## Mission
Build a specialized game-development model that can understand, create, modify, test, and repair complete gameplay systems in real Unity and Unreal projects. The first product milestone is proven model capability, not a Windows application.

## Intended outcome
A model that reliably beats strong general-purpose models on a disclosed and reproducible set of game-development tasks, with held-out tasks, real engine execution, and clear reporting of costs and tool access.

## First milestone
Build and validate a small cross-engine benchmark before committing to large-scale model training.

## In scope for Step 1
- Define operational success criteria.
- Define a benchmark task schema and 30 logical T2/T3 task specifications.
- Choose six pilot tasks for detailed specification.
- Define grading layers, report fields, and baseline protocol.
- Establish provenance/licensing fields and a decision log.

## Out of scope for Step 1
- Training a frontier model from scratch.
- Building the finished Windows desktop application.
- Promising that one universal Game IR can represent every game system.
- Building a full text-to-3D / rigging / animation pipeline before simple engine-native tasks are validated.
- Making a public “world's number one” claim without independent, held-out evidence.

## Operational definition of success
For a fixed benchmark version, engine version, harness, tool budget, context policy, and model version, the system has a high repeatable pass rate on hidden tests, runtime behavior probes, saved-asset checks, and regression suites. Results include pass@1, layer-by-layer completion, regression rate, paired Unity/Unreal parity, latency, tool calls, and cost. The comparison is valid only when competing models receive equivalent task setup and budgets.

## Product principles
1. Test behavior, not merely generated text or compilation.
2. Use real engine builds/editor APIs in the final grading loop.
3. Report partial success honestly.
4. Preserve rollback, diffs, logs, and provenance.
5. Separate source-derived assumptions from measured results.
6. Specialize useful reasoning rather than deliberately removing general competence.
7. Treat Game IR, specialist agents, and model architecture as hypotheses to benchmark.

## Proposed first acceptance gate
Do not expand beyond the pilot until two experienced reviewers agree that each pilot prompt is unambiguous, the grader checks the intended behavior, project reset is reproducible, hidden tests are isolated, and repeated runs quantify any flaky checks.
