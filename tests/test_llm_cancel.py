"""Stopping a model call really stops it: the Codex process tree dies, the HTTP request ends."""

import http.server
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from factory_energy.llm import openai_compatible
from factory_energy.llm.base import LLMError, cancel, close
from factory_energy.llm.codex_cli import CodexCLIClient
from factory_energy.llm.openai_compatible import OpenAICompatibleClient

# A parent that starts a child and both sleep: the shape of codex.cmd starting Node.
TREE = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(sys.argv[1], "w").write(str(child.pid))
time.sleep(120)
"""


def alive(pid: int) -> bool:
    if os.name == "nt":
        listing = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, check=False).stdout
        return str(pid) in listing
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_codex_cancel_kills_the_whole_process_tree(tmp_path: Path) -> None:
    client = CodexCLIClient()
    pid_file = tmp_path / "child.pid"
    errors: list[BaseException] = []

    def call() -> None:
        try:
            client.runner([sys.executable, "-c", TREE, str(pid_file)], "", tmp_path)
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    worker = threading.Thread(target=call)
    began = time.monotonic()
    worker.start()
    deadline = time.monotonic() + 20
    while not pid_file.exists() or not pid_file.read_text():
        assert time.monotonic() < deadline, "child never started"
        time.sleep(0.1)
    child = int(pid_file.read_text())
    assert alive(child)
    assert cancel(client)
    worker.join(timeout=15)
    assert not worker.is_alive() and time.monotonic() - began < 30
    time.sleep(0.5)
    assert not alive(child)  # the grandchild went too, not only the wrapper
    with pytest.raises(LLMError, match="cancelled"):  # and the client refuses further calls
        client.runner([sys.executable, "-c", "pass"], "", tmp_path)


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    """A model that takes its time; it notices when the client goes away, as vLLM does."""

    disconnected = threading.Event()

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        self.rfile.read(int(self.headers["Content-Length"]))
        self.connection.settimeout(20)
        try:
            if self.connection.recv(1) == b"":  # EOF: the client shut the connection down
                _SlowHandler.disconnected.set()
        except OSError:
            _SlowHandler.disconnected.set()

    def log_message(self, *args: object) -> None: ...


def test_openai_compatible_cancel_ends_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both halves of a stop: the caller stops waiting at once, and the server sees the client
    disconnect (on Linux a plain close() would not wake the blocked read)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = OpenAICompatibleClient(f"http://127.0.0.1:{server.server_address[1]}/v1", "m",
                                    timeout=60, max_retries=0)
    errors: list[BaseException] = []

    def call() -> None:
        try:
            client.complete([{"role": "user", "content": "hi"}], [])
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    worker = threading.Thread(target=call)
    worker.start()
    time.sleep(0.5)
    began = time.monotonic()
    shut: list[int] = []
    real = openai_compatible._shutdown_sockets
    monkeypatch.setattr(openai_compatible, "_shutdown_sockets",
                        lambda c: shut.append(real(c)) or shut[-1])
    client.cancel()
    worker.join(timeout=10)
    try:
        assert shut and shut[0] >= 1, "no socket found: httpx/httpcore internals changed?"
        assert not worker.is_alive() and time.monotonic() - began < 2
        assert isinstance(errors[0], LLMError) and "cancelled" in str(errors[0])
        assert _SlowHandler.disconnected.wait(5), "the server never saw the client go away"
    finally:
        server.shutdown()


def test_backends_without_cancel_are_left_alone() -> None:
    assert cancel(object()) is False


def test_close_is_safe_twice_and_skipped_for_clients_without_it() -> None:
    client = OpenAICompatibleClient("http://127.0.0.1:1/v1", "m")
    close(client)
    close(client)
    close(object())
