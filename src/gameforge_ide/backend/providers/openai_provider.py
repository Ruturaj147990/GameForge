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

    def _is_local(self) -> bool:
        return any(h in self.base_url for h in ("127.0.0.1", "localhost", "::1"))

    def is_available(self) -> bool:
        if self.test_mode:
            return True
        key = self._get_api_key()
        if not key and not self._is_local():
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
                is_local=self._is_local(),
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

        authorized = kwargs.get("allow_remote", False) or kwargs.get("authorized", False) or self._is_local()
        if not authorized:
            yield StreamChunk(
                token="",
                is_final=True,
                error="Remote provider calls require explicit authorization per Section 3 and Section 5 constraints.",
            )
            return

        api_key = self._get_api_key() or ("local" if self._is_local() else "")
        if not api_key:
            yield StreamChunk(
                token="",
                is_final=True,
                error=f"Remote provider authentication missing: Environment variable '{self.api_key_env}' is not set.",
            )
            return

        # Prepare request
        chat_msgs: List[Dict[str, str]] = []
        if system_prompt:
            chat_msgs.append({"role": "system", "content": system_prompt})
        chat_msgs.extend(messages)

        payload = {
            "model": model_id,
            "messages": chat_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "GameForge-IDE/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choice = (data.get("choices") or [{}])[0]
            content = choice.get("message", {}).get("content", "")
            yield StreamChunk(token=content, is_final=True, metadata={"usage": data.get("usage", {})})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            yield StreamChunk(token="", is_final=True, error=f"OpenAI HTTP {exc.code}: {body}")
        except Exception as exc:
            yield StreamChunk(token="", is_final=True, error=f"OpenAI stream error: {exc}")

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

        authorized = kwargs.get("allow_remote", False) or kwargs.get("authorized", False) or self._is_local()
        if not authorized:
            raise RuntimeError("Remote completion requires explicit user authorization and verified endpoint.")

        api_key = self._get_api_key() or ("local" if self._is_local() else "")
        if not api_key:
            raise RuntimeError(f"Missing API key in environment variable '{self.api_key_env}'")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "GameForge-IDE/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message", {})
            return ChatResponse(
                content=msg.get("content", ""),
                model=data.get("model", model_id),
                finish_reason=choice.get("finish_reason", "stop"),
                usage=data.get("usage", {}),
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            raise RuntimeError(f"OpenAI-compatible HTTP {exc.code}: {body}") from exc
        except Exception as exc:
            raise RuntimeError(f"OpenAI-compatible request failed: {exc}") from exc
