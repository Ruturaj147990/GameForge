# GameForge Integration Test Report

Updated 2026-10-30T17:20Z (Claude Code). This report only collects results that were actually executed. No new
engine runs were executed in the 2026-10-30 Claude planning session; its results are carried over from the audit.

## Latest executed results
| Date | Command | Result | Evidence |
|---|---|---|---|
| 2026-10-30 | `python -m pytest tests/unit/` | 411 passed, exit 0 | `reports/AUDIT_M1_M10_2026-10-30.md` §4 |
| 2026-10-30 | `python -m pytest graders/protected/` | 45 passed, exit 0 | same |
| 2026-10-30 | `scripts/audit_rebuild_games.py` | 4 games × 8 stages OK | `reports/audit_20261030_pipeline_runs.json` |
| 2026-10-30 | `scripts/verify_real_input_packaged.py` | 3/3, 4/4, 7/7, 4/4; 0 leaked processes | `reports/packaged_real_input_summary.json` |
| 2026-10-30 | M8 completion checks | 6/6 PASS | `reports/audit_m8_completion.json` |
| 2026-10-30 | M9/M10 completion checks | 10/10 PASS | `reports/audit_m9_m10_completion.json` |

## Required for every future WP (template)
Command · exit code · log path · read-back JSON · screenshot path · packaged check (if game-affecting) ·
unit + protected counts.
