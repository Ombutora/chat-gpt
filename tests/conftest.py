"""A tiny fake OpenAI-compatible server, so the chat engine can be tested without an API key."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class FakeServer:
    def __init__(self):
        self.responses: list = []  # each: list of delta dicts to stream, or an int HTTP error status
        self.requests: list[dict] = []
        handler = self._make_handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                server.requests.append(body)
                response = server.responses.pop(0)
                if isinstance(response, int):
                    self.send_response(response)
                    self.send_header("content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": {"message": "boom"}}).encode())
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                for delta in response:
                    chunk = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                             "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")

        return Handler


@pytest.fixture
def fake_server():
    server = FakeServer()
    yield server
    server.httpd.shutdown()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Keep the developer's real keys and .env settings out of the tests.
    for var in ("TORA_PROVIDER", "TORA_BASE_URL", "TORA_API_KEY", "TORA_MODEL", "TORA_REASONING_EFFORT", "TORA_TEMPERATURE",
                "TORA_TOOLS", "TORA_PYTHON_BACKEND", "TORA_SYSTEM_PROMPT", "OPENROUTER_API_KEY", "GROQ_API_KEY", "HF_TOKEN",
                "EXA_API_KEY", "YDC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
