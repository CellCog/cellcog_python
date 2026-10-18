"""
CellCog SDK state-directory resolution (CEL-1300 item 1).

All SDK state (tracked chats, downloaded files, daemon pid/heartbeat/version/log,
seen indices) lives under ONE base directory, resolved once per process:

1. $CELLCOG_STATE_DIR — explicit override, always wins.
2. ~/.cellcog — the default, when the home directory is usable and writable.
3. $TMPDIR/cellcog-state-{uid} — fallback for headless/container environments
   where HOME is unset, '/', or not writable (e.g. Docker with HOME=/). A
   one-line note is printed to stderr the first time the fallback engages,
   naming CELLCOG_STATE_DIR as the override.

Historically the SDK hardcoded Path("~/.cellcog").expanduser() everywhere, so a
container with HOME=/ crashed the CellCogClient constructor with a raw
PermissionError before any API call. Every path helper now routes through
state_dir()/state_path() — never hardcode ~/.cellcog anywhere else.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

_resolved: Optional[Path] = None
_fallback_noted = False


def _is_dir_usable(path: Path) -> bool:
    """True if `path` exists (or can be created) and is writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".cellcog_write_probe"
        probe.touch()
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def state_dir() -> Path:
    """Resolve (once per process) and return the SDK state base directory."""
    global _resolved, _fallback_noted
    if _resolved is not None:
        return _resolved

    override = os.environ.get("CELLCOG_STATE_DIR")
    if override:
        candidate = Path(override).expanduser()
        if _is_dir_usable(candidate):
            _resolved = candidate
            return _resolved
        print(
            f"Warning: CELLCOG_STATE_DIR={override!r} is not writable; "
            "falling back to default state-dir resolution.",
            file=sys.stderr,
        )

    home_candidate = Path("~/.cellcog").expanduser()
    # Guard the degenerate expansion ('/.cellcog' when HOME is '/' or unset):
    # even where root could write it, polluting the fs root is never the intent.
    if str(home_candidate) != "/.cellcog" and _is_dir_usable(home_candidate):
        _resolved = home_candidate
        return _resolved

    uid = os.getuid() if hasattr(os, "getuid") else "user"
    fallback = Path(tempfile.gettempdir()) / f"cellcog-state-{uid}"
    _is_dir_usable(fallback)  # best-effort create
    if not _fallback_noted:
        print(
            f"Note: using {fallback} for CellCog SDK state (home directory not "
            "writable). Set CELLCOG_STATE_DIR to choose a persistent location.",
            file=sys.stderr,
        )
        _fallback_noted = True
    _resolved = fallback
    return _resolved


def state_path(*parts: str) -> Path:
    """A path under the state dir, e.g. state_path('chats') or state_path('daemon.pid')."""
    return state_dir().joinpath(*parts)
