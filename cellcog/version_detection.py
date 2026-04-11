"""
CellCog SDK — Agent Version Auto-Detection.

Best-effort version detection for known agent frameworks.
Fast (no subprocess calls), no external dependencies.
Returns None if version cannot be determined.
"""

import os


def auto_detect_version(agent_provider: str) -> str | None:
    """
    Best-effort version detection for known agent frameworks.

    Called when agent_version is not explicitly provided to CellCogClient.
    Returns None if version cannot be determined — stored as-is in the backend.

    Args:
        agent_provider: The agent name (lowercase, kebab-case) provided by the caller.

    Returns:
        Version string if detected, None otherwise.
    """
    detectors = {
        "openclaw": _detect_openclaw_version,
        "claude-code": _detect_claude_code_version,
        "cursor": _detect_cursor_version,
        "aider": _detect_aider_version,
    }

    detector = detectors.get(agent_provider)
    if detector:
        return detector()
    return None


def _detect_openclaw_version() -> str | None:
    """
    OpenClaw version detection.

    Try: importlib.metadata → OPENCLAW_VERSION env → config file → None
    """
    # 1. Python package version (most reliable)
    try:
        from importlib.metadata import version

        return version("openclaw")
    except Exception:
        pass

    # 2. Env var
    v = os.environ.get("OPENCLAW_VERSION")
    if v:
        return v

    # 3. Config file meta.lastTouchedVersion
    try:
        import json

        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
            return config.get("meta", {}).get("lastTouchedVersion")
    except Exception:
        pass

    return None


def _detect_claude_code_version() -> str | None:
    """
    Claude Code version detection.

    No reliable env var available. Could try `claude --version` but
    subprocess calls are too slow for SDK init. Returns None.
    """
    return None


def _detect_cursor_version() -> str | None:
    """
    Cursor version detection.

    No reliable env var or package metadata available. Returns None.
    """
    return None


def _detect_aider_version() -> str | None:
    """
    Aider version detection.

    Try: AIDER_VERSION env → importlib.metadata → None
    """
    v = os.environ.get("AIDER_VERSION")
    if v:
        return v

    try:
        from importlib.metadata import version

        return version("aider-chat")
    except Exception:
        pass

    return None
