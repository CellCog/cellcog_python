"""
CellCog SDK error reports (SDK 2.8.0).

When the SDK itself fails (an upload, a download, an API call), it sends ONE small report to CellCog
(POST /api/cellcog/sdk-errors) so CellCog can see failures that happen on your machine and fix them.

What a report carries: the step that failed, the HTTP status, the error class, the error message with every URL query
string and file path removed, the host the request went to, the file's type and size, a path CATEGORY (for example
"mac", "windows", "claude_sandbox", never the path itself), your OS and Python version. The SDK version and agent name
ride the request headers the SDK already sends.

What it never carries: file contents, prompts, messages, API keys or file paths.

Reports never block or fail your call: each is sent in the background with a 2 second timeout, every error in the
reporter is swallowed, and a process sends at most 20.

Turn reports off: set CELLCOG_DISABLE_ERROR_REPORTS=1.
"""

import os
import platform
import re
import threading
from typing import Optional
from urllib.parse import urlparse

import requests

ENV_OFF = "CELLCOG_DISABLE_ERROR_REPORTS"
TIMEOUT_S = 2
MAX_PER_PROCESS = 20
THREAD_NAME = "cellcog-error-report"

_sent = 0
_lock = threading.Lock()

_URL_RE = re.compile(r"\b(https?|gs)://([^/\s'\"?#]+)[^\s'\"]*")
_UNIX_PATH_RE = re.compile(r"(?<![\w:<>/.])/[^\s'\"]+")
_WIN_PATH_RE = re.compile(r"(?:[A-Za-z]:|\\\\)[\\/][^\s'\"]+")
_ID_RE = re.compile(r"[0-9a-fA-F]{24}")


def enabled() -> bool:
    return os.environ.get(ENV_OFF, "").strip().lower() not in ("1", "true", "yes", "on")


def path_kind(path) -> str:
    """The category of a local path, never the path."""
    p = str(path or "").strip()
    if not p:
        return "empty"
    if p.startswith(("http://", "https://", "gs://")):
        return "url"
    if p.startswith(("/home/claude", "/mnt/", "/sessions/")) or "/tmp/claude" in p:
        return "claude_sandbox"
    if p.startswith("/home/app/"):
        return "cellcog_container"
    if p.startswith("/Users/"):
        return "mac"
    if re.match(r"^[A-Za-z]:[\\/]", p) or p.startswith("\\\\"):
        return "windows"
    if p.startswith(("~", "/")):
        return "linux"
    return "relative"


def host_of(url) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "")[:80]
    except Exception:  # noqa: BLE001
        return ""


def scrub(text) -> str:
    """URLs keep only scheme and host (a signed URL's query is a credential); file paths become <path>."""
    text = _URL_RE.sub(lambda m: f"{m.group(1)}://{m.group(2)}/<path>", str(text or ""))
    text = _WIN_PATH_RE.sub("<path>", text)
    text = _UNIX_PATH_RE.sub(lambda m: m.group(0) if m.group(0) == "/<path>" else "<path>", text)
    return text.replace("\r", "").replace("\n", " | ")[:400]


def _status_of(exc) -> Optional[int]:
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _send(url: str, headers: dict, report: dict) -> None:
    try:
        requests.post(url, headers=headers, json={"errors": [report]}, timeout=TIMEOUT_S)
    except Exception:  # noqa: BLE001  a report never surfaces as an error
        pass


def report_error(config, step: str, exc: Optional[BaseException] = None, *, status: Optional[int] = None,
                 host: Optional[str] = None, path=None, mime: Optional[str] = None, size=None,
                 route: Optional[str] = None, chat_id: Optional[str] = None, message: Optional[str] = None) -> None:
    """Send one error report in the background. Never raises, never blocks."""
    global _sent
    try:
        if config is None or not enabled() or not getattr(config, "api_key", None):
            return
        with _lock:
            if _sent >= MAX_PER_PROCESS:
                return
            _sent += 1
        if status is None and exc is not None:
            status = _status_of(exc)
        report = {
            "step": str(step)[:30],
            "status": str(status) if status is not None else "",
            "err": type(exc).__name__ if exc is not None else "",
            "msg": scrub(message if message is not None else (str(exc) if exc is not None else "")),
            "host": (host or "")[:80],
            "path_kind": path_kind(path) if path is not None else "",
            "mime": str(mime or "")[:80],
            "size": str(size) if size is not None else "",
            "route": _ID_RE.sub("{id}", str(route or "").split("?", 1)[0])[:120],
            "chat_id": str(chat_id or "") if _ID_RE.fullmatch(str(chat_id or "")) else "",
            "os": f"{platform.system()} {platform.release()}"[:40],
            "py": platform.python_version(),
        }
        url = f"{config.api_base_url}/cellcog/sdk-errors"
        headers = config.get_request_headers()
        threading.Thread(target=_send, args=(url, headers, report), name=THREAD_NAME, daemon=False).start()
    except Exception:  # noqa: BLE001
        pass
