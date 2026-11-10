"""Model Router and Multi-Provider Registry for GameForge IDE.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
- Phase-based routing based on measured capability, not model's own request:
  - discover/explore: fast agent model (9B-14B in VRAM).
  - author: domain specialist (gameforge-27b-sft or qwen3.8:27b).
  - multimodal: vision-capable model only.
- Strict anti-fallback rule: No silent fallback to unapproved models or cloud providers.
- Local by default: Cloud egress blocked unless explicitly authorized.
- Startup self-test: checks native tool rendering.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..models.capability import CapabilityRecord, CapabilityRegistry
from .base import ModelInfo, ModelProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAICompatibleProvider
from .hosted import GuardedProvider, build_guarded_providers


class ModelRouter:
    """Routes tasks across configured local and remote model providers."""

    def __init__(
        self,
        ollama_host: str = "127.0.0.1:11434",
        storage_root: Optional[Path] = None,
    ):
        self.providers: Dict[str, ModelProvider] = {
            "ollama": OllamaProvider(host=ollama_host),
            "openai_compatible": OpenAICompatibleProvider(),
        }
        self.default_provider_id = "ollama"
        self.registry = CapabilityRegistry(storage_root=storage_root)
        self.hosted: Dict[str, GuardedProvider] = {}

    def attach_hosted(self, workspace_root: Path, profiles=None) -> Dict[str, GuardedProvider]:
        """Register the hosted heavy-model tier for a workspace (each provider stays guarded)."""
        self.hosted = build_guarded_providers(workspace_root, profiles)
        for pid, prov in self.hosted.items():
            self.providers[f"hosted:{pid}"] = prov
        return self.hosted

    def route_hosted(self, role: str, requires_images: bool = False):
        """Pick a hosted (provider_id, model_id) for a role, only if enabled, opted-in and credentialed.

        Returns None when no hosted model is usable; the caller then stays on the local tier and
        says so. There is never a silent switch between tiers in the middle of a task.
        """
        for pid, prov in self.hosted.items():
            if not prov.is_available():
                continue
            for m in prov.profile.models:
                if role in m.roles and (m.supports_images or not requires_images):
                    return f"hosted:{pid}", m.id
        return None

    def register_provider(self, provider_id: str, provider: ModelProvider) -> None:
        self.providers[provider_id] = provider

    def get_provider(self, provider_id: Optional[str] = None) -> ModelProvider:
        pid = provider_id or self.default_provider_id
        if pid not in self.providers:
            raise KeyError(f"Provider '{pid}' is not registered. Available: {list(self.providers.keys())}")
        return self.providers[pid]

    def list_all_models(self, include_configured_when_offline: bool = True) -> List[ModelInfo]:
        """Models from every reachable provider.

        When no provider answers (Ollama not started yet), the configured routing models are
        returned with an "offline" description instead of an empty list, so the model selector
        still shows the user which model will be used and the UI can say *why* it is unavailable.
        """
        all_models: List[ModelInfo] = []
        seen: set = set()
        for provider in self.providers.values():
            try:
                if provider.is_available():
                    for m in provider.list_models():
                        if m.id not in seen:
                            seen.add(m.id)
                            all_models.append(m)
            except Exception:
                continue
        if all_models or not include_configured_when_offline:
            return all_models
        try:
            import json as _json
            from pathlib import Path as _Path

            cfg = _Path(__file__).resolve().parents[2] / "config" / "model_routing.json"
            roles = _json.loads(cfg.read_text(encoding="utf-8")).get("roles", {})
        except Exception:
            roles = {}
        for role, model_id in roles.items():
            if model_id and model_id not in seen:
                seen.add(model_id)
                all_models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        provider=self.default_provider_id or "ollama",
                        description=f"Configured for '{role}' (provider offline: start Ollama to use it)",
                        is_local=True,
                    )
                )
        return all_models

    def route_for_phase(
        self,
        phase: str,
        requires_images: bool = False,
        preferred_model: Optional[str] = None,
    ) -> CapabilityRecord:
        """Determines active model based on phase and verified capability records."""
        records = self.registry.list_records()
        if not records:
            raise ValueError("No models registered in capability registry.")

        if requires_images:
            for rec in records:
                if rec.supports_images and rec.data_egress_class == "local_only":
                    return rec
            raise ValueError("No vision-capable local model available for image task.")

        if preferred_model:
            rec = self.registry.get_record(preferred_model)
            if rec:
                return rec

        target_role = "fast_agent" if phase in ("discover", "explore") else "specialist_author"
        for rec in records:
            if rec.role == target_role and rec.data_egress_class == "local_only":
                return rec

        # Fallback to first verified local model
        local_records = [r for r in records if r.data_egress_class == "local_only"]
        if local_records:
            return local_records[0]

        raise ValueError(f"No authorized local model available for phase '{phase}'. Cloud egress blocked.")

    def run_startup_tool_self_test(self, provider_id: str, model_id: str) -> Dict[str, Any]:
        """Self-test verifying that the model's template renders structured tool calls."""
        provider = self.get_provider(provider_id)
        if not provider.is_available():
            return {
                "ok": False,
                "status": "PROVIDER_OFFLINE",
                "error": f"Provider '{provider_id}' is offline. Self-test cannot run.",
            }
        if hasattr(provider, "native_tool_self_test"):
            return provider.native_tool_self_test(model_id)

        sample_prompt = (
            "Invoke the list_dir tool to check the workspace root.\n"
            "Emit the tool call in JSON format:\n"
            "```json\n{\"tool\": \"list_dir\", \"args\": {\"subpath\": \"\"}}\n```"
        )
        try:
            resp = provider.complete(
                model_id=model_id,
                prompt=sample_prompt,
                system_prompt="You are a tool-using AI assistant.",
                temperature=0.0,
                max_tokens=256,
            )
            # Verify JSON tool block rendered
            rendered_tool = "list_dir" in resp.content and '"args"' in resp.content
            return {
                "ok": rendered_tool,
                "status": "SELF_TEST_PASSED" if rendered_tool else "TEMPLATE_FAILED",
                "model_id": model_id,
                "rendered_tool": rendered_tool,
            }
        except Exception as e:
            return {
                "ok": False,
                "status": "SELF_TEST_ERROR",
                "error": f"Tool self-test failed: {e}",
            }

    def resolve_model(self, model_id: str) -> tuple[ModelProvider, str]:
        """Resolves model_id to its matching provider without silent fallback."""
        # 1. Check explicit provider prefix (e.g. "hosted:anthropic:claude-3-7-sonnet" or "openai_compatible:gpt-4o")
        if ":" in model_id:
            for pid, prov in self.providers.items():
                if model_id.startswith(f"{pid}:"):
                    target_model = model_id[len(pid) + 1 :]
                    return prov, target_model

        # 2. Check all available registered providers for matching model ID
        for pid, prov in self.providers.items():
            try:
                if prov.is_available():
                    for m in prov.list_models():
                        if m.id == model_id or m.name == model_id:
                            return prov, m.id
            except Exception:
                continue

        # 3. Fall back to default provider
        prov = self.get_provider()
        return prov, model_id
