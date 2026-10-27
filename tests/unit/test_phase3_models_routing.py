"""Unit and regression tests for Phase 3 — Models, Routing, & Clean Evaluation.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
1. Model capability records: explicit identity, tool support, licensing, and local_only egress.
2. Phase-based routing without silent fallback:
   - discover/explore -> fast agent model
   - author -> domain specialist
   - image tasks -> vision-capable model only
3. Startup self-test verifying structured tool-calling format and Modelfile template.
4. Clean-fixture benchmarking integrity: zero-patch grounding, protected grader immutability,
   and honest score reporting.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.gameforge_ide.backend.models.capability import CapabilityRecord, CapabilityRegistry
from src.gameforge_ide.backend.providers.base import (
    ChatResponse,
    ModelInfo,
    ModelProvider,
    ProviderCapabilities,
    StreamChunk,
)
from src.gameforge_ide.backend.providers.router import ModelRouter


class MockSelfTestProvider(ModelProvider):
    """Test double that simulates valid or invalid tool template rendering."""

    def __init__(self, render_tools: bool = True, available: bool = True):
        self._render_tools = render_tools
        self._available = available

    def get_provider_id(self) -> str:
        return "mock_test"

    def is_available(self) -> bool:
        return self._available

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="mock-fast", name="Mock Fast", provider="mock_test")]

    def get_capabilities(self, model_id: str) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=self._render_tools, max_context=16384)

    def complete(self, *args, **kwargs) -> ChatResponse:
        if self._render_tools:
            content = '```json\n{"tool": "list_dir", "args": {"subpath": ""}}\n```'
        else:
            content = "I would normally list the directory, but I am outputting text only."
        return ChatResponse(content=content, model="mock-fast")

    async def stream_chat(self, *args, **kwargs):
        yield StreamChunk(token="mock")


def test_capability_registry_discovers_local_models():
    """Verifies that CapabilityRegistry discovers verified models and SHA-256 digests on E:\\GameForge."""
    registry = CapabilityRegistry(storage_root=Path(r"E:\GameForge"))
    records = registry.list_records()

    assert len(records) >= 2, "Expected at least 2 models discovered or registered."

    # Verify field schema on every record
    for rec in records:
        assert rec.model_id
        assert rec.data_egress_class == "local_only", "Cloud egress must be blocked by default."
        assert rec.license_name
        assert rec.max_context >= 4096


def test_phase_based_routing_and_no_silent_fallback(tmp_path: Path):
    """Router selects models by phase; refuses cloud egress and fails closed."""
    router = ModelRouter(storage_root=Path(r"E:\GameForge"))

    # Register deterministic test records
    router.registry._records = {
        "fast-9b": CapabilityRecord(
            model_id="fast-9b",
            display_name="Fast 9B Agent",
            tag="9b",
            role="fast_agent",
            supports_tools=True,
            supports_images=False,
            data_egress_class="local_only",
        ),
        "specialist-27b": CapabilityRecord(
            model_id="specialist-27b",
            display_name="Specialist 27B Author",
            tag="27b",
            role="specialist_author",
            supports_tools=True,
            supports_images=True,
            data_egress_class="local_only",
        ),
    }

    # 1. Routing for discover/explore phase -> fast agent
    rec_discover = router.route_for_phase("discover")
    assert rec_discover.role == "fast_agent"
    assert rec_discover.model_id == "fast-9b"

    # 2. Routing for author phase -> domain specialist
    rec_author = router.route_for_phase("author")
    assert rec_author.role == "specialist_author"
    assert rec_author.model_id == "specialist-27b"

    # 3. Routing for multimodal image task -> requires_images=True
    rec_vision = router.route_for_phase("author", requires_images=True)
    assert rec_vision.supports_images is True
    assert rec_vision.model_id == "specialist-27b"

    # 4. Fail closed when vision required but no model supports it
    router.registry._records["specialist-27b"].supports_images = False
    with pytest.raises(ValueError) as exc:
        router.route_for_phase("author", requires_images=True)
    assert "No vision-capable local model available" in str(exc.value)


def test_tool_calling_startup_self_test():
    """Startup self-test verifies whether model's template renders structured tool calls."""
    router = ModelRouter()

    # Case 1: Template correctly renders structured tools
    good_provider = MockSelfTestProvider(render_tools=True)
    router.register_provider("good_prov", good_provider)
    res_good = router.run_startup_tool_self_test("good_prov", "mock-fast")
    assert res_good["ok"] is True
    assert res_good["status"] == "SELF_TEST_PASSED"

    # Case 2: Template fails to render tool calls
    bad_provider = MockSelfTestProvider(render_tools=False)
    router.register_provider("bad_prov", bad_provider)
    res_bad = router.run_startup_tool_self_test("bad_prov", "mock-fast")
    assert res_bad["ok"] is False
    assert res_bad["status"] == "TEMPLATE_FAILED"

    # Case 3: Provider offline
    offline_provider = MockSelfTestProvider(available=False)
    router.register_provider("offline_prov", offline_provider)
    res_offline = router.run_startup_tool_self_test("offline_prov", "mock-fast")
    assert res_offline["ok"] is False
    assert res_offline["status"] == "PROVIDER_OFFLINE"


def test_clean_fixture_benchmark_zero_patch_grounding(tmp_path: Path):
    """Clean Fixture Benchmark: Protected paths and forbidden files are detected and rejected."""
    from src.gameforge_bench.policy import check_candidate_policy

    workspace = tmp_path / "ws"
    workspace.mkdir()
    candidate_dir = workspace / "candidate"
    candidate_dir.mkdir()

    # 1. Candidate modifies protected grader file
    grader_file = candidate_dir / "graders" / "protected" / "test_hidden.py"
    grader_file.parent.mkdir(parents=True, exist_ok=True)
    grader_file.write_text("assert True", encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate_dir,
        allowed_edit_paths=["Source/GameMode.cpp"],
        forbidden_paths=["graders"],
    )
    assert res.passed is False
    assert any("protected" in v.lower() or "forbidden" in v.lower() for v in res.violations)
