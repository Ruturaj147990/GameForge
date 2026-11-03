"""Hosted heavy-model tier (Master Blueprint v2 §3, §6).

Pieces:
  * HostedProfile / load_profiles   provider + model declarations (disabled by default)
  * CredentialStore                 Windows Credential Manager (ctypes) or environment variable
  * EgressPolicy                    per-workspace opt-in: <workspace>/.gameforge/egress.json
  * SpendLedger                     per-task / per-day caps enforced BEFORE a call
  * OpenAICompatibleHostedProvider  /v1/chat/completions (streaming SSE, tools)
  * AnthropicProvider               /v1/messages (streaming SSE, tools)
  * GuardedProvider                 wraps any hosted provider with egress + spend + no-fallback

Nothing here sends data anywhere unless a profile is enabled AND the workspace opted in AND
a credential exists AND the spend cap allows the call.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from .base import ChatResponse, ModelInfo, ModelProvider, ProviderCapabilities, StreamChunk

DEFAULT_PROFILES = Path(__file__).resolve().parents[2] / "config" / "hosted_providers.default.json"


def user_config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "GameForge"


# ── profiles ────────────────────────────────────────────────────────────────

@dataclass
class HostedModel:
    id: str
    display_name: str
    max_context: int
    supports_tools: bool = True
    supports_images: bool = False
    usd_per_mtok_in: float = 0.0
    usd_per_mtok_out: float = 0.0
    roles: List[str] = field(default_factory=list)


@dataclass
class HostedProfile:
    provider_id: str
    kind: str  # "openai_compatible" | "anthropic" | "gameforge_gateway"
    base_url: str
    models: List[HostedModel]
    enabled: bool = False
    api_key_env: Optional[str] = None
    data_policy: str = ""
    per_task_usd_cap: float = 5.0
    per_day_usd_cap: float = 20.0
    timeout_s: float = 300.0
    unmetered: bool = False  # e.g. a self-hosted GameForge gateway; otherwise prices are mandatory

    def model(self, model_id: str) -> Optional[HostedModel]:
        return next((m for m in self.models if m.id == model_id), None)


def load_profiles(paths: Optional[List[Path]] = None) -> Dict[str, HostedProfile]:
    """Shipped defaults, then the user's override file (%APPDATA%/GameForge/hosted_providers.json)."""
    paths = paths or [DEFAULT_PROFILES, user_config_dir() / "hosted_providers.json"]
    out: Dict[str, HostedProfile] = {}
    for p in paths:
        if not Path(p).is_file():
            continue
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        for raw in data.get("providers", []):
            models = [HostedModel(**m) for m in raw.pop("models", [])]
            prof = HostedProfile(models=models, **raw)
            out[prof.provider_id] = prof
    return out


# ── credentials ─────────────────────────────────────────────────────────────

class _CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


class CredentialStore:
    """API keys live in Windows Credential Manager (target 'GameForge/<provider_id>') or an env var.

    Keys are never written to config files, logs, ledgers or session transcripts.
    """
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    @staticmethod
    def _target(provider_id: str) -> str:
        return f"GameForge/{provider_id}"

    def get(self, profile: HostedProfile) -> Optional[str]:
        if sys.platform == "win32":
            ptr = ctypes.POINTER(_CREDENTIAL)()
            advapi = ctypes.windll.advapi32
            if advapi.CredReadW(self._target(profile.provider_id), self.CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
                try:
                    c = ptr.contents
                    blob = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
                    return blob.decode("utf-16-le")
                finally:
                    advapi.CredFree(ptr)
        if profile.api_key_env:
            return os.environ.get(profile.api_key_env) or None
        return None

    def set(self, provider_id: str, secret: str) -> bool:
        if sys.platform != "win32":
            return False
        blob = secret.encode("utf-16-le")
        buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = _CREDENTIAL(Type=self.CRED_TYPE_GENERIC, TargetName=self._target(provider_id),
                           CredentialBlobSize=len(blob), CredentialBlob=buf,
                           Persist=self.CRED_PERSIST_LOCAL_MACHINE, UserName="GameForge")
        return bool(ctypes.windll.advapi32.CredWriteW(ctypes.byref(cred), 0))

    def delete(self, provider_id: str) -> bool:
        if sys.platform != "win32":
            return False
        return bool(ctypes.windll.advapi32.CredDeleteW(self._target(provider_id), self.CRED_TYPE_GENERIC, 0))


def redact(text: str, secret: Optional[str]) -> str:
    return text.replace(secret, "***REDACTED***") if secret and secret in text else text


# ── egress and spend ────────────────────────────────────────────────────────

class EgressPolicy:
    def __init__(self, workspace_root: Path):
        self.path = Path(workspace_root) / ".gameforge" / "egress.json"

    def allowed(self) -> List[str]:
        if not self.path.is_file():
            return []
        try:
            return list(json.loads(self.path.read_text(encoding="utf-8")).get("allowed_providers", []))
        except (OSError, json.JSONDecodeError):
            return []

    def is_allowed(self, provider_id: str) -> bool:
        return provider_id in self.allowed()

    def allow(self, provider_id: str) -> None:
        cur = sorted(set(self.allowed()) | {provider_id})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"allowed_providers": cur}, indent=1), encoding="utf-8")

    def revoke(self, provider_id: str) -> None:
        cur = [p for p in self.allowed() if p != provider_id]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"allowed_providers": cur}, indent=1), encoding="utf-8")


class SpendCapExceeded(RuntimeError):
    pass


class SpendLedger:
    def __init__(self, workspace_root: Path):
        self.path = Path(workspace_root) / ".gameforge" / "spend.jsonl"
        self._lock = threading.Lock()

    def _entries(self) -> Iterator[Dict]:
        if not self.path.is_file():
            return iter(())
        entries = []
        with open(self.path, encoding="utf-8") as fh:
            for l in fh:
                line = l.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue  # Gracefully skip corrupted or partial lines from crashed processes
        return iter(entries)

    def spent(self, provider_id: str, task_id: Optional[str] = None, day: Optional[str] = None) -> float:
        day = day or time.strftime("%Y-%m-%d")
        total = 0.0
        for e in self._entries():
            if e["provider_id"] != provider_id:
                continue
            if task_id is not None and e.get("task_id") != task_id:
                continue
            if task_id is None and e["day"] != day:
                continue
            total += e["usd"]
        return total

    def check(self, profile: HostedProfile, task_id: Optional[str], estimate_usd: float) -> None:
        day_spent = self.spent(profile.provider_id)
        if day_spent + estimate_usd > profile.per_day_usd_cap:
            raise SpendCapExceeded(f"daily cap ${profile.per_day_usd_cap:.2f} for {profile.provider_id} "
                                   f"would be exceeded (spent ${day_spent:.4f})")
        if task_id:
            task_spent = self.spent(profile.provider_id, task_id=task_id)
            if task_spent + estimate_usd > profile.per_task_usd_cap:
                raise SpendCapExceeded(f"per-task cap ${profile.per_task_usd_cap:.2f} would be exceeded "
                                       f"(task spent ${task_spent:.4f})")

    def record(self, profile: HostedProfile, model: HostedModel, task_id: Optional[str],
               tokens_in: int, tokens_out: int) -> float:
        usd = tokens_in / 1e6 * model.usd_per_mtok_in + tokens_out / 1e6 * model.usd_per_mtok_out
        entry = {"ts": time.time(), "day": time.strftime("%Y-%m-%d"), "provider_id": profile.provider_id,
                 "model": model.id, "task_id": task_id, "tokens_in": tokens_in, "tokens_out": tokens_out,
                 "usd": round(usd, 6)}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return usd


# ── HTTP helpers ────────────────────────────────────────────────────────────

def _post_json(url: str, headers: Dict[str, str], body: Dict, timeout: float) -> Dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _sse_lines(url: str, headers: Dict[str, str], body: Dict, timeout: float) -> Iterator[Dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Accept": "text/event-stream",
                                          **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                continue


async def _iterate_in_thread(gen_factory) -> AsyncIterator[Any]:
    """Run a blocking generator in a thread and yield its items asynchronously."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    def worker():
        try:
            for item in gen_factory():
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:  # surfaced to the consumer
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = await queue.get()
        if item is sentinel:
            return
        if isinstance(item, Exception):
            raise item
        yield item


# ── providers ───────────────────────────────────────────────────────────────

class _HostedBase(ModelProvider):
    def __init__(self, profile: HostedProfile, credentials: Optional[CredentialStore] = None):
        self.profile = profile
        self.credentials = credentials or CredentialStore()
        self.last_usage: Dict[str, int] = {}

    def get_provider_id(self) -> str:
        return self.profile.provider_id

    def is_available(self) -> bool:
        return self.profile.enabled and bool(self.credentials.get(self.profile))

    def list_models(self) -> List[ModelInfo]:
        return [ModelInfo(id=m.id, name=m.display_name, provider=self.profile.provider_id, is_local=False,
                          description=f"{self.profile.kind} @ {self.profile.base_url}") for m in self.profile.models]

    def get_capabilities(self, model_id: str) -> ProviderCapabilities:
        m = self.profile.model(model_id)
        return ProviderCapabilities(supports_streaming=True, supports_tools=bool(m and m.supports_tools),
                                    supports_images=bool(m and m.supports_images),
                                    max_context=m.max_context if m else 8192)

    def _key(self) -> str:
        key = self.credentials.get(self.profile)
        if not key:
            raise PermissionError(f"no credential for hosted provider '{self.profile.provider_id}'")
        return key


class OpenAICompatibleHostedProvider(_HostedBase):
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._key()}", "User-Agent": "GameForge-IDE/2"}

    def _body(self, model_id, messages, system_prompt, temperature, max_tokens, stream, tools=None):
        msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + list(messages)
        body = {"model": model_id, "messages": msgs, "temperature": temperature, "max_tokens": max_tokens,
                "stream": stream}
        if stream:
            body["stream_options"] = {"include_usage": True}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        return body

    async def stream_chat(self, model_id, messages, system_prompt=None, temperature=0.2, max_tokens=2048, **kw):
        url = self.profile.base_url.rstrip("/") + "/chat/completions"
        body = self._body(model_id, messages, system_prompt, temperature, max_tokens, True, kw.get("tools"))
        headers = self._headers()
        usage: Dict[str, int] = {}
        async for ev in _iterate_in_thread(lambda: _sse_lines(url, headers, body, self.profile.timeout_s)):
            if ev.get("usage"):
                usage = {"prompt_tokens": ev["usage"].get("prompt_tokens", 0),
                         "completion_tokens": ev["usage"].get("completion_tokens", 0)}
            for ch in ev.get("choices", []):
                tok = (ch.get("delta") or {}).get("content")
                if tok:
                    yield StreamChunk(token=tok)
        self.last_usage = usage
        yield StreamChunk(token="", is_final=True, metadata={"usage": usage})

    def complete(self, model_id, prompt, system_prompt=None, temperature=0.2, max_tokens=2048, **kw) -> ChatResponse:
        url = self.profile.base_url.rstrip("/") + "/chat/completions"
        data = _post_json(url, self._headers(), self._body(model_id, [{"role": "user", "content": prompt}],
                                                           system_prompt, temperature, max_tokens, False,
                                                           kw.get("tools")), self.profile.timeout_s)
        choice = data["choices"][0]
        usage = {"prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                 "completion_tokens": data.get("usage", {}).get("completion_tokens", 0)}
        self.last_usage = usage
        return ChatResponse(content=choice["message"].get("content") or "", model=model_id,
                            finish_reason=choice.get("finish_reason", "stop"), usage=usage,
                            metadata={"tool_calls": choice["message"].get("tool_calls") or []})


class AnthropicProvider(_HostedBase):
    API_VERSION = "2023-06-01"

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self._key(), "anthropic-version": self.API_VERSION, "User-Agent": "GameForge-IDE/2"}

    @staticmethod
    def _convert(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        out = []
        for m in messages:
            role = "assistant" if m.get("role") == "assistant" else "user"
            if out and out[-1]["role"] == role:  # API requires alternating roles
                out[-1]["content"] += "\n\n" + m.get("content", "")
            else:
                out.append({"role": role, "content": m.get("content", "")})
        return out

    def _body(self, model_id, messages, system_prompt, temperature, max_tokens, stream, tools=None):
        body = {"model": model_id, "max_tokens": max_tokens, "messages": self._convert(messages),
                "temperature": temperature, "stream": stream}
        if system_prompt:
            body["system"] = system_prompt
        if tools:
            body["tools"] = [{"name": t["name"], "description": t.get("description", ""),
                              "input_schema": t.get("parameters", {"type": "object"})} for t in tools]
        return body

    async def stream_chat(self, model_id, messages, system_prompt=None, temperature=0.2, max_tokens=2048, **kw):
        url = self.profile.base_url.rstrip("/") + "/messages"
        body = self._body(model_id, messages, system_prompt, temperature, max_tokens, True, kw.get("tools"))
        headers = self._headers()
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        async for ev in _iterate_in_thread(lambda: _sse_lines(url, headers, body, self.profile.timeout_s)):
            t = ev.get("type")
            if t == "message_start":
                usage["prompt_tokens"] = ev.get("message", {}).get("usage", {}).get("input_tokens", 0)
            elif t == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                yield StreamChunk(token=ev["delta"].get("text", ""))
            elif t == "message_delta":
                usage["completion_tokens"] = ev.get("usage", {}).get("output_tokens", usage["completion_tokens"])
            elif t == "error":
                yield StreamChunk(token="", is_final=True, error=str(ev.get("error")))
                return
        self.last_usage = usage
        yield StreamChunk(token="", is_final=True, metadata={"usage": usage})

    def complete(self, model_id, prompt, system_prompt=None, temperature=0.2, max_tokens=2048, **kw) -> ChatResponse:
        url = self.profile.base_url.rstrip("/") + "/messages"
        data = _post_json(url, self._headers(), self._body(model_id, [{"role": "user", "content": prompt}],
                                                           system_prompt, temperature, max_tokens, False,
                                                           kw.get("tools")), self.profile.timeout_s)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        calls = [{"name": b["name"], "arguments": b.get("input", {})} for b in data.get("content", [])
                 if b.get("type") == "tool_use"]
        usage = {"prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                 "completion_tokens": data.get("usage", {}).get("output_tokens", 0)}
        self.last_usage = usage
        return ChatResponse(content=text, model=model_id, finish_reason=data.get("stop_reason", "end_turn"),
                            usage=usage, metadata={"tool_calls": calls})


PROVIDER_KINDS = {"openai_compatible": OpenAICompatibleHostedProvider, "gameforge_gateway": OpenAICompatibleHostedProvider,
                  "anthropic": AnthropicProvider}


class EgressBlocked(PermissionError):
    pass


class GuardedProvider(ModelProvider):
    """Enforces, before every hosted call: enabled profile, workspace opt-in, credential, spend cap."""

    def __init__(self, inner: _HostedBase, workspace_root: Path, task_id_getter=lambda: None):
        self.inner = inner
        self.profile = inner.profile
        self.egress = EgressPolicy(workspace_root)
        self.ledger = SpendLedger(workspace_root)
        self.task_id_getter = task_id_getter

    def get_provider_id(self) -> str:
        return self.inner.get_provider_id()

    def is_available(self) -> bool:
        return self.inner.is_available() and self.egress.is_allowed(self.profile.provider_id)

    def list_models(self) -> List[ModelInfo]:
        return self.inner.list_models()

    def get_capabilities(self, model_id: str) -> ProviderCapabilities:
        return self.inner.get_capabilities(model_id)

    def preflight(self, model_id: str, est_in_tokens: int, max_tokens: int) -> HostedModel:
        if not self.profile.enabled:
            raise EgressBlocked(f"hosted provider '{self.profile.provider_id}' is disabled")
        if not self.egress.is_allowed(self.profile.provider_id):
            raise EgressBlocked(f"workspace has not opted in to '{self.profile.provider_id}' "
                                f"(add it to .gameforge/egress.json via Settings)")
        model = self.profile.model(model_id)
        if model is None:
            raise EgressBlocked(f"model '{model_id}' is not declared in profile '{self.profile.provider_id}'")
        if not self.profile.unmetered and model.usd_per_mtok_in <= 0 and model.usd_per_mtok_out <= 0:
            raise EgressBlocked(f"prices for '{model_id}' are not configured; spend caps cannot be enforced")
        est = est_in_tokens / 1e6 * model.usd_per_mtok_in + max_tokens / 1e6 * model.usd_per_mtok_out
        self.ledger.check(self.profile, self.task_id_getter(), est)
        return model

    async def stream_chat(self, model_id, messages, system_prompt=None, temperature=0.2, max_tokens=2048, **kw):
        est_in = sum(len(m.get("content", "")) for m in messages) // 3 + len(system_prompt or "") // 3
        try:
            model = self.preflight(model_id, est_in, max_tokens)
        except (EgressBlocked, SpendCapExceeded) as exc:
            yield StreamChunk(token="", is_final=True, error=f"HOSTED_BLOCKED: {exc}")
            return
        try:
            async for chunk in self.inner.stream_chat(model_id, messages, system_prompt, temperature, max_tokens, **kw):
                if chunk.is_final and chunk.metadata.get("usage"):
                    u = chunk.metadata["usage"]
                    usd = self.ledger.record(self.profile, model, self.task_id_getter(),
                                             u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
                    chunk.metadata["usd"] = round(usd, 6)
                yield chunk
        except urllib.error.HTTPError as exc:
            # No silent fallback: report the provider failure as-is (secret redacted).
            body = exc.read().decode("utf-8", "replace")[:400] if hasattr(exc, "read") else ""
            yield StreamChunk(token="", is_final=True,
                              error=redact(f"HOSTED_HTTP_{exc.code}: {body}", self.inner.credentials.get(self.profile)))
        except Exception as exc:
            yield StreamChunk(token="", is_final=True, error=f"HOSTED_ERROR: {type(exc).__name__}: {exc}")

    def complete(self, model_id, prompt, system_prompt=None, temperature=0.2, max_tokens=2048, **kw) -> ChatResponse:
        model = self.preflight(model_id, len(prompt) // 3 + len(system_prompt or "") // 3, max_tokens)
        resp = self.inner.complete(model_id, prompt, system_prompt, temperature, max_tokens, **kw)
        usd = self.ledger.record(self.profile, model, self.task_id_getter(),
                                 resp.usage.get("prompt_tokens", 0), resp.usage.get("completion_tokens", 0))
        resp.metadata["usd"] = round(usd, 6)
        return resp


def build_guarded_providers(workspace_root: Path, profiles: Optional[Dict[str, HostedProfile]] = None) -> Dict[str, GuardedProvider]:
    out: Dict[str, GuardedProvider] = {}
    for pid, prof in (profiles if profiles is not None else load_profiles()).items():
        cls = PROVIDER_KINDS.get(prof.kind)
        if cls is None:
            continue
        out[pid] = GuardedProvider(cls(prof), workspace_root)
    return out
