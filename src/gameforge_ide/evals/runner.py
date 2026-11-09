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


def _resolve_json_pointer(doc: Dict[str, Any], path: str) -> List[Any]:
    """Resolve a JSON-pointer-like path (supporting '*' wildcard segment) into matching values."""
    parts = [p for p in path.strip("/").split("/") if p]
    current: List[Any] = [doc]
    for part in parts:
        next_items: List[Any] = []
        for item in current:
            if part == "*":
                if isinstance(item, list):
                    next_items.extend(item)
                elif isinstance(item, dict):
                    next_items.extend(item.values())
            elif isinstance(item, dict) and part in item:
                next_items.append(item[part])
            elif isinstance(item, list):
                try:
                    idx = int(part)
                    if 0 <= idx < len(item):
                        next_items.append(item[idx])
                except ValueError:
                    pass
        current = next_items
    return current


def _check_gds_expectations(
    base_gds: GameDesignSpec,
    patched_gds: GameDesignSpec,
    expectations: List[Dict[str, Any]],
) -> bool:
    """Verify all task expectations against base_gds and patched_gds."""
    if not expectations:
        return patched_gds.meta.revision > base_gds.meta.revision

    base_doc = base_gds.model_dump()
    patched_doc = patched_gds.model_dump()

    for exp in expectations:
        path = exp.get("path", "")
        op = exp.get("op", "==")
        before_vals = _resolve_json_pointer(base_doc, path)
        after_vals = _resolve_json_pointer(patched_doc, path)

        if op == "==":
            target = exp.get("value")
            if not any(v == target for v in after_vals):
                # Fallback: check level-0 lighting if "/scene/lighting" was specified
                if path == "/scene/lighting":
                    lvl_vals = _resolve_json_pointer(patched_doc, "/scene/levels/*/lighting")
                    if not any(v == target for v in lvl_vals):
                        return False
                else:
                    return False
        elif op == "contains_kind":
            target_kind = str(exp.get("value", "")).lower()
            entities = after_vals[0] if after_vals and isinstance(after_vals[0], list) else []
            if not any(
                target_kind in str(e.get("kind", "")).lower()
                or target_kind in str(e.get("entity_id", "")).lower()
                or target_kind in str(e.get("display_name", "")).lower()
                for e in entities
                if isinstance(e, dict)
            ):
                return False
        elif op == "does_not_contain_kind":
            target_kind = str(exp.get("value", "")).lower()
            entities = after_vals[0] if after_vals and isinstance(after_vals[0], list) else []
            if any(
                target_kind == str(e.get("kind", "")).lower()
                or target_kind in str(e.get("entity_id", "")).lower()
                for e in entities
                if isinstance(e, dict)
            ):
                return False
        elif op == "count_increase":
            delta = int(exp.get("delta", 1))
            b_list = before_vals[0] if before_vals and isinstance(before_vals[0], list) else []
            a_list = after_vals[0] if after_vals and isinstance(after_vals[0], list) else []
            if len(a_list) < len(b_list) + delta:
                return False
        elif op in (">", "<"):
            multiplier = exp.get("multiplier")
            delta = exp.get("delta")
            b_nums = [float(v) for v in before_vals if isinstance(v, (int, float))]
            a_nums = [float(v) for v in after_vals if isinstance(v, (int, float))]
            if not a_nums:
                return False
            if op == ">":
                if multiplier is not None and b_nums:
                    if not any(a >= b * float(multiplier) - 1e-6 for a, b in zip(a_nums, b_nums)) and max(a_nums) <= max(b_nums):
                        return False
                elif delta is not None and b_nums:
                    if sum(a_nums) < sum(b_nums) + float(delta) and max(a_nums) < max(b_nums) + float(delta):
                        return False
                elif b_nums and max(a_nums) <= max(b_nums):
                    return False
            elif op == "<":
                if multiplier is not None and b_nums:
                    if not any(a <= b * float(multiplier) + 1e-6 for a, b in zip(a_nums, b_nums)) and min(a_nums) >= min(b_nums):
                        return False
                elif b_nums and min(a_nums) >= min(b_nums):
                    return False

    return True


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
        if limit is not None:
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
                f"Task ID: {task['id']}\n"
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
        if limit is not None:
            tasks = tasks[:limit]

        results = []

        for task in tasks:
            fixture_name = task.get("gds_fixture", "relic_hunt")
            try:
                base_gds = get_preset_spec(fixture_name)
            except Exception:
                base_gds = get_preset_spec("relic_hunt")

            prompt = (
                f"Task ID: {task['id']}\n"
                f"You are the GameForge Design Agent. Propose an RFC 6902 JSON patch for this request: '{task['request']}'.\n"
                f"Base GDS JSON:\n{base_gds.model_dump_json()}\n"
                f"Expected assertions: {json.dumps(task.get('expect', []))}\n"
                f"Return JSON: {{\"ops\": [{{\"op\": \"replace\"|\"add\"|\"remove\", \"path\": str, \"value\": any}}], \"summary\": str}}"
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
                        try:
                            patched = apply_patch(base_gds, ops)
                            passed = (
                                patched.meta.revision > base_gds.meta.revision
                                and _check_gds_expectations(base_gds, patched, task.get("expect", []))
                            )
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
        if limit is not None:
            tasks = tasks[:limit]

        results = []
        for task in tasks:
            prompt = (
                f"Task ID: {task['id']}\n"
                f"Fix the following C++ compiler error:\n"
                f"Kind: {task.get('kind', '')}\n"
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
                    if expected_snippet:
                        passed = expected_snippet in fixed_code
                    else:
                        orig_sources = "\n".join(task.get("files", {}).values())
                        passed = bool(fixed_code.strip() and fixed_code.strip() != orig_sources.strip())
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
        if limit is not None:
            tasks = tasks[:limit]

        results = []
        for task in tasks:
            prompt = (
                f"Task ID: {task['id']}\n"
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

    def run_vision_rubric(self, adapter: ModelAdapter, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        tasks = self.load_tasks("vision_rubric")
        if limit is not None:
            tasks = tasks[:limit]

        results = []
        schema = {
            "criteria": {
                "mesh_quality": "int (1-5)",
                "lighting_coherence": "int (1-5)",
                "composition_readability": "int (1-5)",
                "thematic_consistency": "int (1-5)",
                "no_placeholders": "int (1-5)",
                "framerate_stability": "int (1-5)",
            },
            "overall": "float",
            "passed": "bool",
        }

        for task in tasks:
            prompt = (
                f"Task ID: {task['id']}\n"
                f"Evaluate the visual quality rubric for capture '{task.get('capture_id', '')}' "
                f"in environment '{task.get('environment', '')}'.\n"
                f"Target criteria: {json.dumps(task.get('criteria', {}))}\n"
                f"Return JSON matching schema: {json.dumps(schema)}"
            )
            res = adapter.complete(prompt, schema_json=schema, num_ctx=4096)
            valid_json = False
            first_try = False
            passed = False

            if not res.get("error"):
                try:
                    data = json.loads(res["text"])
                    valid_json = True
                    first_try = True
                    criteria = data.get("criteria") if isinstance(data, dict) else None
                    overall = float(data.get("overall", 0.0)) if isinstance(data, dict) else 0.0
                    if isinstance(criteria, dict) and overall == 0.0 and criteria:
                        overall = sum(float(v) for v in criteria.values()) / len(criteria)
                    threshold = float(task.get("acceptable_threshold", 3.5))
                    passed = isinstance(criteria, dict) and len(criteria) >= 6 and overall >= threshold
                except Exception:
                    valid_json = False

            results.append({
                "task_id": task["id"],
                "family": "vision_rubric",
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
        def _get_limit(family: str) -> Optional[int]:
            if limits is None:
                return None
            return limits.get(family, 0)

        dd_res = self.run_design_draft(adapter, limit=_get_limit("design_draft"))
        gp_res = self.run_gds_patch(adapter, limit=_get_limit("gds_patch"))
        cr_res = self.run_codegen_rule(adapter, limit=_get_limit("codegen_rule"))
        rep_res = self.run_cpp_repair(adapter, limit=_get_limit("cpp_repair"))
        vr_res = self.run_vision_rubric(adapter, limit=_get_limit("vision_rubric"))

        all_results = dd_res + gp_res + cr_res + rep_res + vr_res
        family_metrics = {
            "design_draft": compute_task_metrics(dd_res),
            "gds_patch": compute_task_metrics(gp_res),
            "codegen_rule": compute_task_metrics(cr_res),
            "cpp_repair": compute_task_metrics(rep_res),
            "vision_rubric": compute_task_metrics(vr_res),
        }
        overall = compute_task_metrics(all_results)

        return {
            "model_id": adapter.model_id,
            "provider_kind": adapter.provider_kind,
            "version_info": adapter.get_version_info(),
            "overall": overall,
            "families": family_metrics,
        }
