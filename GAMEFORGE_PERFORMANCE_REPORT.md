# GameForge Performance Report

Updated 2026-10-30T20:00Z (Claude Code).

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
Packaged Win64 games are ~860 MB each (Development). Packaged games have no profiling data yet.

## First engine profile (M19, 2026-10-30) — `scripts/perf_village_pie.py` → `reports/m19_perf_village.json`
Generated forest village (landscape 127×127 vertices with 3 paint layers, ~270 PCG instances, 3 kit houses, Sky
Atmosphere + clouds + fog), editor PIE, `-RenderOffscreen` 1280×720, Development editor, `csvprofile` for ~10 s:

| Stat | Mean | p95 | Max |
|---|---|---|---|
| FrameTime | 8.34 ms (≈120 fps) | 8.97 ms | 18.6 ms |
| GameThreadTime | 3.70 ms | 4.61 ms | 7.47 ms |
| GPUTime | 2.00 ms | 2.10 ms | 2.16 ms |
| RenderThreadTime | 0.09 ms | — | 2.61 ms |

1,190 frames. This is an editor-PIE measurement at offscreen resolution, so treat it as a regression baseline,
not a shipping number. Next: the same capture in a packaged build (`-csvprofile` on the command line), plus
Insights traces and per-game budgets.
