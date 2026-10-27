# GameForge Reality Audit and First Live Engine Link — 2026-10-27

Scope: compare what `context.md` reports against the code, then replace the simulated Unreal link with a real one and prove it on UE 5.7.4 (CL 51494982).

## 1. Findings: simulated components reported as verified

| Component | Reported (context.md, 2026-10-27T15:15) | Actual behaviour in source | New status |
|---|---|---|---|
| `unreal/transport.py` `PythonRemoteTransport` | "loopback EditorTransport adapter" | Opened no socket; `send_operation` returned a hard-coded `ok: True` envelope | `[SUPERSEDED]` as evidence; now returns `simulated: True` |
| `unreal/supervisor.py` `handshake()` | "handshake" | Returned literal `"5.7.4"` and `token_verified: True` without contacting an editor | `[SUPERSEDED]`; marked `simulated: True` |
| `unreal/operations.py` `UnrealOperationsLibrary` | "6 genuine read-backs" | Actors and assets kept in Python dicts; read-backs read those dicts | `[SUPERSEDED]`; docstring says SIMULATION |
| `unreal/physics_probe.py` | "Chaos-compliant gravity drop tests" | Python Euler integrator; Unreal never runs | `[SUPERSEDED]` as engine evidence |

The unit tests for these modules still pass and remain useful as offline test doubles. They are not evidence of engine capability (Blueprint v2 rule 10).

## 2. Real link implemented

| File | Purpose |
|---|---|
| `src/gameforge_ide/unreal/live_editor.py` | `LiveEditorLink`: prepares the project (remote exec bound to 127.0.0.1, TTL 0, Python plugins enabled), installs the op library, writes a 256-bit session token, launches/stops the editor, discovers with the engine's own `remote_execution.py`, accepts only the node whose `project_root` matches, runs one call at a time with a timeout, and classifies `EDITOR_CRASHED`/`EDITOR_LINK_LOST` |
| `src/gameforge_ide/unreal/GameForge/Content/Python/gameforge_ops.py` | 18 in-editor operations with a token check (`hmac.compare_digest`), transactions, read-back and a JSON envelope. SHA-256 `2666313805574335105a716222e1cc9fb7af9d42c631de98718a817dfaec33d9` |
| `scripts/live_editor_contract_test.py` | Live contract test: launch → 13 operations with read-back checks → forged-token check → stop → JSON evidence |
| `tests/unit/test_live_editor_link.py` | 9 offline tests (argument injection safety, envelope parsing, fail-closed paths, project preparation) |

## 3. Live runs on UE 5.7.4

| Run | Flags | Result | Evidence |
|---|---|---|---|
| 1 | `-nullrhi` | Discovery, handshake and `new_level` pass; `spawn_actor` **crashed the editor** (`EXCEPTION_INT_DIVIDE_BY_ZERO`, UnrealEditor-Engine.dll). The client then mis-reported `ConnectionResetError`; fixed to classify as `EDITOR_CRASHED` | `E:\GameForge\validation\live_editor_probe_20261027\editor_run1_nullrhi_crash.log`, `probe_run1_nullrhi_*` |
| 2 | `-RenderOffscreen` | 9/13. Real bugs found: `new_level` on an existing path; Python type passed where a `UClass` was needed; `Blueprint.status` is protected from Python on 5.7.4; saving an untitled level | `...\live_editor_probe_20261027\Saved\GameForge\contract_result.json`, `contract_run2_stdout.txt` |
| 3 | `-RenderOffscreen`, fresh project | **13/13 pass**; forged token refused; discovery 8.0 s; `.umap` + 2 `.uasset` files on disk; no leaked `UnrealEditor.exe` | `E:\GameForge\validation\live_editor_probe_20261027b\Saved\GameForge\contract_result.json` (SHA-256 `982a040754d24c90ad33b9c915bb52d64bc9d290aff74c6fcb852c7c0075735a`) |

**Caveats from run 3**

- `viewport.png` (SHA-256 `29b9ad28…fcfc4`) exists but is entirely black: the new level has no lights or sky. The contract proves the capture path works, not the image content.
- The editor exit code is 1 because it was terminated rather than quit gracefully. Next step: request `quit_editor` through the link before terminating.
- `compile_blueprint` was verified on an empty Actor Blueprint only (generated class present, no log errors).

## 4. Test suite

- `python -m pytest tests/unit/ -q` → **250 passed** (241 previous + 9 new), 2 upstream deprecation warnings.
- `python -m pytest graders/protected/ -q` → **45 passed**.
- Both runs used `TEMP`/`TMP` set to `E:\gameforge_step1\scratch\pytest_os_temp`.
