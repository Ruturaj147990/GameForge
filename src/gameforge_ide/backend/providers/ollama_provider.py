"""Local Ollama Provider Adapter for GameForge IDE."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
import urllib.error
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from .base import ChatResponse, ModelInfo, ModelProvider, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)


def _extract_clean_json(text: str) -> Optional[str]:
    """Extract and validate clean JSON from raw model output, unwrapping code fences or explanatory prose."""
    if not text:
        return None
    s = text.strip()
    # 1. Fast path: directly parses as JSON
    try:
        json.loads(s)
        return s
    except Exception:
        pass

    # 2. Extract from markdown code fences: ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass

    # 3. Locate the outermost balanced JSON object {...}
    start = s.find("{")
    if start != -1:
        brace_count = 0
        in_str = False
        escape = False
        for i in range(start, len(s)):
            c = s[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if not in_str:
                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        candidate = s[start : i + 1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except Exception:
                            pass
                        break

    # 4. Locate the outermost balanced JSON array [...]
    arr_start = s.find("[")
    if arr_start != -1:
        bracket_count = 0
        in_str = False
        escape = False
        for i in range(arr_start, len(s)):
            c = s[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if not in_str:
                if c == "[":
                    bracket_count += 1
                elif c == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        candidate = s[arr_start : i + 1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except Exception:
                            pass
                        break

    return s


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
        # Dynamic capability resolution based on model tag/family
        model_lower = model_id.lower()
        is_vision = "vision" in model_lower or "27b-sft" in model_lower
        is_27b = "27b" in model_lower
        is_mid = "9b" in model_lower or "8b" in model_lower or "qwen" in model_lower
        ctx = 32768 if (is_27b or is_mid) else 4096
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=True,  # Native tool calling supported via chat_with_tools (/api/chat)
            supports_images=is_vision,
            supports_reasoning=False,
            max_context=ctx,
        )

    def budget_num_ctx(self, model_id: str, estimated_input_tokens: int = 0, requested_ctx: Optional[int] = None) -> int:
        """Dynamically budgets num_ctx based on model family and input size, respecting hardware bounds."""
        caps = self.get_capabilities(model_id)
        base_needed = max(8192, estimated_input_tokens + 4096)
        if requested_ctx and requested_ctx > 0:
            needed = max(requested_ctx, base_needed)
        else:
            needed = base_needed
        return min(needed, caps.max_context)

    def _request_with_retry(
        self,
        req: urllib.request.Request,
        timeout: float,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Executes HTTP request to Ollama with exponential backoff on transient errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_bytes = resp.read()
                    if not raw_bytes or not raw_bytes.strip():
                        if attempt < max_retries - 1:
                            sleep_time = 0.5 * (2 ** attempt)
                            logger.warning(
                                "Ollama returned empty response body, retrying in %.1fs (attempt %d/%d)",
                                sleep_time, attempt + 1, max_retries
                            )
                            time.sleep(sleep_time)
                            continue
                        raise RuntimeError("Ollama returned an empty response body")
                    return json.loads(raw_bytes.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
                last_exc = RuntimeError(f"Ollama API HTTP {exc.code}: {body}")
                if exc.code in (429, 502, 503, 504) and attempt < max_retries - 1:
                    sleep_time = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Ollama HTTP %s (transient busy state), retrying in %.1fs (attempt %d/%d): %s",
                        exc.code, sleep_time, attempt + 1, max_retries, body[:200]
                    )
                    time.sleep(sleep_time)
                    continue
                raise last_exc from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError, ValueError) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    sleep_time = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Ollama connection/decode error '%s', retrying in %.1fs (attempt %d/%d)",
                        exc, sleep_time, attempt + 1, max_retries
                    )
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError(f"Ollama connection failed after {max_retries} attempts: {exc}") from exc
        if last_exc:
            raise last_exc
        return {}

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
        est_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 3
        needed = max(8192, num_ctx, est_tokens + max_tokens + 512)
        effective_ctx = self.budget_num_ctx(model_id, est_tokens, needed)
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "tools": [{"type": "function", "function": t} for t in tools],
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": effective_ctx},
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        req = urllib.request.Request(
            f"http://{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/2"},
            method="POST",
        )
        data = self._request_with_retry(req, timeout=self.timeout)
        if "error" in data:
            raise RuntimeError(f"Ollama API error: {data['error']}")
        msg = data.get("message", {}) or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    clean_args = _extract_clean_json(args)
                    if clean_args:
                        try:
                            args = json.loads(clean_args)
                        except Exception:
                            args = {"_unparsed": args}
                    else:
                        args = {"_unparsed": args}
            calls.append({"name": fn.get("name"), "arguments": args})
        return {
            "content": msg.get("content", ""),
            "tool_calls": calls,
            "usage": {"prompt_tokens": data.get("prompt_eval_count", 0),
                      "completion_tokens": data.get("eval_count", 0)},
            "total_duration_ns": data.get("total_duration", 0),
        }

    def complete_json(
        self,
        model_id: str,
        system: str,
        user: str,
        schema: dict,
        num_ctx: int = 8192,
        temperature: float = 0.2,
        timeout_s: float = 120.0,
    ) -> Optional[str]:
        """Structured output via /api/chat `format` (JSON schema). Returns clean JSON text or None on transport errors."""
        est_tokens = (len(system) + len(user)) // 3
        effective_ctx = max(num_ctx, self.budget_num_ctx(model_id, est_tokens, num_ctx))
        payload = {
            "model": model_id,
            "stream": False,
            "think": False,
            "format": schema,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"num_ctx": effective_ctx, "temperature": temperature},
        }
        req = urllib.request.Request(
            f"http://{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/2"},
            method="POST",
        )
        try:
            data = self._request_with_retry(req, timeout=timeout_s)
            msg = data.get("message", {}) or {}
            raw_content = msg.get("content", "")
            return _extract_clean_json(raw_content)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            logger.warning("Ollama complete_json HTTP %s: %s", exc.code, body)
            return None
        except Exception as exc:
            logger.debug("Ollama complete_json error: %s", exc)
            return None

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
        saw_done = False
        for line in lines:
            if not line:
                continue
            try:
                chunk = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                continue
            if not isinstance(chunk, dict):
                continue
            if "error" in chunk and chunk["error"]:
                saw_done = True
                yield StreamChunk(
                    token="",
                    is_final=True,
                    error=str(chunk["error"]),
                )
                break
            done = chunk.get("done", False)
            if done:
                saw_done = True
            # /api/chat sends token in chunk["message"]["content"], /api/generate sends in chunk["response"]
            msg = chunk.get("message", {})
            token = msg.get("content", "") if isinstance(msg, dict) else ""
            if not token and "response" in chunk:
                token = chunk.get("response", "")
            status = chunk.get("status")
            meta = {"eval_count": chunk.get("eval_count", 0)} if done else {}
            if status and not token:
                meta["status"] = status
            # Only yield if there's a token, completion, or status update
            if token or done or status:
                yield StreamChunk(
                    token=token,
                    is_final=done,
                    metadata=meta,
                )
            if done:
                break
        if not saw_done:
            # Stream severed or ended without explicit done signal
            yield StreamChunk(token="", is_final=True)

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
        resolved_ctx = kwargs.get("num_ctx") or self.get_capabilities(model_id).max_context
        
        payload = self.build_chat_payload(
            model_id=model_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=resolved_ctx,
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
        est_tokens = (len(prompt) + len(system_prompt or "")) // 3
        resolved_ctx = kwargs.get("num_ctx") or self.budget_num_ctx(model_id, est_tokens)
        payload = {
            "model": model_id,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": resolved_ctx,
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
            data = self._request_with_retry(req, timeout=self.timeout)
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
