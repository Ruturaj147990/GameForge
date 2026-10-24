"""Extensible OpenAI-Compatible Remote Provider for GameForge IDE."""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import ChatResponse, ModelInfo, ModelProvider, ProviderCapabilities, StreamChunk


class OpenAICompatibleProvider(ModelProvider):
    """Integrates remote OpenAI-compatible endpoints and future self-hosted GameForge models."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        test_mode: bool = False,
        timeout_seconds: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.test_mode = test_mode
        self.timeout = timeout_seconds

    def _get_api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    def get_provider_id(self) -> str:
        return "openai_compatible"

    def is_available(self) -> bool:
        if self.test_mode:
            return True
        key = self._get_api_key()
        if not key:
            return False
        # Do not make external network calls unless explicitly configured and enabled
        return True

    def list_models(self) -> List[ModelInfo]:
        if self.test_mode:
            return [
                ModelInfo(
                    id="gameforge-hosted-frontier",
                    name="GameForge Hosted Frontier (Remote)",
                    provider="openai_compatible",
                    description="Future hosted remote GameForge model",
                    is_local=False,
                ),
                ModelInfo(
                    id="gpt-4o",
                    name="GPT-4o (Remote)",
                    provider="openai_compatible",
                    description="OpenAI general reasoning backend",
                    is_local=False,
                ),
            ]
        return [
            ModelInfo(
                id="custom-remote",
                name="Configured Remote Model",
                provider="openai_compatible",
                description=f"Endpoint: {self.base_url}",
                is_local=False,
            )
        ]

    def get_capabilities(self, model_id: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_images=True,
            supports_reasoning=True,
            max_context=128000,
        )

    async def stream_chat(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        if self.test_mode:
            mock_tokens = ["Plan:", " 1. Inspect", " files.", " 2. Lower", " Game", " IR.", " 3. Verify."]
            for t in mock_tokens:
                yield StreamChunk(token=t, is_final=False)
            yield StreamChunk(token="", is_final=True)
            return

        api_key = self._get_api_key()
        if not api_key:
            yield StreamChunk(
                token="",
                is_final=True,
                error=f"Remote provider authentication missing: Environment variable '{self.api_key_env}' is not set.",
            )
            return

        # Remote execution disabled unless authorized
        yield StreamChunk(
            token="",
            is_final=True,
            error="Remote provider calls require explicit authorization per Section 3 and Section 5 constraints.",
        )

    def complete(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> ChatResponse:
        if self.test_mode:
            return ChatResponse(
                content="[Deterministic Test Double]: Code generated cleanly.",
                model=model_id,
                finish_reason="stop",
                usage={"prompt_tokens": 20, "completion_tokens": 10},
            )
        raise RuntimeError("Remote completion requires explicit user authorization and verified endpoint.")
