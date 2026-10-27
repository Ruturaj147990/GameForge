"""Local Ollama Provider Adapter for GameForge IDE."""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from .base import ChatResponse, ModelInfo, ModelProvider, ProviderCapabilities, StreamChunk


class OllamaProvider(ModelProvider):
    """Integrates local Ollama running on consumer AMD GPU/CPU."""

    def __init__(self, host: str = "127.0.0.1:11434", timeout_seconds: int = 180):
        self.host = host.rstrip("/")
        self.timeout = timeout_seconds

    def get_provider_id(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        try:
            url = f"http://{self.host}/api/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "GameForge-IDE/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> List[ModelInfo]:
        if not self.is_available():
            return []
        try:
            url = f"http://{self.host}/api/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "GameForge-IDE/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("models", []):
                name = item.get("name", "")
                models.append(
                    ModelInfo(
                        id=name,
                        name=name,
                        provider="ollama",
                        size_bytes=item.get("size"),
                        description=f"Local Ollama model: {name}",
                        is_local=True,
                    )
                )
            return models
        except Exception:
            return []

    def get_capabilities(self, model_id: str) -> ProviderCapabilities:
        # Pinned production model: 4096 context, vision attached via projector
        is_vision = "vision" in model_id.lower() or "27b-sft" in model_id.lower()
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=False,  # Evaluated: reliable via structured json action formatting
            supports_images=is_vision,
            supports_reasoning=False,
            max_context=4096,
        )

    @staticmethod
    def build_stream_payload(
        model_id: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        num_ctx: int = 4096,
    ) -> Dict[str, Any]:
        """Build the exact JSON payload sent to Ollama for streamed generation."""
        prompt_parts = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "user":
                prompt_parts.append(f"Developer: {content}")
            elif role == "assistant":
                prompt_parts.append(f"GameForge: {content}")
            elif role == "system" and not system_prompt:
                system_prompt = content

        full_prompt = "\n\n".join(prompt_parts) + "\n\nGameForge:"
        return {
            "model": model_id,
            "prompt": full_prompt,
            "system": system_prompt or "You are GameForge, expert game development AI assistant.",
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": num_ctx,
            },
            "think": False,
        }

    def chat_with_tools(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        num_ctx: int = 8192,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        keep_alive: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Native tool calling via /api/chat `tools`. Returns {content, tool_calls, usage}.

        `tools` uses the provider-neutral shape {name, description, parameters}. `think` is
        always False and `num_ctx` is always explicit (Master Blueprint v2 §6).
        """
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "tools": [{"type": "function", "function": t} for t in tools],
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": num_ctx},
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        req = urllib.request.Request(
            f"http://{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/2"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data.get("message", {}) or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_unparsed": args}
            calls.append({"name": fn.get("name"), "arguments": args})
        return {
            "content": msg.get("content", ""),
            "tool_calls": calls,
            "usage": {"prompt_tokens": data.get("prompt_eval_count", 0),
                      "completion_tokens": data.get("eval_count", 0)},
            "total_duration_ns": data.get("total_duration", 0),
        }

    def native_tool_self_test(self, model_id: str, num_ctx: int = 4096) -> Dict[str, Any]:
        """Startup gate: the model must answer a one-tool request with a structured call."""
        tool = {"name": "list_dir", "description": "List files in a workspace directory.",
                "parameters": {"type": "object", "properties": {"subpath": {"type": "string"}},
                               "required": ["subpath"]}}
        t0 = time.time()
        try:
            res = self.chat_with_tools(
                model_id,
                [{"role": "system", "content": "You are a tool-using assistant. Use tools to act."},
                 {"role": "user", "content": "List the files in the workspace root directory."}],
                [tool], num_ctx=num_ctx, max_tokens=128)
        except Exception as exc:
            return {"ok": False, "model": model_id, "status": "SELF_TEST_ERROR", "error": str(exc)}
        calls = res["tool_calls"]
        ok = len(calls) >= 1 and calls[0]["name"] == "list_dir" and isinstance(calls[0]["arguments"], dict)
        return {"ok": ok, "model": model_id, "status": "SELF_TEST_PASSED" if ok else "TEMPLATE_FAILED",
                "tool_calls": calls, "content_preview": res["content"][:120],
                "seconds": round(time.time() - t0, 2)}

    @staticmethod
    def build_chat_payload(
        model_id: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        num_ctx: int = 4096,
    ) -> Dict[str, Any]:
        """Build structured chat payload for Ollama /api/chat preserving multi-turn roles."""
        chat_messages = []
        if system_prompt:
            chat_messages.append({"role": "system", "content": system_prompt})
        for m in messages:
            chat_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        return {
            "model": model_id,
            "messages": chat_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": num_ctx,
            },
            "think": False,
        }

    @staticmethod
    def parse_stream_lines(lines) -> Iterator[StreamChunk]:
        """Decode Ollama's newline-delimited JSON response records from /api/chat or /api/generate."""
        for line in lines:
            if not line:
                continue
            try:
                chunk = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                continue
            done = chunk.get("done", False)
            # /api/chat sends token in chunk["message"]["content"], /api/generate sends in chunk["response"]
            msg = chunk.get("message", {})
            token = msg.get("content", "") if isinstance(msg, dict) else ""
            if not token and "response" in chunk:
                token = chunk.get("response", "")
            yield StreamChunk(
                token=token,
                is_final=done,
                metadata={"eval_count": chunk.get("eval_count", 0)} if done else {},
            )
            if done:
                break

    async def stream_chat(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Streams completion tokens from Ollama /api/chat."""
        url = f"http://{self.host}/api/chat"
        
        payload = self.build_chat_payload(
            model_id=model_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=kwargs.get("num_ctx", 4096),
        )

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/1.0"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for chunk in self.parse_stream_lines(resp):
                    yield chunk
        except urllib.error.URLError as e:
            yield StreamChunk(
                token="",
                is_final=True,
                error=f"Local Ollama connection failure: {e.reason}. Ensure 'ollama serve' is running.",
            )
        except Exception as e:
            yield StreamChunk(token="", is_final=True, error=f"Ollama streaming error: {str(e)}")

    def complete(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> ChatResponse:
        url = f"http://{self.host}/api/generate"
        payload = {
            "model": model_id,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": kwargs.get("num_ctx", 4096),
            },
            "think": False,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return ChatResponse(
                content=data.get("response", ""),
                model=model_id,
                finish_reason="stop" if data.get("done") else "length",
                usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                },
                metadata={"total_duration": data.get("total_duration", 0)},
            )
        except Exception as e:
            raise RuntimeError(f"Ollama completion failed: {e}") from e
