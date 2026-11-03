"""Autonomous Counter-Strike Benchmark Runner.

Executes the benchmark exclusively through GameForge production APIs:
1. Natural language prompt -> Ollama GDS drafting
2. Composer -> Tactical FPS layout (CT Base, T Base, Site A, Site B, corridors, cover, 5 bots)
3. Forge Executor -> DAG execution (Scaffold -> Build -> Assemble -> Automation -> Package -> Scenarios -> Report)
4. Packaged game verification and headless scenario replay
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
from src.gameforge_ide.backend.tools.game_tools import GameTools
from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.forge.model import StepStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cs_benchmark")

BENCHMARK_PROMPT = (
    "Create a first-person tactical Counter-Strike game called CounterStrike with "
    "bomb defusal at site A and B, assault rifle and pistol weapons, opposing terrorist bots, "
    "round timer, and HUD."
)

TARGET_DIR = Path(r"E:\GameForge\projects\CounterStrike")


def run_benchmark():
    start_time = time.time()
    logger.info("================================================================================")
    logger.info("STARTING GAMEFORGE 1.0 MANDATORY COUNTER-STRIKE BENCHMARK")
    logger.info("Prompt: %s", BENCHMARK_PROMPT)
    logger.info("Target Directory: %s", TARGET_DIR)
    logger.info("================================================================================")

    # Clean existing benchmark folder if present
    if TARGET_DIR.exists():
        logger.info("Cleaning previous benchmark directory at %s...", TARGET_DIR)
        import shutil
        shutil.rmtree(TARGET_DIR, ignore_errors=True)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Draft GDS using production Ollama model
    settings = get_settings()
    provider = OllamaProvider(host=settings.ollama_url.replace("http://", "").replace("https://", ""))
    model = settings.model_for("design")
    logger.info("Drafting GDS using local Ollama model '%s'...", model)

    def complete_json(system: str, user: str, schema: dict):
        return provider.complete_json(model, system, user, schema)

    draft_res = prompt_to_gds(BENCHMARK_PROMPT, complete_json=complete_json, model=model)
    logger.info("Draft result status: %s", draft_res.status)
    if draft_res.questions:
        logger.info("Clarification questions generated: %s", draft_res.questions)

    gds = draft_res.gds
    if not gds:
        logger.error("Failed to generate GDS from prompt!")
        sys.exit(1)

    # Ensure project metadata points to our benchmark target
    gds.meta.project_name = "CounterStrike"
    gds.meta.title = "CounterStrike"
    gds.meta.project_dir = str(TARGET_DIR)
    gds.meta.source_prompt = BENCHMARK_PROMPT
    if hasattr(gds.overview, "camera"):
        from src.gameforge_ide.design.gds import CameraKind
        gds.overview.camera = CameraKind.FIRST_PERSON

    logger.info("GDS validated: project='%s', genre='%s', camera='%s'",
                gds.meta.project_name, gds.overview.genre, getattr(gds.overview, "camera", None))

    # 2. Verify Composer Layout
    logger.info("Composing level and runtime definition...")
    comp = compose(gds, allow_partial=True)
    level_plan = comp.levels[0]
    logger.info("Level composed: level_id='%s', geometry_ops=%d, actors=%d, player_start=%s",
                level_plan.level_id, len(level_plan.geometry_ops), len(level_plan.actors), level_plan.player_start)

    actor_classes = [a.runtime_class for a in level_plan.actors]
    logger.info("Placed actor classes: %s", set(actor_classes))

    # 3. Execute Forge DAG
    logger.info("Initializing GameTools and executing Forge DAG...")
    tools = GameTools(workspace_root=REPO_ROOT, projects_root=TARGET_DIR.parent, engine_root=settings.engine_root)

    events_log = []

    def on_event(topic: str, data: dict):
        events_log.append((topic, data))
        kind = data.get("kind")
        step_id = data.get("step_id")
        if kind == "step_started":
            logger.info("--> [STAGE START] %s (attempt %s)", step_id, data.get("attempt", 1))
        elif kind == "step_finished":
            ok = data.get("ok")
            dur = data.get("duration_s", 0)
            status_str = "SUCCESS" if ok else "FAILED"
            logger.info("<-- [STAGE %s] %s (duration: %.1fs)", status_str, step_id, dur)
        elif kind == "log":
            line = data.get("line", "")
            if "error" in line.lower() or "warning" in line.lower() or "building" in line.lower():
                logger.info("    [LOG] %s", line.strip())

    logger.info("Launching GameTools.create_game for CounterStrike...")
    run_outcome = tools.create_game(
        gds_or_params=gds,
        project_dir=TARGET_DIR,
        package=True,
        on_event=on_event,
    )

    logger.info("create_game outcome: %s", run_outcome.get("ok"))
    if not run_outcome.get("ok"):
        logger.error("Run failed! Errors: %s", run_outcome.get("errors"))

    total_duration = time.time() - start_time
    logger.info("================================================================================")
    logger.info("BENCHMARK EXECUTION FINISHED in %.1fs (%.2f min)", total_duration, total_duration / 60.0)
    logger.info("================================================================================")

    # 4. Verify On-Disk Artifacts
    uproject_file = TARGET_DIR / "CounterStrike.uproject"
    editor_dll = TARGET_DIR / "Binaries" / "Win64" / "UnrealEditor-CounterStrike.dll"
    level_umap = TARGET_DIR / "Content" / "Maps" / "Level_1.umap"
    packaged_exe = TARGET_DIR / "Packaged" / "Windows" / "CounterStrike.exe"

    logger.info("Artifact Verification:")
    logger.info("  • .uproject: %s (exists=%s)", uproject_file, uproject_file.is_file())
    logger.info("  • Level_1.umap: %s (exists=%s)", level_umap, level_umap.is_file())
    logger.info("  • Editor DLL: %s (exists=%s)", editor_dll, editor_dll.is_file())
    logger.info("  • Packaged Executable: %s (exists=%s)", packaged_exe, packaged_exe.is_file())

    if packaged_exe.is_file():
        exe_size_mb = packaged_exe.stat().st_size / (1024 * 1024)
        logger.info("  • Packaged binary size: %.2f MB", exe_size_mb)

    # Check scenario replay results
    scenario_result = TARGET_DIR / "Saved" / "GameForge" / "evidence" / "scenario_results.json"
    if scenario_result.is_file():
        logger.info("Scenario results: %s", scenario_result.read_text(encoding="utf-8")[:500])

    return run_outcome


if __name__ == "__main__":
    run_benchmark()
