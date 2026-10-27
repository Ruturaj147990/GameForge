"""Hosted heavy-model tier: gates, ledger, credentials and real HTTP/SSE paths against a local mock."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.gameforge_ide.backend.providers.hosted import (
    AnthropicProvider, CredentialStore, EgressBlocked, EgressPolicy, GuardedProvider, HostedModel,
    HostedProfile, OpenAICompatibleHostedProvider, SpendCapExceeded, SpendLedger, load_profiles, redact)
from src.gameforge_ide.backend.providers.router import ModelRouter

SEEN = []


class _Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        if self.path.endswith("/messages"):
            if body.get("stream"):
                events = [{"type": "message_start", "message": {"usage": {"input_tokens": 1000}}},
                          {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}},
                          {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}},
                          {"type": "message_delta", "usage": {"output_tokens": 500}}]
                return self._sse(events)
            return self._json({"content": [{"type": "text", "text": "ok"},
                                           {"type": "tool_use", "name": "list_dir", "input": {"subpath": ""}}],
                               "stop_reason": "tool_use", "usage": {"input_tokens": 10, "output_tokens": 5}})
        if body.get("stream"):
            return self._sse([{"choices": [{"delta": {"content": "Hi"}}]},
                              {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}], done=True)
        return self._json({"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 2, "completion_tokens": 1}})

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _sse(self, events, done=False):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for e in events:
            self.wfile.write(f"data: {json.dumps(e)}\n\n".encode())
        if done:
            self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


class _EnvCreds(CredentialStore):
    def get(self, profile):
        return "sk-test-SECRET"


def _profile(kind, url, **kw):
    m = HostedModel(id="m1", display_name="M1", max_context=200000, usd_per_mtok_in=3.0, usd_per_mtok_out=15.0,
                    roles=["author"], supports_images=True)
    return HostedProfile(provider_id=f"p_{kind}", kind=kind, base_url=url, models=[m], enabled=True, **kw)


def _collect(gen):
    async def run():
        return [c async for c in gen]
    return asyncio.run(run())


def test_shipped_profiles_are_all_disabled():
    profiles = load_profiles()
    assert profiles and not any(p.enabled for p in profiles.values())


def test_guard_blocks_without_workspace_opt_in(tmp_path, server):
    g = GuardedProvider(AnthropicProvider(_profile("anthropic", server), _EnvCreds()), tmp_path)
    out = _collect(g.stream_chat("m1", [{"role": "user", "content": "hi"}]))
    assert out[-1].error.startswith("HOSTED_BLOCKED") and "opted in" in out[-1].error
    assert not g.is_available()


def test_guard_blocks_unpriced_metered_model(tmp_path, server):
    prof = _profile("anthropic", server)
    prof.models[0].usd_per_mtok_in = prof.models[0].usd_per_mtok_out = 0
    EgressPolicy(tmp_path).allow(prof.provider_id)
    with pytest.raises(EgressBlocked, match="prices"):
        GuardedProvider(AnthropicProvider(prof, _EnvCreds()), tmp_path).preflight("m1", 10, 10)


def test_anthropic_stream_real_http_and_ledger(tmp_path, server):
    prof = _profile("anthropic", server)
    EgressPolicy(tmp_path).allow(prof.provider_id)
    g = GuardedProvider(AnthropicProvider(prof, _EnvCreds()), tmp_path, task_id_getter=lambda: "t1")
    out = _collect(g.stream_chat("m1", [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}],
                                 system_prompt="sys"))
    assert "".join(c.token for c in out) == "Hello"
    assert out[-1].metadata["usd"] == pytest.approx(1000 / 1e6 * 3 + 500 / 1e6 * 15)
    req = SEEN[-1]
    assert req["headers"]["x-api-key"] == "sk-test-SECRET" and req["headers"]["anthropic-version"]
    assert req["body"]["system"] == "sys" and len(req["body"]["messages"]) == 1  # merged alternating roles
    assert SpendLedger(tmp_path).spent(prof.provider_id, task_id="t1") > 0


def test_anthropic_complete_parses_tool_use(tmp_path, server):
    prof = _profile("anthropic", server)
    EgressPolicy(tmp_path).allow(prof.provider_id)
    g = GuardedProvider(AnthropicProvider(prof, _EnvCreds()), tmp_path)
    r = g.complete("m1", "x", tools=[{"name": "list_dir", "description": "d", "parameters": {"type": "object"}}])
    assert r.metadata["tool_calls"] == [{"name": "list_dir", "arguments": {"subpath": ""}}]
    assert SEEN[-1]["body"]["tools"][0]["input_schema"] == {"type": "object"}


def test_openai_compatible_stream_and_complete(tmp_path, server):
    prof = _profile("openai_compatible", server)
    EgressPolicy(tmp_path).allow(prof.provider_id)
    g = GuardedProvider(OpenAICompatibleHostedProvider(prof, _EnvCreds()), tmp_path)
    out = _collect(g.stream_chat("m1", [{"role": "user", "content": "hi"}]))
    assert "".join(c.token for c in out) == "Hi" and out[-1].metadata["usage"]["completion_tokens"] == 3
    assert SEEN[-1]["headers"]["authorization"] == "Bearer sk-test-SECRET"
    assert g.complete("m1", "ping").content == "pong"


def test_spend_caps_enforced_before_call(tmp_path):
    prof = _profile("anthropic", "http://unused", per_task_usd_cap=0.01, per_day_usd_cap=1.0)
    led = SpendLedger(tmp_path)
    led.record(prof, prof.models[0], "t", 2000, 0)  # $0.006
    led.check(prof, "t", 0.001)
    with pytest.raises(SpendCapExceeded, match="per-task"):
        led.check(prof, "t", 0.01)
    with pytest.raises(SpendCapExceeded, match="daily"):
        led.check(prof, "other", 2.0)


def test_router_routes_hosted_only_when_usable(tmp_path, server):
    prof = _profile("anthropic", server)
    router = ModelRouter()
    router.attach_hosted(tmp_path, {prof.provider_id: prof})
    router.hosted[prof.provider_id].inner.credentials = _EnvCreds()
    assert router.route_hosted("author") is None            # not opted in -> stays local
    EgressPolicy(tmp_path).allow(prof.provider_id)
    assert router.route_hosted("author") == (f"hosted:{prof.provider_id}", "m1")
    assert router.route_hosted("planner") is None


def test_redaction():
    assert redact("key=sk-1 failed", "sk-1") == "key=***REDACTED*** failed"
