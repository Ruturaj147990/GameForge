# Antigravity handoff — small, scoped follow-ups

Updated 2026-10-27 (second build-out). Read `context.md` first, then this file.
Done and verified, so don't redo them: live editor link, toolchain, recipe pipeline (tic-tac-toe, Gomoku,
N-in-a-row, Connect Four), free-form pipeline with repair ladder and vision review, IDE approval cards,
Mission Control, Hosted Models dialog, cancel, `/game`, storage hygiene, scalable explorer, idle-editor
reaper, native tool calling, hosted tier, efficiency budgets.

**Do not weaken any gate.** Completion stays evidence-based, approvals stay UI-only, simulations stay labelled
`simulated: True`, generated code keeps passing `authoring.safety_scan`, and vision review stays advisory.

## How to verify anything you change

```powershell
$env:TEMP="E:\gameforge_step1\scratch\pytest_os_temp"; $env:TMP=$env:TEMP
python -m pytest tests/unit/ graders/protected/ -q                      # expect 363+ passed
python scripts/live_editor_contract_test.py <fresh>\GFProbe.uproject      # expect 16/16, graceful stop
python scripts/run_game_pipeline.py --name TicTacToe                      # expect REPORT ... OK
python scripts/run_game_pipeline.py --name FourInARow --title "Four in a Row" --size 7 --win 4 --ai greedy --gravity
python scripts/run_freeform_game.py --prompt "create a click the cubes game" --title "Cube Clicker" --reference
python scripts/ide_prompt_to_game_e2e.py --workspace E:\GameForge\ide_e2e_ws   # expect verdict ok
python scripts/ide_resource_benchmark.py --workspace E:\GameForge\ide_bench_ws # expect no violations
python scripts/native_tool_selftest.py                                     # expect 4/4 SELF_TEST_PASSED
```

Automation that closes the IDE must set `win.confirm_on_close = False` first. The IDE now only prompts on close when
a build or agent turn is running, but tests should never depend on that.

## Remaining small tasks

None. Items 1, 3, 13 and 15–18 were completed on 2026-10-27 (third build-out):
exposure fix (grid + free-form cameras), approval-card collapse + elapsed time, simulations moved to
`tests/doubles/` with a real `unreal/live_operations.py` backend (live-verified), Mission Control thumbnails +
review verdicts, `/game` flags (`--size --win --hotseat --gravity --ai --title`), framework `SpawnText`/`SetText`,
and price validation in the Hosted Models dialog.

## Bigger items reserved for a heavy-model session (not quick fixes)

- General multi-task DAG planner for arbitrary coding requests (WP3 remainder).
- New recipe families: top-down arena, platformer, card game, each with automation tests and packaged self-test.
- C++ editor-plugin operations for Blueprint graph nodes and UMG widget trees (catalogue rows B2, J1).
- Free-form quality: enable a hosted heavy model (File → Hosted Models…) and re-run whack-a-mole; compare against the 9B result in `E:\GameForge\projects\WhackAMole\Saved\GameForge\pipeline_report.md`.
- Advanced domains (catalogue rows E1–N1): landscape/PCG, characters/animation, Sequencer, MetaSound, Niagara, multiplayer.
