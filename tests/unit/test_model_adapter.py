"""Unit tests for GameForge Model Evaluation Adapter (model_adapter.py)."""

from pathlib import Path
import pytest
from gameforge_bench.model_adapter import (
    ModelRequest,
    ModelResponse,
    extract_code_blocks,
    invoke_candidate,
)


def test_extract_code_blocks_with_file_header():
    sample_text = (
        "Here is the implementation:\n\n"
        "### File: Source/GameForgePilot/Public/HealthComponent.h\n"
        "```cpp\n"
        "#pragma once\n"
        "#include \"CoreMinimal.h\"\n"
        "```\n\n"
        "### File: Source/GameForgePilot/Private/HealthComponent.cpp\n"
        "```cpp\n"
        "#include \"HealthComponent.h\"\n"
        "```\n"
    )
    patches = extract_code_blocks(sample_text)
    assert "Source/GameForgePilot/Public/HealthComponent.h" in patches
    assert "Source/GameForgePilot/Private/HealthComponent.cpp" in patches
    assert "#pragma once" in patches["Source/GameForgePilot/Public/HealthComponent.h"]


def test_extract_code_blocks_fallback_to_allowed_path():
    sample_text = (
        "```cpp\n"
        "void AProjectileActor::OnHit() {}\n"
        "```\n"
    )
    allowed = ["Source/GameForgePilot/Private/ProjectileActor.cpp"]
    patches = extract_code_blocks(sample_text, allowed_paths=allowed)
    assert "Source/GameForgePilot/Private/ProjectileActor.cpp" in patches
    assert "OnHit" in patches["Source/GameForgePilot/Private/ProjectileActor.cpp"]


def test_invoke_candidate_test_double():
    cand_config = {
        "candidate_id": "test_double_01",
        "runtime_type": "test_double",
    }
    req = ModelRequest(
        task_id="t2-004-health-damage",
        prompt="Implement health component",
    )
    resp = invoke_candidate(cand_config, req)
    assert resp.success is True
    assert resp.candidate_id == "test_double_01"
    assert "TEST DOUBLE" in resp.raw_output


def test_invoke_candidate_unsupported_provider():
    cand_config = {
        "candidate_id": "unknown_01",
        "runtime_type": "cloud_api",
        "provider": "unsupported_provider_xyz",
    }
    req = ModelRequest(
        task_id="t2-004-health-damage",
        prompt="Implement health component",
    )
    resp = invoke_candidate(cand_config, req)
    assert resp.success is False
    assert "Unsupported candidate provider" in resp.error


def test_model_request_default_fields():
    req = ModelRequest(
        task_id="t1-001-health-invariants",
        prompt="Explain invariants",
    )
    assert req.temperature == 0.0
    assert req.max_tokens == 4096
    assert req.timeout_seconds == 120
    assert req.run_id.startswith("req_")
