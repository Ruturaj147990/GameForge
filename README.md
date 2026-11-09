# GameForge

GameForge is a desktop game-creation platform that turns any natural-language game prompt into a **playable, verified Unreal Engine 5 game** and iteratively refines it through natural-language prompts. Rather than returning static premade template games, GameForge semantically analyzes the prompt, synthesizes a full Game Design Specification (GDS) with custom entities, weapons, abilities, physics, state machines, rules, HUD bindings, and architectural C++ subsystems, composes multi-zone 3D levels and procedural assets in Unreal Engine, compiles generated C++ gameplay handlers, validates the build through automated input replay, and reports verifiable evidence.

> Status (v1.0.0): Dynamic prompt-to-game synthesis across arbitrary game mechanics and spatial archetypes, backed by unit/integration verification, live Unreal Editor bridge operations, and standalone packaging. The roadmap to 1.0 is in [`docs/04_ROADMAP.md`](docs/04_ROADMAP.md). Live status, with evidence, is in [`docs/00_STATUS.md`](docs/00_STATUS.md).

## Requirements

- Windows 11, Unreal Engine **5.7.4** (Epic Launcher install, detected automatically), Visual Studio 2022 C++ toolchain.
- Python 3.10+, PySide6 6.6+, FastAPI, Uvicorn, HTTPX, NumPy 1.24+, Pillow 10+, psutil (`pip install -r requirements.txt`).
- Local models through Ollama (four GameForge specialist models), or an opt-in hosted provider.
- Disk: games and artifacts are stored on the drive configured in Settings / host profile (`configs/host_profiles/`).

## Run

```powershell
python -m src.gameforge_ide.launcher            # desktop IDE
python -m src.gameforge_ide.launcher --serve    # loopback bridge for the Unreal plugin (development)
```

## Verify & Test

```powershell
$env:TEMP="$PWD\scratch\pytest_os_temp"; $env:TMP=$env:TEMP
python scripts/pipeline/eval_prompt_to_gds.py
python scripts/test_prompt_to_game_distinctness.py
```

More commands are in [`docs/08_TESTING_AND_EVIDENCE.md`](docs/08_TESTING_AND_EVIDENCE.md).

## Repository map

| Path | Contents |
|---|---|
| `src/gameforge_ide/` | The product: desktop IDE, agent runtime, dynamic design/composer/codegen/QA pipelines, Unreal integration and plugin |
| `src/gameforge_ide/unreal/GameForge/` | Unreal plugin: `GameForgeEditor` (editor ops) and `GameForgeRuntime` (extensible C++ gameplay runtime) |
| `src/gameforge_bench/` | Benchmark and model-training product line (see `docs/README.md`) |
| `docs/` | Knowledge base: architecture, roadmap, UX spec, engine notes, content/models, testing, handovers |
| `configs/` & `schemas/` | Model manifests, routing tables, acceptance schemas, and JSON contracts |
| `scripts/` | Engine verification suites, pipeline runners, IDE benchmarks, model tooling |

## For agents

Read [`AGENTS.md`](AGENTS.md) first, then [`context.md`](context.md) and [`docs/README.md`](docs/README.md).
