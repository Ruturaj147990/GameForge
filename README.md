# GameForge

GameForge is a Windows desktop platform that turns a natural-language game idea into a **playable, verified Unreal
Engine 5 game**. The game can then be changed with further prompts. It plans the work, writes a reviewable Game Design
Spec, builds the game from a tested gameplay kit (with generated code only where needed), assembles levels in the
live Unreal Editor, tests the game by replaying input against the packaged build, and reports the evidence.

> Status (2026-10-31): five genres go from prompt to packaged game, and the engine layer for worlds, materials, props,
> VFX, audio, AI, quests and cinematics is verified in Play-In-Editor. The roadmap to 1.0 is in
> [`docs/04_ROADMAP.md`](docs/04_ROADMAP.md). Live status, with evidence, is in [`docs/00_STATUS.md`](docs/00_STATUS.md).

## Requirements (current development host)

- Windows 11, Unreal Engine **5.7.4** (Epic Launcher install, detected automatically after P0), Visual Studio 2022
  C++ toolchain.
- Python 3.14, PySide6 6.12, numpy, Pillow (`pip install -r requirements.txt`).
- Local models through Ollama (four GameForge models), or an opt-in hosted provider.
- Disk: games and artifacts are stored on the drive configured in Settings (the development host uses `E:`).

## Run

```powershell
python -m src.gameforge_ide.launcher            # desktop IDE
python -m src.gameforge_ide.launcher --serve    # loopback bridge for the Unreal plugin (development)
```

## Test

```powershell
$env:TEMP="E:\gameforge_step1\scratch\pytest_os_temp"; $env:TMP=$env:TEMP
python -m pytest tests/unit/ -q
python -m pytest graders/protected/ -q
```

More commands are in [`docs/08_TESTING_AND_EVIDENCE.md`](docs/08_TESTING_AND_EVIDENCE.md).

## Repository map

| Path | Contents |
|---|---|
| `src/gameforge_ide/` | The product: desktop IDE, agent, design/build/QA pipelines, Unreal integration and plugin |
| `src/gameforge_ide/unreal/GameForge/` | Unreal plugin: `GameForgeEditor` (editor ops) and `GameForgeRuntime` (gameplay kit) |
| `src/gameforge_bench/` | Benchmark and model-training product line (frozen; see `docs/README.md`) |
| `docs/` | Knowledge base: architecture, audit, research, roadmap, UX spec, engine notes, handovers |
| `reports/` | Evidence from real runs and model-training reports |
| `scripts/` | Engine demos, pipeline runners, IDE benchmarks, model tooling |
| `tests/` | Unit and integration tests; `graders/protected/` holds protected benchmark oracles |

## For agents

Read `AGENTS.md` first, then `context.md`. Implementation agents start with `ANTIGRAVITY_HANDOFF.md`.
