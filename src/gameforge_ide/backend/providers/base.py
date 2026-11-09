"""Base Model Provider Interfaces and Capabilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str  # "ollama", "openai_compatible", "gameforge_hosted"
    size_bytes: Optional[int] = None
    description: Optional[str] = None
    is_local: bool = True


class ProviderCapabilities(BaseModel):
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_images: bool = False
    supports_reasoning: bool = False
    max_context: int = 4096


class StreamChunk(BaseModel):
    token: str
    is_final: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ChatResponse(BaseModel):
    content: str
    model: str
    finish_reason: str = "stop"
    usage: Dict[str, int] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelProvider(ABC):
    """Abstract interface for all GameForge LLM providers."""

    @abstractmethod
    def get_provider_id(self) -> str:
        """Returns unique identifier for this provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider endpoint is reachable."""
        pass

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """Lists available models from this provider."""
        pass

    @abstractmethod
    def get_capabilities(self, model_id: str) -> ProviderCapabilities:
        """Returns declared capabilities for a model."""
        pass

    @abstractmethod
    def stream_chat(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Asynchronously streams response tokens for a conversation."""
        pass

    @abstractmethod
    def complete(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> ChatResponse:
        """Executes a synchronous completion request."""
        pass

ModelCapabilities = ProviderCapabilities
