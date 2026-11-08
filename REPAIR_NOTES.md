# GameForge source repair notes

This archive contains a focused, source-level repair pass over the supplied ZIP.
It is not a claim that every defect in the entire application has been eliminated.

## Changes made

- Removed the obsolete fixed executable allowlist from direct terminal command parsing.
- Made the host-native shell the default for terminal commands and exposed the shell choice in the run-command tool schema.
- Made unknown permission-mode values fail closed instead of silently falling back to Auto; retained legacy aliases.
- Added POSIX absolute-path detection to command risk classification.
- Hardened multi-file manifest execution:
  - validates every target path before reading snapshots,
  - rejects traversal and symlink targets,
  - detects dependency cycles instead of silently guessing an order,
  - implements delete operations,
  - forwards permission/approval state instead of hardcoding approval,
  - fixes the propose-edit/apply-edit two-stage flow and preserves full-file replacements recovered from prose,
  - rolls back only files actually modified,
  - uses atomic file replacement for restoration,
  - reports rollback failures accurately.
- Connected LLM strategy evaluation to prompt-to-GDS selection when a model callback is available.
- Validates model-selected template IDs and rejects templates that conflict with explicit game requirements.
- Corrected scratch GDS generator provenance so deterministic fallback is not mislabeled as model-generated.
- Added a truthful fallback provenance value to the GDS schema.
- Corrected the semantic plan fallback's final evidence-report tool from `play_game` to `write_file`/`verify_disk` and made its fallback provenance explicit.
- Fixed symlink-safe file/directory cleanup and made quarantine results truthful.
- Added fallback project discovery when the configured projects root returns no projects.
- Updated AgentRuntime to drain multiple validated native tool calls returned in one provider response instead of discarding all but the first.

## Verification performed

- Python source-wide syntax compilation: PASS across 318 Python source files.
- Focused regression suites: 134 passed, 0 failed.
- Focused suites covered command broker, multi-file manifest, prompt-to-GDS, plan generation, context usage and several agent-runtime regressions.

## Verification limitations

- The full desktop/UI test suite could not be run in this review environment because PySide6 is not installed.
- Unreal Engine build, cook, package, editor integration and runtime tests could not be run because this environment does not contain the user's Windows Unreal Engine installation.
- The supplied archive does not contain Git metadata, so this pass could not inspect the live branch, uncommitted changes or compare against the user's current working tree.
- No local Ollama models or the user's Windows process environment were available for end-to-end validation.
- Therefore this is a tested improvement pass, not a guarantee of zero bugs. Run the full Windows acceptance suite and UE 5.7.4 integration/package tests before replacing the working project.

## Modified files

- `src/gameforge_ide/backend/models/modes.py`
- `src/gameforge_ide/backend/tools/terminal_tools.py`
- `src/gameforge_ide/backend/tools/gateway.py`
- `src/gameforge_ide/backend/tools/command_broker.py`
- `src/gameforge_ide/backend/agent/multi_file_manifest.py`
- `src/gameforge_ide/backend/agent/runtime.py`
- `src/gameforge_ide/backend/agent/plan_generator.py`
- `src/gameforge_ide/design/prompt_to_gds.py`
- `src/gameforge_ide/design/template_registry.py`
- `src/gameforge_ide/design/gds.py`
- `src/gameforge_ide/core/process_manager.py`
- `src/gameforge_ide/desktop/services/projects_service.py`
- `tests/unit/test_command_broker.py`
- `tests/unit/test_multi_file_manifest.py`
- `tests/unit/test_prompt_to_gds.py`
- `tests/unit/test_ai_agent_orchestration_improvements.py`
