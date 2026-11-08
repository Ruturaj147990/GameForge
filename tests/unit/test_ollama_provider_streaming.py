"""OllamaProvider: threaded/cancellable streaming, sticky num_ctx and timeout handling (fake server)."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider


class _Handler(BaseHTTPRequestHandler):
    tokens = 50
    delay = 0.01
    seen = []

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode())
        type(self).seen.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            for i in range(self.tokens):
                self.wfile.write((json.dumps({"message": {"content": f"t{i} "}, "done": False}) + "\n").encode())
                self.wfile.flush()
                time.sleep(self.delay)
            self.wfile.write((json.dumps({"message": {"content": ""}, "done": True, "eval_count": 3}) + "\n").encode())
        except (BrokenPipeError, ConnectionResetError):
            type(self).aborted = True


@pytest.fixture()
def server():
    _Handler.seen = []
    _Handler.aborted = False
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _collect(provider, **kw):
    async def run():
        out = []
        async for ch in provider.stream_chat("gameforge-qwen3.5-9b", [{"role": "user", "content": "hi"}], **kw):
            out.append(ch)
        return out
    return asyncio.run(run())


def test_stream_collects_all_tokens_and_sends_think_false(server):
    _Handler.tokens, _Handler.delay = 5, 0
    p = OllamaProvider(host=server)
    chunks = _collect(p)
    text = "".join(c.token for c in chunks)
    assert text.startswith("t0 ") and "t4" in text
    assert chunks[-1].is_final
    assert _Handler.seen[-1]["think"] is False
    assert _Handler.seen[-1]["options"]["num_ctx"] >= 8192


def test_stream_cancel_event_stops_early(server):
    _Handler.tokens, _Handler.delay = 400, 0.01
    p = OllamaProvider(host=server)
    ev = threading.Event()

    async def run():
        n = 0
        async for ch in p.stream_chat("m", [{"role": "user", "content": "x"}], cancel_event=ev):
            n += 1
            if n == 3:
                ev.set()
        return n

    t0 = time.time()
    n = asyncio.run(run())
    assert n < 50
    assert time.time() - t0 < 3.0


def test_stream_does_not_block_event_loop(server):
    _Handler.tokens, _Handler.delay = 20, 0.02
    p = OllamaProvider(host=server)

    async def run():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        tk = asyncio.create_task(ticker())
        async for _ in p.stream_chat("m", [{"role": "user", "content": "x"}]):
            pass
        tk.cancel()
        return ticks

    assert asyncio.run(run()) >= 5


def test_connection_failure_yields_error_chunk():
    p = OllamaProvider(host="127.0.0.1:9")  # nothing listens on the discard port
    chunks = _collect(p)
    assert chunks and chunks[-1].is_final and chunks[-1].error


def test_sticky_num_ctx_never_shrinks_and_is_bucketed():
    p = OllamaProvider()
    model = "gameforge-qwen3.5-9b-sticky-test"
    OllamaProvider._sticky_ctx.pop(model, None)
    big = p.budget_num_ctx(model, 0, 20000)
    small = p.budget_num_ctx(model, 0, 8192)
    assert big == 32768 and small == 32768


def test_host_with_scheme_is_normalised():
    assert OllamaProvider(host="http://127.0.0.1:11434/").host == "127.0.0.1:11434"
