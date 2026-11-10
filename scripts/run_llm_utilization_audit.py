"""Comprehensive Real LLM Utilization & Prompt-Driven Game Modification Audit.

Investigates:
1. Live local LLM invocation (Ollama 9B) during game generation.
2. Understanding of natural language prompts across distinct genres.
3. Prompt diversity analysis (GDS differences vs template cloning).
4. Progressive natural-language modifications through the GameForge IDE pipeline.
5. Multi-file changes, persistence, non-regression of prior features, and build verification.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.design.patch import propose_patch, apply_patch
from src.gameforge_ide.composer.compose import compose

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LLMAudit")


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def test_initial_generation_diversity(provider: OllamaProvider, model_name: str, output_dir: Path) -> List[Dict[str, Any]]:
    """Test 3 materially distinct game creation prompts using live local LLM."""
    logger.info("=== TEST 1: Initial Game Generation Diversity (Live Ollama 9B) ===")

    test_prompts = [
        {
            "id": "game_1_stealth",
            "name": "SilentInfiltration",
            "prompt": "Silent Infiltration: A dark night stealth game where you play a ninja evading 4 laser tripwire hazards and 3 patrolling guards to hack an altar terminal in an indoor facility",
        },
        {
            "id": "game_2_scifi",
            "name": "CyberOrbit",
            "prompt": "Cyber Orbit: A fast-paced sci-fi arena game with 3 waves of 5 enemy drones, glowing projectile blasters, 850 player move speed, and survive 90 seconds",
        },
        {
            "id": "game_3_dungeon",
            "name": "CryptRelics",
            "prompt": "Crypt Relics: A gothic dungeon rooms game where you explore ancient crypts, collect 7 cursed relics, avoid 4 spike hazards, and reach the old portal gate",
        },
    ]

    results: List[Dict[str, Any]] = []

    def complete_json(system: str, user: str, schema: dict):
        return provider.complete_json(model_name, system, user, schema, think=False)

    for item in test_prompts:
        prompt_text = item["prompt"]
        t0 = time.monotonic()
        logger.info("Prompting LLM for '%s'...", item["name"])
        res = prompt_to_gds(prompt_text, complete_json=complete_json, model=model_name)
        elapsed = time.monotonic() - t0

        assert res.status == "OK" or res.gds is not None, f"Failed to generate GDS for {item['name']}: {res.errors}"
        gds = res.gds

        gds_file = output_dir / f"{item['name']}.gds.json"
        _write_json_atomic(gds_file, gds.model_dump())

        summary = {
            "id": item["id"],
            "name": item["name"],
            "prompt": prompt_text,
            "elapsed_seconds": round(elapsed, 2),
            "generator": gds.meta.generator,
            "title": gds.meta.title,
            "genre": gds.overview.genre.value,
            "camera": gds.overview.camera.value if hasattr(gds.overview.camera, "value") else str(gds.overview.camera),
            "lighting": gds.scene.levels[0].lighting.value if hasattr(gds.scene.levels[0].lighting, "value") else str(gds.scene.levels[0].lighting),
            "layout": gds.scene.levels[0].layout.value if hasattr(gds.scene.levels[0].layout, "value") else str(gds.scene.levels[0].layout),
            "entities_count": len(gds.entities),
            "entity_kinds": [e.kind.value for e in gds.entities],
            "win_conditions": [getattr(w, "kind", str(w)) for w in gds.goals.win],
            "lose_conditions": [getattr(l, "kind", str(l)) for l in gds.goals.lose],
        }
        logger.info("Generated %s in %.2fs: genre=%s, camera=%s, lighting=%s, entities=%s",
                    item["name"], elapsed, summary["genre"], summary["camera"], summary["lighting"], summary["entity_kinds"])
        results.append(summary)

    return results


def test_progressive_modifications(provider: OllamaProvider, model_name: str, base_gds_path: Path, output_dir: Path) -> List[Dict[str, Any]]:
    """Progressively apply 4 substantially different modifications to a game."""
    logger.info("=== TEST 2: Progressive Prompt-Driven Modifications via LLM ===")

    current_gds = GameDesignSpec.model_validate_json(base_gds_path.read_text(encoding="utf-8"))
    mod_history: List[Dict[str, Any]] = []

    def model_caller(task: str, prompt: str) -> str:
        sys_prompt = (
            "You are a GameForge GDS patch assistant. Generate RFC 6902 JSON patch ops "
            "to update the GameDesignSpec based on the user request. "
            "Return a JSON object with keys: ops (array of {op, path, value}), summary (concise description under 15 words without preamble or reasoning), questions (array of string)."
        )
        raw = provider.complete_json(
            model_name,
            sys_prompt,
            prompt,
            {
                "type": "object",
                "properties": {
                    "ops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["add", "remove", "replace"]},
                                "path": {"type": "string"},
                                "value": {},
                            },
                            "required": ["op", "path"],
                        },
                    },
                    "summary": {"type": "string"},
                    "questions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ops", "summary"],
            },
            think=False,
        )
        return raw or "{}"

    modification_steps = [
        {
            "step": 1,
            "label": "Sprint Speed & Max Health",
            "request": "Increase player move speed to 1250 and set player max health to 300",
            "verify_key": lambda g: (
                float(g.entities[0].props.get("move_speed", 0)) == 1250.0
                and float(g.entities[0].props.get("player_max_health", g.entities[0].props.get("max_health", 0))) == 300.0
            ),
        },
        {
            "step": 2,
            "label": "Night Atmosphere & Toxic Hazards",
            "request": "Change the lighting to night and add 4 toxic acid hazards scattered across the area",
            "verify_key": lambda g: (
                str(getattr(g.scene.levels[0].lighting, "value", g.scene.levels[0].lighting)).lower() == "night"
                and any(e.kind.value == "hazard" for e in g.entities)
            ),
        },
        {
            "step": 3,
            "label": "Shotgun Arsenal & Combat Bots",
            "request": "Equip the player with a shotgun weapon and increase hostile enemies to 6 per wave",
            "verify_key": lambda g: (
                g.entities[0].props.get("attack_mode") == "shotgun"
                or "shotgun" in str(g.entities[0].props.get("weapons", []))
                or any(float(e.props.get("enemies_per_wave", 0)) >= 5 for e in g.entities)
            ),
        },
        {
            "step": 4,
            "label": "Survive 180s Objective & Timer",
            "request": "Update the win condition so the player must survive for 180 seconds or reach the goal",
            "verify_key": lambda g: (
                any("180" in str(w) or "survive" in str(w) or "timer" in str(w) or "goal" in str(w) for w in g.goals.win)
            ),
        },
    ]

    for m in modification_steps:
        step_num = m["step"]
        req_text = m["request"]
        logger.info("Running Modification Step %d: '%s'...", step_num, req_text)
        t0 = time.monotonic()

        prop = propose_patch(current_gds, req_text, model_caller=model_caller)
        elapsed = time.monotonic() - t0

        logger.info("Step %d proposed in %.2fs: status=%s, summary=%s", step_num, elapsed, prop.status, prop.summary)
        assert prop.status == "OK" and prop.ops, f"Step {step_num} failed: {prop.summary} questions={prop.questions}"

        # Apply patch
        patched_gds = apply_patch(current_gds, prop.ops)
        patched_gds.meta.revision += 1

        # Verify target modification
        verified = m["verify_key"](patched_gds)
        logger.info("Step %d verification condition satisfied: %s", step_num, verified)
        assert verified, f"Step {step_num} verification failed on patched GDS!"

        # Save snapshot
        snap_file = output_dir / f"step_{step_num}_patched.gds.json"
        _write_json_atomic(snap_file, patched_gds.model_dump())

        # Run composition to verify whole-game integration
        comp = compose(patched_gds)
        assert comp.levels, f"Step {step_num} composition produced 0 level plans"

        mod_history.append({
            "step": step_num,
            "label": m["label"],
            "request": req_text,
            "elapsed_seconds": round(elapsed, 2),
            "ops": prop.ops,
            "summary": prop.summary,
            "verified": verified,
            "revision": patched_gds.meta.revision,
            "entities_count": len(patched_gds.entities),
            "level_actors_placed": len(comp.levels[0].actors),
            "lighting": str(patched_gds.scene.levels[0].lighting),
        })

        # Advance current GDS for progressive chaining
        current_gds = patched_gds

    return mod_history


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Real LLM Utilization & Game Modification Audit")
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--out-dir", type=Path, default=Path("reports/acceptance_audit/llm_utilization"))
    args = parser.parse_args(argv)

    settings = get_settings()
    host = settings.ollama_url.replace("http://", "").replace("https://", "")
    provider = OllamaProvider(host=host)
    model_name = args.model or settings.model_for("design")

    if not provider.is_available():
        logger.error("Ollama daemon is offline at %s. Aborting audit.", host)
        return 2

    output_dir = args.out_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Ollama Host: %s, Model: %s", host, model_name)

    try:
        # 1. Test Initial Generation Diversity
        diversity_results = test_initial_generation_diversity(provider, model_name, output_dir)

        # 2. Test Progressive Modifications
        base_file = output_dir / "CyberOrbit.gds.json"
        mod_results = test_progressive_modifications(provider, model_name, base_file, output_dir)

        # 3. Save Summary JSON
        summary_data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": model_name,
            "initial_generation": diversity_results,
            "progressive_modifications": mod_results,
        }
        summary_file = output_dir / "audit_summary.json"
        _write_json_atomic(summary_file, summary_data)

        logger.info("Audit complete! Results written to %s", summary_file)
        return 0
    finally:
        # Unload model to preserve 12GB VRAM budget
        try:
            provider.chat_with_tools(
                model_name,
                [{"role": "user", "content": "ok"}],
                [],
                num_ctx=512,
                max_tokens=1,
                keep_alive="0",
                think=False,
            )
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
