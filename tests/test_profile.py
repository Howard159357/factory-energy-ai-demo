"""The profiler against a local fake streaming server that serves one request at a time."""

import http.server
import json
import threading
import time

import pytest

from factory_energy.evaluation.profile import Level, Sample, markdown, profile, run_level
from factory_energy.llm.factory import LLMSettings

TOKENS = 10
DELAY_S = 0.05  # per token; large next to Windows' ~15 ms sleep resolution


class _OneSlotStreamer(http.server.BaseHTTPRequestHandler):
    slot = threading.Lock()  # like a single-slot engine: concurrent requests queue

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        self.rfile.read(int(self.headers["Content-Length"]))
        with _OneSlotStreamer.slot:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for index in range(TOKENS):
                time.sleep(DELAY_S)
                chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                         "choices": [{"index": 0, "delta": {"content": f"t{index} "},
                                      "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
            usage = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                     "choices": [], "usage": {"prompt_tokens": 30, "completion_tokens": TOKENS,
                                              "total_tokens": 30 + TOKENS}}
            self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())
            self.wfile.flush()

    def log_message(self, *args: object) -> None: ...


def test_profile_measures_ttft_decode_and_queueing() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _OneSlotStreamer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        settings = LLMSettings("openai_compatible", f"http://127.0.0.1:{server.server_address[1]}/v1",
                               "m", "", 0.0, 64, {})
        levels = profile(settings, levels=(1, 2), rounds=2, max_tokens=32, warmup=False)
    finally:
        server.shutdown()
    one, two = (level.summary() for level in levels)
    assert one["requests"] == 2 and one["errors"] == 0 and two["requests"] == 4
    assert one["completion_tokens_median"] == TOKENS  # taken from the server's usage chunk
    assert one["ttft_median_s"] < one["latency_median_s"]
    assert one["decode_tok_s_median"] > 0
    # One slot: with two users the slowest first token waits for a whole other request.
    assert two["ttft_max_s"] > one["ttft_median_s"] + 0.6 * one["latency_median_s"]
    assert two["throughput_tok_s"] < 1.5 * one["throughput_tok_s"]  # no gain from a 2nd user
    text = markdown(levels, "test / fake server")
    assert "# Inference profile: test / fake server" in text and "| 2 | 4 | 0 |" in text


def test_errors_are_counted_not_raised() -> None:
    level = Level(1, 1.0, [Sample(0.0, 0.5, 0, 0, "ConnectionError: refused")])
    assert level.summary() == {"users": 1, "requests": 1, "errors": 1}
    assert "ConnectionError" in markdown([level], "x")


def test_a_failing_client_factory_raises_instead_of_hanging() -> None:
    def broken() -> object:
        raise RuntimeError("no client")

    with pytest.raises(RuntimeError, match="no client"):
        run_level(broken, "m", users=3, rounds=1, max_tokens=8, extra_body={})
