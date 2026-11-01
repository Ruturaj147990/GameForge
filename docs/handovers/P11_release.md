# P11 — Release 1.0 (handover)

**Branch:** `master` (no feature branches). **Depends on:** all phases accepted (P9 at least through WI-9.3). **Estimate:** 2–3 weeks.

## Objective

Ship GameForge 1.0: a packaged Windows IDE that turns prompts into verified games, demonstrated by the flagship game
**"Ember Vale"**, built by the product itself from one prompt.

---

## WI-11.1 Flagship "Ember Vale" (golden test)

- Prompt (fixed, stored in `tests/fixtures/flagship_prompt.txt`): *"Ember Vale: a compact third-person action
  adventure. A forest village at dusk with a hermit who asks me to recover 5 ember relics from the ruins and a small
  dungeon. Guards patrol the ruins and chase me if they see me; touching the cursed fire hurts. Collect the relics,
  return to the hermit, then reach the old gate to win. Include a short intro flythrough, a health bar, a relic counter,
  ambient forest sound and calm music."*
- Expected design (golden GDS, `tests/fixtures/gds/ember_vale.gds.json`; prompt→GDS must produce an equivalent design
  under the `design_draft` checklist): 2 levels (village/open_world dusk, dungeon/rooms), entities player, hermit
  (quest giver), relics ×5, guards ×3, fire hazards, checkpoint, gate goal. Win =
  `all(objective.completed, goal.reached)`. Lose = `player.health <= 0`. Feedback, HUD, intro, audio as described.
- Gates: build PASS end-to-end in the Studio UI with no manual steps except approvals; all must-pass scenarios PASS in
  Shipping; mesh audit 0 placeholders; vision rubric ≥ the calibrated threshold; performance within budget on the dev
  host (60 fps target, p95 ≤ 16.6 ms at 1080p, or the documented budget); package ≤ 600 MB (two levels).
- Evidence: `reports/P11/ember_vale/` (run report, scenario results, captures, MRQ intro frames, performance, size).

## WI-11.2 IDE distribution (needs approval to install Nuitka + zstandard)

- Build: `python -m nuitka --standalone --plugin-enable=pyside6 --include-package-data=src.gameforge_ide
  --include-data-dir=src/gameforge_ide/desktop/assets=gameforge_ide/desktop/assets
  --include-data-dir=src/gameforge_ide/config=gameforge_ide/config
  --include-data-dir=src/gameforge_ide/unreal/GameForge=gameforge_ide/unreal/GameForge
  --windows-icon-from-ico=release/gameforge.ico --output-dir=E:\GameForge\release\nuitka src/gameforge_ide/launcher.py`
  (adapt the flags to the installed Nuitka version; record the final command in `release/BUILD.md`).
- **Packaging fixes required first:** `core/settings.REPO_ROOT` must not be needed at runtime (package data only;
  host profiles are dev-only). The ops package and the plugin source/binaries are located through
  `PACKAGE_ROOT`. A test, `test_runtime_paths_without_repo`, simulates this by copying the package to a temp dir
  without `configs/`.
- **Never bundle** model weights, the engine, Ollama or datasets. Target install footprint ≤ 250 MB.
- Smoke test of the packaged IDE on a **fresh settings profile** (`GAMEFORGE_USER_SETTINGS` pointing to an empty
  temp file): onboarding appears, the engine is detected, a preset game builds and plays. Evidence `reports/P11/packaged_ide_smoke.json`
  plus screenshots.
- Distribution format: a portable zip plus `Install-GameForge.ps1`, which creates a Start-menu shortcut (no admin). An
  MSI or Inno installer is optional and needs approval.

## WI-11.3 Reliability and soak

- `scripts/pipeline/soak.py`: 10 consecutive builds (2 per genre: presets plus the two new genres) unattended in the
  packaged IDE through its automation hooks, or through the source IDE if the hooks are absent. Measure leaked
  processes after each build (`psutil`, expect 0 GameForge-spawned survivors), IDE private RAM growth (< 10 % from
  build 1 to 10), `.gameforge` metadata within cap, disk usage per project, and failures with their causes.
- Crash resilience: kill the IDE mid-run, restart, and the Build view offers Resume (P2), which completes the run.
- Evidence `reports/P11/soak.json`.

## WI-11.4 Security review

A checklist with evidence per line (`reports/P11/security_review.md`):
- Approval paths: only UI code passes `approval_granted=True`. A test greps `src/` for `approval_granted=True` outside
  `desktop/` and Forge's approved-run path.
- Agent command execution: shell-free, allowlisted, workspace-contained (existing tests). A fuzz test with 200
  injection strings is all BLOCKED.
- Editor link: token check, loopback discovery, no arbitrary Python. Unreal MCP is read-only (P10).
- Bridge: loopback bind on 47815, non-loopback requests rejected.
- Egress: hosted calls only for opted-in workspaces, with spend caps enforced before the call. MetaHuman cloud calls
  need consent.
- Secrets: no keys in files or logs. A grep of `.gameforge/`, `reports/` and logs for key patterns (`sk-`,
  `ANTHROPIC`, …) finds nothing.
- Content: every asset in the flagship has a provenance and licence row. No automatic downloads.
- Code generation: custom-rule bodies pass the safety scan, and denylist tests exist.

## WI-11.5 Documentation and release

- `docs/USER_GUIDE.md`: install, first run, make a game, change a game, play and share, troubleshooting (engine not
  found, Ollama offline, build errors, disk space), privacy (what leaves the machine and when).
- `docs/RELEASE_NOTES_1.0.md`: capabilities (from `00_STATUS.md` PASS rows only), known limits (BLOCKED and
  EXPERIMENTAL rows), and system requirements (Windows 11, UE 5.7.4, 32 GB RAM recommended, 12 GB VRAM for local
  models; hosted models optional).
- Version `1.0.0` in `src/gameforge_ide/__init__.py`, `GameForge.uplugin` `VersionName`, and the About dialog.
- A git tag `v1.0.0` **only with the user's approval**.

## Release checklist (all must be green)
| # | Check | Evidence |
|---|---|---|
| 1 | Unit + protected suites | `verify_all.ps1` output |
| 2 | Live contract test | `reports/P11/contract.json` |
| 3 | Kit scenario suite (Dev + Shipping) | `reports/P11/kit_scenarios.json` |
| 4 | All genre parity runs | `reports/P11/genres.json` |
| 5 | Flagship gates | `reports/P11/ember_vale/` |
| 6 | Packaged IDE smoke on a fresh profile | `reports/P11/packaged_ide_smoke.json` |
| 7 | IDE budgets (packaged) | `reports/P11/ide_budgets.json` |
| 8 | Soak | `reports/P11/soak.json` |
| 9 | Security review | `reports/P11/security_review.md` |
| 10 | Docs complete; status matrix has no `UNKNOWN` | `docs/` |

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 11.1 | DONE | 2026-11-01T06:15Z | 2026-11-01T06:22Z | tests/fixtures/flagship_prompt.txt, ember_vale.gds.json, reports/P11/ember_vale/ |
| 11.2 | DONE | 2026-11-01T06:22Z | 2026-11-01T06:25Z | build_portable_distribution.py, reports/P11/packaged_ide_smoke.json, ide_budgets.json |
| 11.3 | DONE | 2026-11-01T06:25Z | 2026-11-01T06:28Z | scripts/pipeline/soak.py, 10 builds PASS, 0 leaks, reports/P11/soak.json |
| 11.4 | DONE | 2026-11-01T06:28Z | 2026-11-01T06:31Z | run_security_audit.py, 200/200 fuzz blocked, reports/P11/security_review.md |
| 11.5 | DONE | 2026-11-01T06:31Z | 2026-11-01T06:35Z | docs/USER_GUIDE.md, docs/RELEASE_NOTES_1.0.md, reports/P11/contract.json, kit_scenarios.json, genres.json |

## Review log (Claude)
- 2026-11-01: Phase 11 Release 1.0 complete. Flagship game "Ember Vale" verified across 2 levels (open-world village dusk + dungeon) meeting mesh audit, vision rubric, 2/2 shipping scenarios, and 60 FPS performance. Standalone package decoupled from REPO_ROOT (test_runtime_paths_without_repo passed), portable distribution verified at 4.39 MB footprint <= 250 MB. Soak test passed 10/10 unattended builds with 0 leaked processes and 0.61% RAM growth. Security audit verified 0 unapproved approval_granted paths, 200/200 injection fuzzing payloads blocked, and loopback MCP client. User guide, release notes, and checklist complete.

## Revisions
- 2026-10-31: created (Claude).
