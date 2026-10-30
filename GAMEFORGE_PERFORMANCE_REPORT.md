# GameForge Performance Report

Updated 2026-10-30T17:20Z (Claude Code).

## Shipped IDE budgets (measured earlier by `scripts/ide_resource_benchmark.py`, from the source tree)
| Metric | Budget (proposed) | Last measured | Status |
|---|---|---|---|
| Cold start | ≤ 2.0 s | 0.98 s (2026-10-27) | PASS |
| Idle private RAM | ≤ 150 MB | 89.8 MB | PASS |
| Idle CPU | ≤ 1 % | 0.78 % | PASS |
| Child processes at idle | 0 | 0 | PASS |
| Explorer stall on a 30k-file folder | ≤ 50 ms | 37 ms | PASS |
| Installed size, handle count, leak test, packaged-IDE measurement | define | not measured | NOT VERIFIED (no PyInstaller; installing it needs approval) |

## Development/generation resources (host)
Ryzen 5 7600X, 32 GB DDR5, RX 7700 XT 12 GB. Measured LLM speeds: 4B 102.8 tok/s, 9B 63.9, 27B 5.4, llama 77.3.
Rule: no UE Editor run concurrently with a >6 GB VRAM model job.

## Game builds
Packaged Win64 games are ~860 MB each (Development). There is no profiling data yet. M19 adds `-csvprofile`,
Insights traces and per-game budgets.
