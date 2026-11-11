"""Local Ollama Provider Adapter for GameForge IDE."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import threading
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
    s = re.sub(r"<think>[\s\S]*?</think>", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"</?think>", "", s, flags=re.IGNORECASE).strip()
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

    # Ollama reloads a model (several seconds, plus VRAM churn on a 12 GB card) whenever a
    # request arrives with a different num_ctx than the loaded instance. Every caller used to
    # pick its own value (8192 for design JSON, 32768 for chat, ...), so switching between the
    # assistant and the design tools reloaded the model each time. The provider now keeps a
    # per-model "sticky" context that only grows (in power-of-two buckets) up to the model cap.
    _CTX_BUCKETS = (4096, 8192, 16384, 32768, 65536, 131072)
    _sticky_ctx: Dict[str, int] = {}
    _sticky_lock = threading.Lock()

    def __init__(self, host: str = "127.0.0.1:11434", timeout_seconds: int = 180):
        host = (host or "127.0.0.1:11434").strip().rstrip("/")
        # Accept "http://host:port" as well as "host:port" (OLLAMA_HOST is often set with a scheme).
        for prefix in ("http://", "https://"):
            if host.lower().startswith(prefix):
                host = host[len(prefix):]
        self.host = host
        self.timeout = timeout_seconds

    def get_provider_id(self) -> str:
        return "ollama"

    # The desktop asks for availability/model lists several times during startup and on every
    # dropdown open, often on the UI thread. One /api/tags probe answers both questions, and the
    # answer is cached briefly per host so repeated calls do not each pay an HTTP round-trip.
    _TAGS_TTL_S = 5.0
    _tags_cache: Dict[str, Any] = {}
    _tags_lock = threading.Lock()

    def _fetch_tags(self, force: bool = False) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        with self._tags_lock:
            hit = self._tags_cache.get(self.host)
            if hit and not force and now - hit[0] < self._TAGS_TTL_S:
                return hit[1]
        data: Optional[Dict[str, Any]] = None
        try:
            url = f"http://{self.host}/api/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "GameForge-IDE/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8") or "{}")
        except Exception:
            data = None
        with self._tags_lock:
            self._tags_cache[self.host] = (now, data)
        return data

    def invalidate_cache(self) -> None:
        with self._tags_lock:
            self._tags_cache.pop(self.host, None)

    def is_available(self) -> bool:
        return self._fetch_tags() is not None

    def list_models(self) -> List[ModelInfo]:
        data = self._fetch_tags()
        if data is None:
            return []
        try:
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
        """Budget num_ctx from model capability and input size, reusing the loaded context when possible.

        The result is rounded up to a bucket and never shrinks below the context this provider
        last used for the same model (see ``_sticky_ctx``), which avoids model reloads.
        """
        caps = self.get_capabilities(model_id)
        base_needed = max(8192, int(estimated_input_tokens) + 4096)
        needed = max(int(requested_ctx), base_needed) if requested_ctx and requested_ctx > 0 else base_needed
        bucket = next((b for b in self._CTX_BUCKETS if b >= needed), needed)
        with self._sticky_lock:
            sticky = self._sticky_ctx.get(model_id, 0)
            # An explicit caller request may exceed the family heuristic (unknown model tags
            # default to a conservative 4096); honour it rather than silently shrinking.
            cap = max(caps.max_context, int(requested_ctx or 0))
            chosen = min(max(bucket, sticky), cap)
            self._sticky_ctx[model_id] = max(sticky, chosen)
        return chosen

    @staticmethod
    def estimate_tokens(*texts: Any) -> int:
        """Cheap token estimate (~3.2 chars/token for code-heavy English; errs on the high side)."""
        total = 0
        for t in texts:
            if t is None:
                continue
            if isinstance(t, (list, tuple)):
                total += OllamaProvider.estimate_tokens(*t)
            elif isinstance(t, dict):
                total += OllamaProvider.estimate_tokens(t.get("content", ""))
            else:
                total += len(str(t))
        return int(total / 3.2) + 1

    @staticmethod
    def is_thinking_model(model_id: str) -> bool:
        """Determines if thinking mode is default on for the model (GameForge Qwen models)."""
        if not model_id:
            return False
        mid = str(model_id).lower().strip()
        return "qwen" in mid or "gameforge-qwen" in mid

    @classmethod
    def resolve_think_mode(cls, model_id: str, explicit_think: Optional[bool] = None) -> bool:
        """Resolves whether thinking mode is enabled for a given model.

        Thinking mode is default ON (True) for GameForge Qwen models.
        For other models, it defaults to False unless explicitly requested.
        """
        if explicit_think is not None:
            return bool(explicit_think)
        return cls.is_thinking_model(model_id)

    def _request_with_retry(
        self,
        req: urllib.request.Request,
        timeout: float,
        max_retries: int = 3,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """Executes HTTP request to Ollama with exponential backoff on transient errors and cooperative cancellation."""
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Operation cancelled by user")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if cancel_event is not None:
                        monitor_stopped = threading.Event()
                        def _monitor():
                            while not monitor_stopped.wait(0.05):
                                if cancel_event.is_set():
                                    try:
                                        resp.close()
                                    except Exception:
                                        pass
                                    break
                        t_mon = threading.Thread(target=_monitor, daemon=True)
                        t_mon.start()
                        try:
                            raw_bytes = resp.read()
                        finally:
                            monitor_stopped.set()
                            t_mon.join(timeout=0.2)
                    else:
                        raw_bytes = resp.read()
                    if not raw_bytes or not raw_bytes.strip():
                        if attempt < max_retries - 1:
                            sleep_time = 0.5 * (2 ** attempt)
                            logger.warning(
                                "Ollama returned empty response body, retrying in %.1fs (attempt %d/%d)",
                                sleep_time, attempt + 1, max_retries
                            )
                            if cancel_event is not None and cancel_event.wait(timeout=sleep_time):
                                raise RuntimeError("Operation cancelled by user")
                            elif cancel_event is None:
                                time.sleep(sleep_time)
                            continue
                        raise RuntimeError("Ollama returned an empty response body")
                    return json.loads(raw_bytes.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
                last_exc = RuntimeError(f"Ollama API HTTP {exc.code}: {body}")
                if exc.code == 400 and "does not support thinking" in body:
                    try:
                        req_data = json.loads(req.data.decode("utf-8")) if req.data else {}
                        if req_data.get("think"):
                            req_data["think"] = False
                            req = urllib.request.Request(
                                req.full_url,
                                data=json.dumps(req_data).encode("utf-8"),
                                headers=dict(req.headers),
                                method=req.get_method(),
                            )
                            logger.info(
                                "Model '%s' does not support native thinking parameter; retrying with think=False",
                                req_data.get("model", ""),
                            )
                            continue
                    except Exception:
                        pass
                if exc.code in (429, 502, 503, 504) and attempt < max_retries - 1:
                    sleep_time = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Ollama HTTP %s (transient busy state), retrying in %.1fs (attempt %d/%d): %s",
                        exc.code, sleep_time, attempt + 1, max_retries, body[:200]
                    )
                    if cancel_event is not None and cancel_event.wait(timeout=sleep_time):
                        raise RuntimeError("Operation cancelled by user")
                    elif cancel_event is None:
                        time.sleep(sleep_time)
                    continue
                raise last_exc from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError, ValueError) as exc:
                last_exc = exc
                # A read timeout means the model is generating (or stuck) for longer than the
                # budget; re-sending the same request would only multiply the wait by max_retries.
                reason = getattr(exc, "reason", exc)
                if isinstance(reason, (socket.timeout, TimeoutError)):
                    raise RuntimeError(
                        f"Ollama request timed out after {timeout:.0f}s (model still loading or generation too long)."
                    ) from exc
                if attempt < max_retries - 1:
                    sleep_time = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Ollama connection/decode error '%s', retrying in %.1fs (attempt %d/%d)",
                        exc, sleep_time, attempt + 1, max_retries
                    )
                    if cancel_event is not None and cancel_event.wait(timeout=sleep_time):
                        raise RuntimeError("Operation cancelled by user")
                    elif cancel_event is None:
                        time.sleep(sleep_time)
                    continue
                raise RuntimeError(f"Ollama connection failed after {max_retries} attempts: {exc}") from exc
        if last_exc:
            raise last_exc
        return {}

    @classmethod
    def build_stream_payload(
        cls,
        model_id: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        num_ctx: int = 4096,
        think: Optional[bool] = None,
        **kwargs: Any,
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
                "repeat_penalty": 1.15,
                "repeat_last_n": 64,
            },
            "think": cls.resolve_think_mode(model_id, think if think is not None else kwargs.get("think")),
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
        cancel_event: Optional[threading.Event] = None,
        think: Optional[bool] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Native tool calling via /api/chat `tools`. Returns {content, tool_calls, usage}."""
        est_tokens = self.estimate_tokens(messages) + self.estimate_tokens(json.dumps(tools))
        needed = max(8192, int(num_ctx or 0), est_tokens + max_tokens + 512)
        effective_ctx = self.budget_num_ctx(model_id, est_tokens, needed)
        if est_tokens + max_tokens > effective_ctx:
            logger.warning(
                "Ollama chat_with_tools: ~%d prompt tokens + %d output exceed num_ctx=%d for %s; "
                "Ollama will truncate the oldest context.", est_tokens, max_tokens, effective_ctx, model_id,
            )
        resolved_think = self.resolve_think_mode(model_id, think if think is not None else kwargs.get("think"))
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "tools": [{"type": "function", "function": t} for t in tools],
            "stream": False,
            "think": resolved_think,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": effective_ctx,
                "repeat_penalty": 1.15,
                "repeat_last_n": 64,
            },
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        req = urllib.request.Request(
            f"http://{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/2"},
            method="POST",
        )
        try:
            data = self._request_with_retry(req, timeout=self.timeout, cancel_event=cancel_event)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            if exc.code == 400 and "does not support thinking" in body and payload.get("think"):
                logger.info(
                    "Ollama model '%s' does not support native thinking parameter in chat_with_tools; retrying with think=False",
                    model_id,
                )
                payload["think"] = False
                retry_req = urllib.request.Request(
                    f"http://{self.host}/api/chat",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/2"},
                    method="POST",
                )
                data = self._request_with_retry(retry_req, timeout=self.timeout, cancel_event=cancel_event)
            else:
                raise exc
        if "error" in data:
            raise RuntimeError(f"Ollama API error: {data['error']}")
        msg = data.get("message", {}) or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            if not isinstance(c, dict):
                continue
            fn = c.get("function")
            if not isinstance(fn, dict):
                fn = c
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
            name = fn.get("name")
            call_id = c.get("id") or c.get("call_id") or fn.get("id")
            calls.append({"name": name, "arguments": args, "id": call_id})
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
        timeout_s: float = 300.0,
        **kwargs: Any,
    ) -> Optional[str]:
        """Structured output via /api/chat `format` (JSON schema). Returns clean JSON text or None on transport errors.

        The default timeout is 300 s: a cold 14-27B model on a 12 GB GPU regularly needed more than the old 120 s to
        load and answer a design request, which silently dropped every prompt to the offline fallback."""
        est_tokens = self.estimate_tokens(system, user, json.dumps(schema))
        effective_ctx = self.budget_num_ctx(model_id, est_tokens, num_ctx)
        payload = {
            "model": model_id,
            "stream": False,
            "think": self.resolve_think_mode(model_id, kwargs.get("think")),
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
        except (urllib.error.HTTPError, RuntimeError) as exc:
            logger.warning("Ollama complete_json HTTP/Runtime error: %s", exc)
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

    @classmethod
    def build_chat_payload(
        cls,
        model_id: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        num_ctx: int = 4096,
        think: Optional[bool] = None,
        **kwargs: Any,
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
                "repeat_penalty": 1.15,
                "repeat_last_n": 64,
            },
            "think": cls.resolve_think_mode(model_id, think if think is not None else kwargs.get("think")),
        }

    @staticmethod
    def parse_stream_lines(lines) -> Iterator[StreamChunk]:
        """Decode Ollama's newline-delimited JSON response records from /api/chat or /api/generate."""
        saw_done = False
        in_thinking_field = False
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

            thinking_token = ""
            content_token = ""
            if "message" in chunk and isinstance(chunk["message"], dict):
                msg = chunk["message"]
                thinking_token = msg.get("thinking", "") or ""
                content_token = msg.get("content", "") or ""
            elif "response" in chunk:
                content_token = chunk.get("response", "") or ""
            if not thinking_token and "thinking" in chunk and isinstance(chunk.get("thinking"), str):
                thinking_token = chunk.get("thinking", "") or ""

            tokens_to_yield = []
            if thinking_token:
                if not in_thinking_field:
                    in_thinking_field = True
                    tokens_to_yield.append("<think>")
                tokens_to_yield.append(thinking_token)

            if content_token:
                if in_thinking_field:
                    in_thinking_field = False
                    tokens_to_yield.append("</think>")
                tokens_to_yield.append(content_token)

            if done and in_thinking_field:
                in_thinking_field = False
                tokens_to_yield.append("</think>")

            token = "".join(tokens_to_yield)
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
        """Stream completion tokens from Ollama /api/chat.

        The blocking HTTP read runs on a worker thread and hands chunks to the event loop through
        a queue, so (a) other coroutines keep running while the model generates, and (b) closing
        the generator (the consumer breaks out, e.g. on user cancel) or setting the optional
        ``cancel_event`` (threading.Event) closes the HTTP response, which makes Ollama stop
        generating instead of burning GPU time on an abandoned answer.
        """
        url = f"http://{self.host}/api/chat"
        est_tokens = self.estimate_tokens(messages, system_prompt)
        resolved_ctx = self.budget_num_ctx(model_id, est_tokens + max_tokens, kwargs.get("num_ctx"))
        if est_tokens + max_tokens > resolved_ctx:
            logger.warning(
                "Ollama stream_chat: ~%d prompt tokens + %d output exceed num_ctx=%d for %s; "
                "Ollama will truncate the oldest context.", est_tokens, max_tokens, resolved_ctx, model_id,
            )

        payload = self.build_chat_payload(
            model_id=model_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=resolved_ctx,
            think=kwargs.get("think"),
        )
        if kwargs.get("keep_alive") is not None:
            payload["keep_alive"] = kwargs["keep_alive"]

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/1.0"},
            method="POST",
        )

        external_cancel: Optional[threading.Event] = kwargs.get("cancel_event")
        stop = threading.Event()
        loop = asyncio.get_running_loop()
        queue: "asyncio.Queue[Optional[StreamChunk]]" = asyncio.Queue()
        holder: Dict[str, Any] = {}

        def _put(item: Optional[StreamChunk]) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:
                pass  # event loop already closed

        def _reader() -> None:
            nonlocal req
            try:
                try:
                    resp = urllib.request.urlopen(req, timeout=self.timeout)
                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                    if e.code == 400 and "does not support thinking" in body and payload.get("think"):
                        logger.info(
                            "Ollama model '%s' does not support native thinking parameter in stream_chat; retrying with think=False",
                            model_id,
                        )
                        payload["think"] = False
                        req = urllib.request.Request(
                            url,
                            data=json.dumps(payload).encode("utf-8"),
                            headers={"Content-Type": "application/json", "User-Agent": "GameForge-IDE/1.0"},
                            method="POST",
                        )
                        resp = urllib.request.urlopen(req, timeout=self.timeout)
                    else:
                        raise e

                with resp:
                    holder["resp"] = resp
                    for chunk in self.parse_stream_lines(resp):
                        if stop.is_set() or (external_cancel is not None and external_cancel.is_set()):
                            break
                        _put(chunk)
                        if chunk.is_final:
                            break
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                if not stop.is_set():
                    _put(StreamChunk(token="", is_final=True, error=f"Ollama HTTP {e.code}: {body or e.reason}"))
            except urllib.error.URLError as e:
                if not stop.is_set():
                    _put(StreamChunk(
                        token="",
                        is_final=True,
                        error=f"Local Ollama connection failure: {e.reason}. Ensure 'ollama serve' is running.",
                    ))
            except Exception as e:  # socket timeouts, resets, decoding errors
                if not stop.is_set():
                    _put(StreamChunk(token="", is_final=True, error=f"Ollama streaming error: {e}"))
            finally:
                _put(None)

        worker = threading.Thread(target=_reader, name="ollama-stream", daemon=True)
        worker.start()
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
                if item.is_final:
                    break
                if external_cancel is not None and external_cancel.is_set():
                    break
        finally:
            stop.set()
            resp = holder.get("resp")
            if resp is not None:
                try:
                    resp.close()  # disconnecting makes Ollama abort the generation
                except Exception:
                    pass

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
        est_tokens = self.estimate_tokens(prompt, system_prompt)
        resolved_ctx = self.budget_num_ctx(model_id, est_tokens + max_tokens, kwargs.get("num_ctx"))
        payload = {
            "model": model_id,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": resolved_ctx,
                "repeat_penalty": 1.15,
                "repeat_last_n": 64,
            },
            "think": self.resolve_think_mode(model_id, kwargs.get("think")),
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
