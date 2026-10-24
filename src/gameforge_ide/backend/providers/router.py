"""Model Router and Multi-Provider Registry for GameForge IDE."""

from __future__ import annotations

from typing import Dict, List, Optional
from .base import ModelInfo, ModelProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAICompatibleProvider


class ModelRouter:
    """Routes tasks across configured local and remote model providers."""

    def __init__(self, ollama_host: str = "127.0.0.1:11434"):
        self.providers: Dict[str, ModelProvider] = {
            "ollama": OllamaProvider(host=ollama_host),
            "openai_compatible": OpenAICompatibleProvider(),
        }
        self.default_provider_id = "ollama"

    def register_provider(self, provider_id: str, provider: ModelProvider) -> None:
        self.providers[provider_id] = provider

    def get_provider(self, provider_id: Optional[str] = None) -> ModelProvider:
        pid = provider_id or self.default_provider_id
        if pid not in self.providers:
            raise KeyError(f"Provider '{pid}' is not registered. Available: {list(self.providers.keys())}")
        return self.providers[pid]

    def list_all_models(self) -> List[ModelInfo]:
        all_models = []
        for provider in self.providers.values():
            if provider.is_available():
                all_models.extend(provider.list_models())
        return all_models

    def resolve_model(self, model_id: str) -> tuple[ModelProvider, str]:
        """Resolves model_id to its matching provider."""
        # Check Ollama first
        ollama = self.providers.get("ollama")
        if ollama and ollama.is_available():
            for m in ollama.list_models():
                if m.id == model_id or m.name == model_id:
                    return ollama, m.id

        # Fallback to default provider
        return self.get_provider(), model_id
