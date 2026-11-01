"""Unit tests for evidence-based model routing (WI-9.3)."""
import json
from pathlib import Path
import pytest

from scripts.models.gen_routing import CANONICAL_ROSTER, generate_routing_table

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTING_FILE = REPO_ROOT / "src" / "gameforge_ide" / "config" / "model_routing.json"


def test_model_routing_structure_and_evidence():
    assert ROUTING_FILE.is_file(), "model_routing.json must exist"
    data = json.loads(ROUTING_FILE.read_text(encoding="utf-8"))

    assert data.get("schema") == "model_routing/1"
    src = data.get("source", {})
    assert "generated_at" in src
    reports = src.get("reports", [])
    assert len(reports) > 0, "model_routing must cite evaluation reports"

    for r in reports:
        assert "path" in r
        assert "sha256" in r
        assert len(r["sha256"]) == 64
        rep_path = REPO_ROOT / r["path"]
        assert rep_path.is_file(), f"Cited report {rep_path} must exist"

    roles = data.get("roles", {})
    required_roles = {"chat", "design", "codegen", "fast", "vision", "heavy_local"}
    assert required_roles.issubset(roles.keys())

    for role_name, model_name in roles.items():
        assert model_name in CANONICAL_ROSTER, (
            f"Role {role_name} assigned '{model_name}', which is not in the canonical 4-model roster"
        )


def test_gen_routing_reproducible():
    routing = generate_routing_table()
    assert routing["schema"] == "model_routing/1"
    assert len(routing["source"]["reports"]) >= 4
