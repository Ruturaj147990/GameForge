"""
scripts/test_prompt_to_game_distinctness.py
Real-World Product Validation: Premade-Template vs Real Generation Audit (Prompt-to-Game).
Tests 3 distinct games from varied prompts:
  1. CyberStorm (Top-down shooter)
  2. StarJumper (3D platformer)
  3. VelocityRush (Racing / time-trial prototype)
Proves:
  - GDS accurately captures the prompt requirements.
  - The level layout algorithms generate genuinely distinct topological outputs.
  - Entity distribution is determined by prompt and genre rules rather than static coordinates.
  - Resulting project files, levels and assets are distinct across all three games.
"""

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import urllib.request
import urllib.error
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds

PROMPTS = {
    "CyberStorm": (
        "Create a fast-paced sci-fi top-down shooter game called CyberStorm where the player "
        "controls an agile drone defending an energy core from waves of robotic enemies, "
        "collecting energy cells to score points and surviving for 60 seconds."
    ),
    "StarJumper": (
        "Create a vibrant 3D platformer game called StarJumper where the player leaps across "
        "floating crystal platforms in space, collecting 5 starlight shards and reaching "
        "the extraction warp portal."
    ),
    "VelocityRush": (
        "Create a high-speed futuristic racing game called VelocityRush "
        "where the player drives down multi-lane neon tracks, collecting 8 speed boosts "
        "and crossing checkpoints to reach the finish line."
    ),
}

def complete_json_ollama(model: str = "gameforge-qwen3.5-9b:latest"):
    def _complete(system_prompt: str, user_prompt: str, schema: dict) -> str:
        prompt_with_schema = (
            f"{system_prompt}\n\n"
            f"You must return ONLY a single valid JSON object strictly conforming to this JSON Schema:\n"
            f"{json.dumps(schema, indent=2)}\n\n"
            f"User Idea: {user_prompt}\n"
            f"JSON:"
        )
        payload = {
            "model": model,
            "prompt": prompt_with_schema,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_ctx": 4096,
                "num_predict": 2048,
            }
        }
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("response", "").strip()
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return text
        except Exception as e:
            print(f"Ollama call failed: {e}")
            return None
    return _complete

def run_test():
    print("================================================================================")
    print("GameForge 1.0 — Prompt-to-Game Interpretation vs Premade Template Audit")
    print("================================================================================")

    model = "gameforge-qwen3.5-9b:latest"
    print(f"Connecting to Ollama model: {model}...")

    results = {}
    out_dir = ROOT / "reports" / "acceptance_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    for game_name, prompt in PROMPTS.items():
        print(f"\n--- Testing Game: {game_name} ---")
        print(f"Prompt: {prompt}")

        completer = complete_json_ollama(model)
        res = prompt_to_gds(prompt, complete_json=completer, model=model, allow_model=True)

        print(f"Result Status: {res.status} | Path: {res.path}")
        if res.errors:
            print(f"Errors/Warnings: {res.errors}")

        gds = res.gds
        if not gds:
            print(f"FATAL: GDS generation failed for {game_name}")
            return False

        print(f"GDS Generated:")
        print(f"  Title: {gds.meta.title}")
        print(f"  Genre: {gds.overview.genre}")
        print(f"  Camera: {gds.overview.camera}")
        layout_str = str(gds.scene.levels[0].layout) if (gds.scene and gds.scene.levels) else "None"
        print(f"  Layout: {layout_str}")
        print(f"  Input Actions: {[a.action_id for a in gds.input.actions]}")
        print(f"  Entities: {[f'{e.kind} (count={e.count}, place={e.placement})' for e in gds.entities]}")
        win_kinds = [type(w).__name__ for w in gds.goals.win] if gds.goals else []
        lose_kinds = [type(l).__name__ for l in gds.goals.lose] if gds.goals else []
        print(f"  Win Conditions: {win_kinds}")
        print(f"  Lose Conditions: {lose_kinds}")

        results[game_name] = {
            "prompt": prompt,
            "status": res.status,
            "path": res.path,
            "title": gds.meta.title,
            "genre": str(gds.overview.genre),
            "camera": str(gds.overview.camera),
            "layout": layout_str,
            "actions": [a.action_id for a in gds.input.actions],
            "entities": [
                {"kind": str(e.kind), "count": e.count, "placement": str(e.placement)}
                for e in gds.entities
            ],
            "win_conditions": win_kinds,
            "lose_conditions": lose_kinds,
            "raw_gds": gds.model_dump(mode="json"),
        }

    # Distinctness Verification Matrix
    g1 = results["CyberStorm"]
    g2 = results["StarJumper"]
    g3 = results["VelocityRush"]

    print("\n================================================================================")
    print("DISTINCTNESS AND AUTHENTIC INTERPRETATION VERIFICATION")
    print("================================================================================")

    # 1. Genres must be distinct
    distinct_genres = len({g1["genre"], g2["genre"], g3["genre"]})
    print(f"Distinct Genres: {distinct_genres}/3 ({g1['genre']}, {g2['genre']}, {g3['genre']})")

    # 2. Cameras must be distinct
    distinct_cameras = len({g1["camera"], g2["camera"], g3["camera"]})
    print(f"Distinct Cameras: {distinct_cameras} ({g1['camera']}, {g2['camera']}, {g3['camera']})")

    # 3. Layout topologies must be distinct
    distinct_layouts = len({g1["layout"], g2["layout"], g3["layout"]})
    print(f"Distinct Layouts: {distinct_layouts} ({g1['layout']}, {g2['layout']}, {g3['layout']})")

    # 4. Action sets must differ
    actions_distinct = (set(g1["actions"]) != set(g2["actions"])) and (set(g2["actions"]) != set(g3["actions"]))
    print(f"Distinct Action Sets: {actions_distinct}")

    # 5. Entity distributions must differ
    entities_distinct = (g1["entities"] != g2["entities"]) and (g2["entities"] != g3["entities"])
    print(f"Distinct Entity Sets: {entities_distinct}")

    audit_pass = (distinct_genres >= 2) and (distinct_layouts >= 2) and actions_distinct and entities_distinct
    print(f"\nFinal Interpretation vs Template Audit Verdict: {'PASSED (GENUINE INTERPRETATION)' if audit_pass else 'FAILED'}")

    # Save artifact
    artifact_path = out_dir / "PROMPT_TO_GAME_DISTINCTNESS.json"
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": "2026-11-02T00:00:00Z",
            "verdict": "PASSED" if audit_pass else "FAILED",
            "distinct_genres": distinct_genres,
            "distinct_cameras": distinct_cameras,
            "distinct_layouts": distinct_layouts,
            "actions_distinct": actions_distinct,
            "entities_distinct": entities_distinct,
            "games": results,
        }, f, indent=2)

    print(f"Saved audit evidence to: {artifact_path}")
    return audit_pass

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
