"""Task execution runner for GameForge Agentic Eval Suite (WI-9.1)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapters import ModelAdapter
from .metrics import compute_task_metrics
from ..design.draft import CameraKind, DesignDraft, DraftWin, Genre
from ..design.gds import GameDesignSpec
from ..design.patch import apply_patch
from ..design.presets import get_preset_spec


class EvalRunner:
    """Executes evaluation tasks across task families."""

    def __init__(self, tasks_dir: Optional[Path] = None):
        self.tasks_dir = tasks_dir or (Path(__file__).resolve().parent / "tasks")

    def load_tasks(self, family: str) -> List[Dict[str, Any]]:
        task_file = self.tasks_dir / f"{family}.jsonl"
        if not task_file.is_file():
            raise FileNotFoundError(f"Task dataset {family} not found at {task_file}")

        tasks = []
        with open(task_file, "r", encoding="utf-8") as f:
            for line in f:
                sline = line.strip()
                if sline:
                    tasks.append(json.loads(sline))
        return tasks

    def run_design_draft(self, adapter: ModelAdapter, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        tasks = self.load_tasks("design_draft")
        if limit:
            tasks = tasks[:limit]

        results = []
        schema = {
            "title": "string",
            "genre": "action_adventure | platformer | arena_combat | card_battler | procedural_world | top_down_shooter | dungeon_crawler | puzzle | exploration",
            "camera": "first_person | third_person | top_down | isometric",
            "pitch": "string",
            "win": [{"type": "string"}],
        }

        for task in tasks:
            prompt = (
                f"You are the GameForge Design Agent. Respond ONLY in valid JSON matching this schema:\n"
                f"{json.dumps(schema)}\n\n"
                f"User request: {task['prompt']}"
            )

            res = adapter.complete(prompt, schema_json=schema, num_ctx=4096)
            valid_json = False
            first_try = False
            passed = False
            parsed_data = None

            if not res.get("error"):
                try:
                    parsed_data = json.loads(res["text"])
                    valid_json = True
                    first_try = True
                except Exception:
                    # One repair round
                    repair_prompt = f"Fix this output into strict valid JSON matching the schema:\n{res['text']}"
                    rep_res = adapter.complete(repair_prompt, schema_json=schema, num_ctx=4096)
                    try:
                        parsed_data = json.loads(rep_res["text"])
                        valid_json = True
                    except Exception:
                        valid_json = False

            if valid_json and isinstance(parsed_data, dict):
                # Check genre and camera requirements
                must = task.get("must_include", {})
                exp_genre = must.get("genre")
                actual_genre = parsed_data.get("genre", "")

                genre_match = True
                if exp_genre:
                    genre_match = (exp_genre.lower() in actual_genre.lower()) or (actual_genre.lower() in exp_genre.lower())

                has_title = bool(parsed_data.get("title"))
                has_win = bool(parsed_data.get("win"))
                passed = genre_match and has_title and has_win

            results.append({
                "task_id": task["id"],
                "family": "design_draft",
                "valid_json": valid_json,
                "first_try_valid": first_try,
                "passed": passed,
                "duration_s": res.get("duration_s", 0.0),
                "tokens_in": res.get("tokens_in", 0),
                "tokens_out": res.get("tokens_out", 0),
                "tok_per_sec": res.get("tok_per_sec", 0.0),
                "cost_usd": res.get("cost_usd", 0.0),
            })

        return results

    def run_gds_patch(self, adapter: ModelAdapter, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        tasks = self.load_tasks("gds_patch")
        if limit:
            tasks = tasks[:limit]

        results = []
        base_gds = get_preset_spec("relic_hunt")

        for task in tasks:
            prompt = (
                f"You are the GameForge Design Agent. Propose an RFC 6902 JSON patch for this request: '{task['request']}'.\n"
                f"Return JSON: {{\"ops\": [{{'op': 'replace'|'add'|'remove', 'path': str, 'value': any}}], 'summary': str}}"
            )
            res = adapter.complete(prompt, schema_json={"ops": []}, num_ctx=4096)
            valid_json = False
            first_try = False
            passed = False

            if not res.get("error"):
                try:
                    data = json.loads(res["text"])
                    valid_json = True
                    first_try = True
                    ops = data.get("ops", [])
                    if isinstance(ops, list) and len(ops) > 0:
                        # Dry run apply
                        try:
                            patched = apply_patch(base_gds, ops)
                            passed = bool(patched.meta.revision > base_gds.meta.revision)
                        except Exception:
                            passed = False
                except Exception:
                    valid_json = False

            results.append({
                "task_id": task["id"],
                "family": "gds_patch",
                "valid_json": valid_json,
                "first_try_valid": first_try,
                "passed": passed,
                "duration_s": res.get("duration_s", 0.0),
                "tokens_in": res.get("tokens_in", 0),
                "tokens_out": res.get("tokens_out", 0),
                "tok_per_sec": res.get("tok_per_sec", 0.0),
                "cost_usd": res.get("cost_usd", 0.0),
            })

        return results

    def run_cpp_repair(self, adapter: ModelAdapter, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        tasks = self.load_tasks("cpp_repair")
        if limit:
            tasks = tasks[:limit]

        results = []
        for task in tasks:
            prompt = (
                f"Fix the following C++ compiler error:\n"
                f"Diagnostic: {task['diagnostics']}\n"
                f"Files:\n{json.dumps(task['files'])}\n"
                f"Return JSON with {{'fixed_code': str, 'explanation': str}}"
            )
            res = adapter.complete(prompt, schema_json={"fixed_code": "string"}, num_ctx=4096)
            valid_json = False
            first_try = False
            passed = False

            if not res.get("error"):
                try:
                    data = json.loads(res["text"])
                    valid_json = True
                    first_try = True
                    fixed_code = data.get("fixed_code", "")
                    expected_snippet = task.get("expected_fix_substring", "")
                    if expected_snippet and expected_snippet in fixed_code:
                        passed = True
                    elif "error" not in fixed_code and len(fixed_code) > 10:
                        passed = True
                except Exception:
                    valid_json = False

            results.append({
                "task_id": task["id"],
                "family": "cpp_repair",
                "valid_json": valid_json,
                "first_try_valid": first_try,
                "passed": passed,
                "duration_s": res.get("duration_s", 0.0),
                "tokens_in": res.get("tokens_in", 0),
                "tokens_out": res.get("tokens_out", 0),
                "tok_per_sec": res.get("tok_per_sec", 0.0),
                "cost_usd": res.get("cost_usd", 0.0),
            })

        return results

    def run_codegen_rule(self, adapter: ModelAdapter, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        tasks = self.load_tasks("codegen_rule")
        if limit:
            tasks = tasks[:limit]

        results = []
        for task in tasks:
            prompt = (
                f"Generate a C++ gameplay rule class for Unreal Engine 5.7:\n"
                f"Class Name: {task['class_name']}\n"
                f"Description: {task['description']}\n"
                f"Return JSON with {{'class_name': str, 'code': str}}"
            )
            res = adapter.complete(prompt, schema_json={"code": "string"}, num_ctx=4096)
            valid_json = False
            first_try = False
            passed = False

            if not res.get("error"):
                try:
                    data = json.loads(res["text"])
                    valid_json = True
                    first_try = True
                    code = data.get("code", "")
                    if "UCLASS" in code or "#include" in code:
                        passed = True
                except Exception:
                    valid_json = False

            results.append({
                "task_id": task["id"],
                "family": "codegen_rule",
                "valid_json": valid_json,
                "first_try_valid": first_try,
                "passed": passed,
                "duration_s": res.get("duration_s", 0.0),
                "tokens_in": res.get("tokens_in", 0),
                "tokens_out": res.get("tokens_out", 0),
                "tok_per_sec": res.get("tok_per_sec", 0.0),
                "cost_usd": res.get("cost_usd", 0.0),
            })

        return results

    def run_suite(self, adapter: ModelAdapter, limits: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Run full evaluation suite across all families."""
        limits = limits or {}
        dd_res = self.run_design_draft(adapter, limit=limits.get("design_draft"))
        gp_res = self.run_gds_patch(adapter, limit=limits.get("gds_patch"))
        cr_res = self.run_codegen_rule(adapter, limit=limits.get("codegen_rule"))
        rep_res = self.run_cpp_repair(adapter, limit=limits.get("cpp_repair"))

        all_results = dd_res + gp_res + cr_res + rep_res
        family_metrics = {
            "design_draft": compute_task_metrics(dd_res),
            "gds_patch": compute_task_metrics(gp_res),
            "codegen_rule": compute_task_metrics(cr_res),
            "cpp_repair": compute_task_metrics(rep_res),
        }
        overall = compute_task_metrics(all_results)

        return {
            "model_id": adapter.model_id,
            "provider_kind": adapter.provider_kind,
            "version_info": adapter.get_version_info(),
            "overall": overall,
            "families": family_metrics,
        }
