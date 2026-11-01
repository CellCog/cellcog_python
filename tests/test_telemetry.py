"""Tests for cellcog.telemetry (SDK 2.8.0 error reports). No network: _send and threading are replaced.

Run: python3 tests/test_telemetry.py   (or pytest)
"""

import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests  # noqa: E402

from cellcog import telemetry  # noqa: E402

SENT = []


class _SyncThread:
    def __init__(self, target=None, args=(), **kw):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class _Cfg:
    api_key = "sk_test_never_sent_in_body"
    api_base_url = "https://cellcog.ai/api"

    def get_request_headers(self):
        return {"Authorization": "Bearer x", "X-CellCog-Python-SDK-Version": "2.8.0"}


def _setup():
    SENT.clear()
    telemetry._sent = 0
    os.environ.pop(telemetry.ENV_OFF, None)
    telemetry._send = lambda url, headers, report: SENT.append((url, report))
    telemetry.threading.Thread = _SyncThread


def test_report_shape_and_scrub():
    _setup()
    exc = requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='storage.googleapis.com'): Max retries exceeded with url: "
        "https://storage.googleapis.com/cellcog_files/human_files/x/foto.jpg?X-Goog-Signature=abc123secret "
        "reading /home/claude/sol/in/foto.jpg and C:\\Users\\Nikita\\a.png")
    telemetry.report_error(_Cfg(), "upload_put", exc, host="storage.googleapis.com",
                           path="/home/claude/sol/in/foto.jpg", mime="image/jpeg", size=480670)
    assert len(SENT) == 1
    url, r = SENT[0]
    assert url == "https://cellcog.ai/api/cellcog/sdk-errors"
    assert r["step"] == "upload_put" and r["err"] == "ConnectionError" and r["path_kind"] == "claude_sandbox"
    assert r["host"] == "storage.googleapis.com" and r["mime"] == "image/jpeg" and r["size"] == "480670"
    for leak in ("abc123secret", "X-Goog-Signature", "foto.jpg", "/home/claude", "Nikita", "sk_test"):
        assert leak not in str(r), leak
    assert "storage.googleapis.com" in r["msg"]  # control: the useful part survives


def test_path_kinds():
    k = telemetry.path_kind
    assert k("/home/claude/x.png") == "claude_sandbox" and k("/mnt/project-files/a") == "claude_sandbox"
    assert k("/tmp/claude-0/x") == "claude_sandbox" and k("/home/app/out/a.png") == "cellcog_container"
    assert k("/Users/me/a.png") == "mac" and k("C:\\Users\\me\\a.png") == "windows" and k("C:/x/a.png") == "windows"
    assert k("/home/bob/a.png") == "linux" and k("rel/a.png") == "relative" and k("") == "empty"
    assert k("https://x.com/a") == "url"


def test_off_switch():
    _setup()
    os.environ[telemetry.ENV_OFF] = "1"
    telemetry.report_error(_Cfg(), "api", RuntimeError("x"))
    assert SENT == []
    os.environ.pop(telemetry.ENV_OFF)
    telemetry.report_error(_Cfg(), "api", RuntimeError("x"))
    assert len(SENT) == 1  # control: on by default


def test_cap_and_ids():
    _setup()
    for _ in range(telemetry.MAX_PER_PROCESS + 5):
        telemetry.report_error(_Cfg(), "api", RuntimeError("x"), route="GET /cellcog/chat/6ae700df68d207cfefbe65a6/history")
    assert len(SENT) == telemetry.MAX_PER_PROCESS
    assert SENT[0][1]["route"] == "GET /cellcog/chat/{id}/history"


def test_never_raises():
    _setup()
    telemetry._send = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
    telemetry.report_error(_Cfg(), "api", RuntimeError("x"))  # must not raise
    telemetry.report_error(None, "api", RuntimeError("x"))
    class NoKey(_Cfg):
        api_key = None
    _setup()
    telemetry.report_error(NoKey(), "api", RuntimeError("x"))
    assert SENT == []  # no key, no report


if __name__ == "__main__":
    real_thread = threading.Thread
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    telemetry.threading.Thread = real_thread
    print(f"{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    sys.exit(1 if fails else 0)
