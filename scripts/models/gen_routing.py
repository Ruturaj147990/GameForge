"""Generate model_routing.json from empirical P9 evaluation reports (WI-9.3, Exit Gate 2)."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "P9"
CONFIG_FILE = REPO_ROOT / "src" / "gameforge_ide" / "config" / "model_routing.json"

CANONICAL_ROSTER = {
    "gameforge-qwen3.5-9b:latest",
    "gameforge-qwen3.5-4b:latest",
    "gameforge-27b-sft:latest",
    "llama3.1:8b",
}

# Latency budgets (Blueprint §9, Handover P9)
BUDGETS = {
    "design": 60.0,
    "codegen": 120.0,
    "fast": 5.0,
    "vision": 20.0,
    "chat": 15.0,
    "heavy_local": 300.0,
}


def load_latest_reports() -> Dict[str, Dict[str, Any]]:
    """Find and load the latest eval report for each evaluated model."""
    if not REPORTS_DIR.is_dir():
        return {}

    reports_by_model: Dict[str, Dict[str, Any]] = {}
    pattern = re.compile(r"^eval_([A-Za-z0-9_.-]+)_(\d{8}T\d{6}Z)\.json$")

    for p in sorted(REPORTS_DIR.glob("eval_*.json")):
        m = pattern.match(p.name)
        if not m:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            model_id = data.get("model_id")
            if not model_id:
                continue
            # Keep newest by file timestamp
            reports_by_model[model_id] = {
                "path": str(p.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "data": data,
            }
        except Exception:
            pass

    return reports_by_model


def select_best_model_for_role(
    role: str,
    reports_by_model: Dict[str, Dict[str, Any]],
    family_key: Optional[str] = None,
) -> str:
    """Select the highest scoring enabled model satisfying the latency budget for the given role."""
    max_lat = BUDGETS.get(role, 60.0)
    candidates: List[tuple[float, float, str]] = []  # (score, -latency, model_id)

    for m_id, item in reports_by_model.items():
        data = item["data"]
        ov = data.get("overall", {})
        fams = data.get("families", {})
        
        # Family score if applicable, else overall pass rate
        if family_key and family_key in fams:
            fam_metrics = fams[family_key]
            score = fam_metrics.get("pass_rate", 0.0)
            lat = fam_metrics.get("p90_latency_s", ov.get("p90_latency_s", 999.0))
        else:
            score = ov.get("pass_rate", 0.0)
            lat = ov.get("p90_latency_s", 999.0)

        # Budget constraint
        if lat <= max_lat:
            candidates.append((score, -lat, m_id))

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][2]

    # Fallbacks based on architectural roles if no candidate met strict budget
    if role == "fast":
        return "gameforge-qwen3.5-4b:latest"
    if role == "vision":
        return "gameforge-qwen3.5-4b:latest"
    if role == "heavy_local":
        return "gameforge-27b-sft:latest"
    return "gameforge-qwen3.5-9b:latest"


def generate_routing_table(write: bool = False) -> Dict[str, Any]:
    """Build the routing table. Pass write=True (the CLI does) to overwrite the packaged config;
    the default is side-effect free so tests do not rewrite a shipped product file.

    Note: role assignments are currently fixed policy (Part 6.1), not derived from the eval
    scores listed under source.reports.
    """
    latest = load_latest_reports()

    # Per Part 6.1: 9B model is the default and primary for chat, design, codegen, planning, tools
    design_model = "gameforge-qwen3.5-9b:latest"
    codegen_model = "gameforge-qwen3.5-9b:latest"
    chat_model = "gameforge-qwen3.5-9b:latest"
    fast_model = "gameforge-qwen3.5-4b:latest"
    vision_model = "gameforge-qwen3.5-4b:latest"
    heavy_model = "gameforge-27b-sft:latest"

    source_records = [
        {"path": v["path"], "sha256": v["sha256"], "model_id": k}
        for k, v in latest.items()
    ]

    routing = {
        "schema": "model_routing/1",
        "source": {
            "description": "Fixed role policy (Part 6.1: 9B primary, 4B fast/vision, 27B heavy). The P9 eval reports below are listed for reference; they do not select the models.",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reports": source_records,
        },
        "roles": {
            "chat": chat_model,
            "design": design_model,
            "codegen": codegen_model,
            "fast": fast_model,
            "vision": vision_model,
            "heavy_local": heavy_model,
        },
    }

    if write:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(routing, indent=2), encoding="utf-8")
        print(f"Generated routing table saved to {CONFIG_FILE}")
        print(f"Role assignments: {json.dumps(routing['roles'], indent=2)}")
    return routing


if __name__ == "__main__":
    generate_routing_table(write=True)
