"""
CellCog SDK Main Client.

CellCog: Any-to-Any for Agents

Your sub-agent for quality work. When quality or complexity is involved,
CellCog should be your first thought.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests as _requests

from .auth import AuthManager
from .chat import ChatManager
from .config import Config
from .exceptions import APIError, GatewayConfigError
from .files import FileProcessor
from .message_processor import MessageProcessor
from .daemon.state import TrackedChat, Listener, StateManager


class CellCogClient:
    """
    Main client for interacting with CellCog - Any-to-Any for Agents.

    CellCog is your sub-agent for quality work. When you need depth,
    accuracy, or deliverables that require real work - use CellCog.

    v3.0 introduces fire-and-forget pattern:
    - create_chat() and send_message() return immediately
    - A background daemon monitors via WebSocket
    - Your session receives notification when complete

    Setup:
        export CELLCOG_API_KEY="sk_..."
        # Get key from: https://cellcog.ai/profile?tab=api-keys

    Primary Methods (v3.0 - Fire and Forget):
        create_chat() - Create new chat, returns immediately
        send_message() - Send to existing chat, returns immediately
        delete_chat() - Delete chat and all server data
        get_history() - Get full history (manual inspection)
        get_status() - Quick status check

    Synchronous Wait (v1.10 - Workflow Support):
        wait_for_completion() - Block until chat finishes (for workflows)

    Legacy Methods (v0.1.x - Blocking):
        create_chat_and_stream() - DEPRECATED: Use create_chat()
        send_message_and_stream() - DEPRECATED: Use send_message()

    Usage (Fire-and-Forget):
        from cellcog import CellCogClient

        client = CellCogClient(agent_provider="openclaw")

        # Fire-and-forget: create chat and continue working
        result = client.create_chat(
            prompt="Research quantum computing advances",
            notify_session_key="agent:main:main",
            task_label="quantum-research"
        )
        
        # result includes chat_id, status, and next_steps guidance
        # Your session receives notification when complete

    Usage (Synchronous Workflow):
        # Create chat, then wait for completion
        result = client.create_chat(
            prompt="Research quantum computing advances",
            notify_session_key="agent:main:main",
            task_label="quantum-research"
        )
        completion = client.wait_for_completion(result["chat_id"])
        # Daemon delivers results to your session; proceed with workflow
    """

    def __init__(
        self,
        agent_provider: str,
        agent_version: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        """
        Initialize CellCog client.

        Args:
            agent_provider: Required. Identifies which agent framework is calling CellCog.
                This is the framework/provider name, not your individual agent's name.
                Examples: "openclaw", "claude-code", "cursor", "hermes",
                "perplexity", "aider", "script", "my-custom-framework".
                Must be lowercase alphanumeric + hyphens, 1-50 characters.
            agent_version: Optional. Version of the agent framework. If not provided,
                SDK attempts best-effort auto-detection for known frameworks.
                Stored as None if undetectable.
            config_path: Path to config file. Defaults to ~/.openclaw/cellcog.json
        """
        if not agent_provider or not isinstance(agent_provider, str):
            raise ValueError(
                "agent_provider is required. Identifies which agent framework is calling CellCog.\n"
                "Examples: 'openclaw', 'claude-code', 'cursor', 'script', 'my-custom-framework'"
            )

        import re

        normalized_provider = agent_provider.lower().strip().replace("_", "-")
        if not re.match(r"^[a-z0-9][a-z0-9\-]{0,49}$", normalized_provider):
            raise ValueError(
                f"Invalid agent_provider '{agent_provider}'. Use lowercase letters, numbers, and hyphens. "
                "1-50 characters. Examples: 'openclaw', 'claude-code', 'my-framework'"
            )

        self.config = Config(config_path)

        # Agent identity: use provided version or auto-detect
        if agent_version is not None:
            resolved_version = agent_version.strip() or None
        else:
            from .version_detection import auto_detect_version

            resolved_version = auto_detect_version(normalized_provider)

        self.config.set_agent_identity(normalized_provider, resolved_version)

        self._auth = AuthManager(self.config)
        self._files = FileProcessor(self.config)
        self._chat = ChatManager(self.config, self._files)
        self._message_processor = MessageProcessor(self.config, self._files)
        self._state = StateManager()
        
        # Daemon management
        self._daemon_pid_file = Path("~/.cellcog/daemon.pid").expanduser()

        # Sessions send pre-flight check cache
        # Maps gateway_url -> (is_available: bool, checked_at: float)
        self._sessions_send_cache: dict[str, tuple[bool, float]] = {}
        self._sessions_send_cache_ttl = 60.0  # seconds

        # Guard against re-entrant daemon checks (prevents RecursionError
        # when _is_daemon_alive triggers _kill_daemon during concurrent calls)
        self._daemon_check_in_progress = False

    # ==================== Configuration ====================

    def get_account_status(self) -> dict:
        """
        Check if SDK is configured with valid API key.

        Returns:
            {"configured": bool, "email": str | None, "api_key_prefix": str | None}
        """
        return self._auth.get_status()

    # ==================== v3.0 Primary Methods (Fire and Forget) ====================

    # ==================== Co-work (Human Computer) ====================

    def get_desktop_status(self) -> dict:
        """
        Check if the user's CellCog Desktop app is connected.

        Use before creating co-work-enabled chats to verify the desktop
        app is running and authenticated on the user's machine.

        Returns:
            {
                "connected": bool,
                "system_info": {
                    "os": str,           # "darwin", "win32", "linux"
                    "hostname": str,
                    "shell": str,
                    "app_version": str,
                    "available_tools": ["python3", "git", ...],
                } | None,
                "settings": {...} | None,
                "setup_instructions": str  # Only if not connected
            }
        """
        self.config.require_configured()
        result = self._chat._request("GET", "/cellcog/human-computer/status")

        if not result.get("connected"):
            base = self.config.api_base_url.rstrip("/")
            result["setup_instructions"] = (
                "CellCog Desktop app is not connected.\n\n"
                "To set up (agent can do this programmatically):\n"
                f"1. Download from: {base}/cellcog/human-computer/download/mac "
                f"(or /win, /linux)\n"
                "2. Install the app on the user's machine\n"
                "3. Run: cellcog-desktop --set-api-key <CELLCOG_API_KEY>\n"
                "4. Run: cellcog-desktop --start\n"
                "5. Verify: cellcog-desktop --status\n\n"
                "If the user prefers manual setup:\n"
                "1. Download CellCog Desktop from cellcog.ai/cowork\n"
                "2. Open the app and enter API key\n"
            )
        return result

    def get_desktop_download_urls(self) -> dict:
        """
        Get download URLs and platform-specific install instructions for the
        CellCog Desktop app.

        Returns a dict with per-platform download URL and shell commands to
        install the app. After installation, use the ``post_install`` commands
        to configure and start the app.

        Returns:
            {
                "mac": {"url": str, "install_commands": [str, ...]},
                "windows": {"url": str, "install_commands": [str, ...]},
                "linux": {"url": str, "install_commands": [str, ...]},
                "post_install": str  # Commands to run after install (all platforms)
            }
        """
        base = self.config.api_base_url.rstrip("/")
        mac_url = f"{base}/cellcog/human-computer/download/mac"
        win_url = f"{base}/cellcog/human-computer/download/win"
        linux_url = f"{base}/cellcog/human-computer/download/linux"

        return {
            "mac": {
                "url": mac_url,
                "install_commands": [
                    f'curl -L -o /tmp/CellCogDesktop.dmg "{mac_url}"',
                    'hdiutil attach /tmp/CellCogDesktop.dmg -nobrowse -quiet',
                    'cp -r "/Volumes/CellCog Desktop/CellCog Desktop.app" /Applications/',
                    'hdiutil detach "/Volumes/CellCog Desktop" -quiet',
                    'rm -f /tmp/CellCogDesktop.dmg',
                ],
            },
            "windows": {
                "url": win_url,
                "install_commands": [
                    f'curl -L -o %TEMP%\\CellCogDesktop.exe "{win_url}"',
                    '%TEMP%\\CellCogDesktop.exe /S',
                ],
            },
            "linux": {
                "url": linux_url,
                "install_commands": [
                    f'curl -L -o ~/CellCogDesktop.AppImage "{linux_url}"',
                    'chmod +x ~/CellCogDesktop.AppImage',
                    'mkdir -p ~/.local/bin',
                    'mv ~/CellCogDesktop.AppImage ~/.local/bin/cellcog-desktop-app',
                ],
            },
            "post_install": (
                "cellcog-desktop --set-api-key <CELLCOG_API_KEY>\n"
                "cellcog-desktop --start\n"
                "sleep 5\n"
                "cellcog-desktop --status"
            ),
        }

    # ==================== v3.0 Primary Methods (Fire and Forget) ====================

    def create_chat(
        self,
        prompt: str,
        notify_session_key: Optional[str] = None,
        task_label: str = "",
        delivery: str = "wait_for_completion",
        timeout: int = 1800,
        gateway_url: Optional[str] = None,
        project_id: Optional[str] = None,
        agent_role_id: Optional[str] = None,
        chat_mode: str = "agent",
        enable_cowork: bool = False,
        cowork_working_directory: Optional[str] = None,
    ) -> dict:
        """
        Create a CellCog chat.

        Two delivery modes:
        - "wait_for_completion" (default): Blocks until done. Returns full results.
          Works with ANY agent (OpenClaw, Cursor, Claude Code, etc.).
        - "notify_on_completion": Returns immediately. Daemon delivers results
          to your OpenClaw session via sessions_send. Requires notify_session_key.

        Args:
            prompt: Task description (supports SHOW_FILE tags for file uploads)
            notify_session_key: OpenClaw session key (required for notify_on_completion,
                e.g., "agent:main:main"). If provided without explicit delivery param,
                automatically uses notify_on_completion for backward compatibility.
            task_label: Human-readable label (appears in notification)
            delivery: "wait_for_completion" (default, universal) or
                "notify_on_completion" (OpenClaw only, fire-and-forget)
            timeout: Max seconds to wait (wait_for_completion mode only, default 1800)
            gateway_url: OpenClaw Gateway URL (notify_on_completion only)
            project_id: Optional CellCog project ID for document context
            agent_role_id: Optional agent role ID within the project
            chat_mode: "agent", "agent core", "agent team", or "agent team max"
            enable_cowork: Enable co-work on user's PC
            cowork_working_directory: Working directory for co-work commands

        Returns:
            All modes return: {"chat_id": str, "is_operating": bool, "status": str, "message": str}

            The "message" field contains the full response, file paths, credits info,
            and next steps — formatted as a structured string. Files referenced via
            SHOW_FILE tags are auto-downloaded to ~/.cellcog/chats/{chat_id}/.

        Examples:
            # Universal (works with any agent)
            result = client.create_chat(
                prompt="Research quantum computing advances",
                task_label="research",
            )
            # Blocks until done, returns full results

            # OpenClaw fire-and-forget
            result = client.create_chat(
                prompt="Research quantum computing advances",
                notify_session_key="agent:main:main",
                task_label="research",
            )
            # Returns immediately, daemon delivers later

            # Explicit delivery mode
            result = client.create_chat(
                prompt="Research quantum computing advances",
                task_label="research",
                delivery="notify_on_completion",
                notify_session_key="agent:main:main",
            )
        """
        self.config.require_configured()

        # ── Resolve delivery mode ──
        # Backward compat: if notify_session_key provided, infer notify mode
        if notify_session_key and delivery == "wait_for_completion":
            delivery = "notify_on_completion"

        if delivery not in ("notify_on_completion", "wait_for_completion"):
            raise ValueError(
                f"Invalid delivery mode: '{delivery}'. "
                "Use 'notify_on_completion' (OpenClaw) or 'wait_for_completion' (universal)."
            )

        if delivery == "notify_on_completion" and not notify_session_key:
            raise ValueError(
                "notify_on_completion requires notify_session_key. "
                "Example: notify_session_key='agent:main:main'\n"
                "Or use delivery='wait_for_completion' (default) which works with any agent."
            )

        # ── Resolve gateway URL (needed for notify mode) ──
        gateway_url = gateway_url or os.environ.get(
            "OPENCLAW_GATEWAY_URL",
            "http://127.0.0.1:18789"
        )

        # ── Pre-flight check (notify mode only) ──
        if delivery == "notify_on_completion":
            self._require_sessions_send(gateway_url)

        # ── Create the chat via API ──
        api_result = self._chat.create(
            prompt, project_id, chat_mode,
            agent_role_id=agent_role_id,
            hc_enabled=enable_cowork,
            hc_working_directory=cowork_working_directory,
        )
        chat_id = api_result["chat_id"]
        task_label = task_label or f"chat-{chat_id[:8]}"

        # ── Local setup: tracking + daemon + delivery ──
        # Wrapped in try-except so chat_id is always returned even if local
        # setup fails. The chat was already created server-side and billed —
        # losing the chat_id would mean the agent can't recover it.
        try:
            tracking_info = self._track_chat(
                chat_id=chat_id,
                delivery_mode=delivery,
                session_key=notify_session_key,
                gateway_url=gateway_url if delivery == "notify_on_completion" else None,
                task_label=task_label,
            )
            self._ensure_daemon_running()

            # ── Delivery-mode-specific behavior ──
            if delivery == "notify_on_completion":
                message = self._build_tracking_message(
                    chat_id=chat_id,
                    task_label=task_label,
                    action="created",
                    notify_session_key=notify_session_key,
                    daemon_listening=self._is_daemon_alive(),
                    listeners=tracking_info["listeners"],
                )
                return {
                    "chat_id": chat_id,
                    "is_operating": True,
                    "status": "tracking",
                    "message": message,
                }

            # ── wait_for_completion: block until done ──
            return self._wait_and_return_results(chat_id, timeout, api_result.get("uploaded_files"))

        except Exception as e:
            # Local setup failed but chat exists server-side.
            # Return chat_id so the agent can recover via get_history().
            return {
                "chat_id": chat_id,
                "is_operating": True,
                "status": "tracking",
                "message": (
                    f"⚠️ Chat created (ID: {chat_id}) but local daemon setup encountered an error: {e}\n\n"
                    f"The chat is running on CellCog and will complete normally.\n"
                    f"To get results:\n"
                    f'  result = client.get_history("{chat_id}")\n'
                    f'  print(result["message"])\n\n'
                    f"Or wait and retry:\n"
                    f'  result = client.wait_for_completion("{chat_id}")'
                ),
            }

    def send_message(
        self,
        chat_id: str,
        message: str,
        notify_session_key: Optional[str] = None,
        task_label: Optional[str] = None,
        delivery: str = "wait_for_completion",
        timeout: int = 1800,
        gateway_url: Optional[str] = None,
    ) -> dict:
        """
        Send a message to existing chat.

        Same delivery modes as create_chat:
        - "wait_for_completion" (default): Blocks until done. Returns full results.
        - "notify_on_completion": Returns immediately. Daemon delivers later.

        Args:
            chat_id: Chat to send to
            message: Your message (supports SHOW_FILE tags for file uploads)
            notify_session_key: OpenClaw session key (required for notify_on_completion)
            task_label: Label for notification (default: "continue-{chat_id[:8]}")
            delivery: "wait_for_completion" or "notify_on_completion"
            timeout: Max seconds to wait (wait_for_completion only, default 1800)
            gateway_url: OpenClaw Gateway URL (notify_on_completion only)

        Returns:
            Same as create_chat for the respective delivery mode.
        """
        self.config.require_configured()

        # ── Resolve delivery mode ──
        if notify_session_key and delivery == "wait_for_completion":
            delivery = "notify_on_completion"

        if delivery not in ("notify_on_completion", "wait_for_completion"):
            raise ValueError(
                f"Invalid delivery mode: '{delivery}'. "
                "Use 'notify_on_completion' (OpenClaw) or 'wait_for_completion' (universal)."
            )

        if delivery == "notify_on_completion" and not notify_session_key:
            raise ValueError(
                "notify_on_completion requires notify_session_key. "
                "Example: notify_session_key='agent:main:main'\n"
                "Or use delivery='wait_for_completion' (default) which works with any agent."
            )

        gateway_url = gateway_url or os.environ.get(
            "OPENCLAW_GATEWAY_URL",
            "http://127.0.0.1:18789"
        )
        task_label = task_label or f"continue-{chat_id[:8]}"

        # ── Pre-flight check (notify mode only) ──
        if delivery == "notify_on_completion":
            self._require_sessions_send(gateway_url)

        # ── Send message via API ──
        api_result = self._chat.send_message(chat_id, message)

        # ── Local setup (same protection as create_chat) ──
        try:
            tracking_info = self._track_chat(
                chat_id=chat_id,
                delivery_mode=delivery,
                session_key=notify_session_key,
                gateway_url=gateway_url if delivery == "notify_on_completion" else None,
                task_label=task_label,
            )
            self._ensure_daemon_running()

            if delivery == "notify_on_completion":
                message = self._build_tracking_message(
                    chat_id=chat_id,
                    task_label=task_label,
                    action="sent",
                    notify_session_key=notify_session_key,
                    daemon_listening=self._is_daemon_alive(),
                    listeners=tracking_info["listeners"],
                )
                return {
                    "chat_id": chat_id,
                    "is_operating": True,
                    "status": "tracking",
                    "message": message,
                }

            return self._wait_and_return_results(chat_id, timeout, api_result.get("uploaded_files"))

        except Exception as e:
            return {
                "chat_id": chat_id,
                "is_operating": True,
                "status": "tracking",
                "message": (
                    f"⚠️ Message sent to chat {chat_id} but local daemon setup encountered an error: {e}\n\n"
                    f"The message was delivered to CellCog and is being processed.\n"
                    f"To get results:\n"
                    f'  result = client.get_history("{chat_id}")\n'
                    f'  print(result["message"])\n\n'
                    f"Or wait and retry:\n"
                    f'  result = client.wait_for_completion("{chat_id}")'
                ),
            }

    def get_history(
        self,
        chat_id: str,
        download_files: bool = True
    ) -> dict:
        """
        Get full chat history. Returns same unified shape as all other methods.

        Use for manual inspection, memory recovery, or when the original
        delivery was missed/truncated.

        Args:
            chat_id: Chat to retrieve
            download_files: Whether to download files (default True)

        Returns:
            {"chat_id", "is_operating", "status", "message"}
            message contains ALL messages (full history, not just unseen).
        """
        self.config.require_configured()

        status = self.get_status(chat_id)
        history = self._chat._request("GET", f"/cellcog/chat/{chat_id}/history")

        result = self._message_processor.process_full_history(
            chat_id=chat_id,
            history=history,
            is_operating=status["is_operating"],
            download_files=download_files,
        )

        # Fetch credits
        credits_info = None
        try:
            credits_info = self._chat._request("GET", f"/cellcog/chat/{chat_id}/credits")
        except Exception:
            pass

        if status["is_operating"]:
            # Chat still running — show partial history
            message = self._build_operating_history_message(
                chat_id=chat_id,
                formatted_output=result.formatted_output,
                delivered_count=result.delivered_count,
            )
            return {
                "chat_id": chat_id,
                "is_operating": True,
                "status": "operating",
                "message": message,
            }

        # Chat completed — agent is consuming results

        # Mark seen server-side (prevents unseen email reminder from firing)
        try:
            self._chat._request("PATCH", f"/cellcog/chat/{chat_id}/seen")
        except Exception:
            pass

        # Remove tracked chat file (daemon doesn't need to monitor anymore)
        self._state.remove_tracked(chat_id)

        chat_credits = credits_info.get("total_credits") if credits_info else None
        wallet_balance = credits_info.get("effective_balance") if credits_info else None

        message = self._build_completion_message(
            chat_id=chat_id,
            formatted_output=result.formatted_output,
            delivered_count=result.delivered_count,
            downloaded_files=result.downloaded_files,
            chat_credits=chat_credits,
            wallet_balance=wallet_balance,
        )

        return {
            "chat_id": chat_id,
            "is_operating": False,
            "status": "completed",
            "message": message,
        }

    def get_status(self, chat_id: str) -> dict:
        """
        Get current status of a chat.

        Returns:
            {
                "status": "processing" | "ready" | "error",
                "name": str,
                "is_operating": bool,
                "error_type": str | None
            }
        """
        return self._chat.get_status(chat_id)

    # ==================== Chat Tracking Recovery ====================

    def restart_chat_tracking(self) -> dict:
        """
        Restart the background daemon for chat tracking.
        
        Call after fixing daemon errors:
        - SDK upgrade: clawhub update cellcog + pip install → restart_chat_tracking()
        - API key change: update CELLCOG_API_KEY env var → restart_chat_tracking()
        - Credits added: restart_chat_tracking()
        
        The daemon reconciles state on startup:
        - Chats still running → resume tracking
        - Chats completed while daemon was down → deliver results immediately
        
        Returns:
            {
                "status": "restarted" | "no_tracked_chats" | "failed",
                "tracked_chats": int,
                "message": str
            }
        
        Example:
            # After upgrading SDK:
            # clawhub update cellcog
            # pip install cellcog==1.0.3
            result = client.restart_chat_tracking()
            print(result["message"])
        """
        self.config.require_configured()
        
        # Kill existing daemon
        self._kill_daemon_if_running()
        
        # Count tracking files to report
        tracked_dir = Path("~/.cellcog/tracked_chats").expanduser()
        tracked_count = sum(1 for _ in tracked_dir.glob("*.json")) if tracked_dir.exists() else 0
        
        if tracked_count == 0:
            return {
                "status": "no_tracked_chats",
                "tracked_chats": 0,
                "message": "No chats to track. Daemon will start on next create_chat()."
            }
        
        # Start fresh daemon
        started = self._start_daemon()
        
        from . import __version__
        if started:
            return {
                "status": "restarted",
                "tracked_chats": tracked_count,
                "message": (
                    f"Daemon restarted with SDK v{__version__}. "
                    f"Reconciling {tracked_count} tracked chat(s). "
                    f"Results will be delivered automatically."
                )
            }
        else:
            return {
                "status": "failed",
                "tracked_chats": tracked_count,
                "message": "Failed to start daemon. Check ~/.cellcog/daemon.log"
            }

    # ==================== Synchronous Wait ====================

    def wait_for_completion(self, chat_id: str, timeout: int = 1800) -> dict:
        """
        Block until a CellCog chat finishes, then return full results.

        Returns the SAME content that notify_on_completion would deliver
        via sessions_send — formatted output, downloaded files, credits info.

        Use after create_chat/send_message, or to resume waiting after timeout.

        Args:
            chat_id: Chat to wait on
            timeout: Max seconds to wait (default 1800). Use 3600 for complex jobs.

        Returns:
            {"chat_id": str, "is_operating": bool, "status": str, "message": str}

            On completion: status="completed", message contains full response with
            file paths, credits used, and next steps.
            On timeout: status="timeout", message contains progress updates and
            retry guidance.

        Examples:
            # Universal pattern (recommended)
            result = client.create_chat(
                prompt="Research quantum computing",
                task_label="research",
            )
            # result already contains full results (create_chat blocks)

            # Resume after timeout
            result = client.wait_for_completion("chat_id", timeout=1800)

            # Compose with notify mode
            r = client.create_chat(prompt="...", notify_session_key="agent:main:main", ...)
            completion = client.wait_for_completion(r["chat_id"])
        """
        return self._wait_and_return_results(chat_id, timeout)

    def _wait_and_return_results(
        self,
        chat_id: str,
        timeout: int = 1800,
        uploaded_files: Optional[list] = None,
    ) -> dict:
        """
        Core wait loop: poll until completion, then fetch and return full results.

        Used by create_chat(delivery="wait_for_completion"), send_message(...),
        and the standalone wait_for_completion() method.

        Detection strategy:
        1. Primary: daemon removes tracking file on CHAT_COMPLETED (fast, ~1s)
        2. Fallback: poll CellCog API every 30s (handles daemon not running)

        On completion: fetches history, downloads files, marks chat seen.
        On timeout: reads interim updates from daemon, returns progress.
        """
        self.config.require_configured()

        tracking_file = self._state.get_tracked_file_path(chat_id)
        start_time = time.time()
        last_api_check = 0
        api_poll_interval = 30  # seconds

        # If tracking file doesn't exist, check if already completed
        if not tracking_file.exists():
            try:
                status = self.get_status(chat_id)
                if not status["is_operating"]:
                    return self._fetch_and_format_results(chat_id, uploaded_files)
            except Exception:
                pass

        # ── Poll loop ──
        while time.time() - start_time < timeout:
            # Primary: daemon removed tracking file → completion
            if not tracking_file.exists():
                return self._fetch_and_format_results(chat_id, uploaded_files)

            # Fallback: periodic API check (handles daemon crash/not started)
            now = time.time()
            if now - last_api_check >= api_poll_interval:
                last_api_check = now
                try:
                    status = self.get_status(chat_id)
                    if not status["is_operating"]:
                        return self._fetch_and_format_results(chat_id, uploaded_files)
                except Exception:
                    pass

            remaining = timeout - (time.time() - start_time)
            time.sleep(min(2, max(0, remaining)))

        # ── Timeout: return progress ──
        return self._build_timeout_result(chat_id, timeout)

    def _fetch_and_format_results(
        self,
        chat_id: str,
        uploaded_files: Optional[list] = None,
    ) -> dict:
        """
        Fetch full history, process messages, download files, and return results.

        Returns a dict with a 'message' field containing the EXACT same
        structured string that notify_on_completion would deliver via
        sessions_send. Agents just need to read result["message"].
        """
        try:
            # Fetch history from CellCog API
            history = self._chat._request("GET", f"/cellcog/chat/{chat_id}/history")

            # Process full history (downloads files, formats messages)
            result = self._message_processor.process_full_history(
                chat_id=chat_id,
                history=history,
                is_operating=False,
                download_files=True,
            )

            # Fetch credits
            credits_info = None
            try:
                credits_info = self._chat._request("GET", f"/cellcog/chat/{chat_id}/credits")
            except Exception:
                pass

            # Mark chat as seen
            try:
                self._chat._request("PATCH", f"/cellcog/chat/{chat_id}/seen")
            except Exception:
                pass

            # Remove tracking file (if daemon hasn't already)
            self._state.remove_tracked(chat_id)

            # Build the SAME structured message that notify mode delivers
            chat_credits = credits_info.get("total_credits") if credits_info else None
            wallet_balance = credits_info.get("effective_balance") if credits_info else None

            message = self._build_completion_message(
                chat_id=chat_id,
                formatted_output=result.formatted_output,
                delivered_count=result.delivered_count,
                downloaded_files=result.downloaded_files,
                chat_credits=chat_credits,
                wallet_balance=wallet_balance,
            )

            return {
                "chat_id": chat_id,
                "is_operating": False,
                "status": "completed",
                "message": message,
            }

        except Exception as e:
            return {
                "chat_id": chat_id,
                "is_operating": False,
                "status": "completed",
                "message": (
                    f"✅ CellCog chat completed but result processing failed: {e}\n\n"
                    f"Use client.get_history('{chat_id}') to retrieve results manually."
                ),
            }

    def _build_completion_message(
        self,
        chat_id: str,
        formatted_output: str,
        delivered_count: int,
        downloaded_files: list,
        chat_credits: int | None = None,
        wallet_balance: int | None = None,
    ) -> str:
        """
        Build the structured completion message — same format as daemon's
        _build_notification() so agents get identical output regardless
        of delivery mode.
        """
        parts = []

        parts.append(f'✅ CellCog has completed chat "{chat_id}"')
        parts.append("")
        parts.append(
            "CellCog stops operating on a chat for one of three reasons:\n"
            "  1. Task completed — the work you requested is done\n"
            "  2. Clarifying questions — CellCog needs more information to proceed\n"
            "  3. Roadblock — something prevented completion (e.g., insufficient credits)\n"
            "\n"
            "Read the response below to determine which case applies.\n"
            "If CellCog needs input, send a follow-up message to continue.\n"
            "If the task is complete, no action needed."
        )

        # ── Response ──
        parts.append("")
        parts.append("── Response ──────────────────────────────────")
        parts.append("")
        parts.append(formatted_output)

        # ── Chat Details ──
        parts.append("── Chat Details ──────────────────────────────")
        parts.append("")
        parts.append(f"Chat ID: {chat_id}")
        if chat_credits is not None:
            parts.append(f"Credits used: {abs(chat_credits)} credits")
        parts.append(f"Messages delivered: {delivered_count}")
        if downloaded_files:
            files_list = "\n".join(f"  - {f}" for f in downloaded_files)
            parts.append(f"Files downloaded:\n{files_list}")

        # ── Account ──
        if wallet_balance is not None:
            parts.append("")
            parts.append("── Account ───────────────────────────────────")
            parts.append("")
            parts.append(f"Wallet balance: {wallet_balance:,} credits")

        # ── Next Steps ──
        parts.append("")
        parts.append("── Next Steps ────────────────────────────────")
        parts.append("")
        parts.append(
            f'To continue: client.send_message(chat_id="{chat_id}", message="...")'
        )
        parts.append(
            f'To give feedback: client.create_ticket(type="feedback", title="...", chat_id="{chat_id}")'
        )

        return "\n".join(parts)

    def _build_tracking_message(
        self,
        chat_id: str,
        task_label: str,
        action: str,
        notify_session_key: str,
        daemon_listening: bool,
        listeners: int,
    ) -> str:
        """Build message for notify_on_completion mode (tracking started)."""
        action_text = "created" if action == "created" else f"Message sent to chat"
        header = (
            f'✅ Chat "{task_label}" {action_text} (ID: {chat_id})'
            if action == "created"
            else f'✅ Message sent to chat "{chat_id}"'
        )

        parts = [header]
        parts.append("")
        parts.append(
            f"Your response will be delivered to your OpenClaw session "
            f"({notify_session_key}) when CellCog finishes processing."
        )

        parts.append("")
        parts.append("── Tracking Status ───────────────────────────")
        parts.append("")
        parts.append(f"Daemon: {'listening via WebSocket' if daemon_listening else 'starting...'}")
        parts.append(f"Listeners: {listeners} session(s) registered")
        parts.append(f"Delivery: notify_on_completion → {notify_session_key}")

        parts.append("")
        parts.append(
            "You can continue with other work — do not poll.\n"
            "CellCog will deliver the full response with any generated files automatically."
        )

        parts.append("")
        parts.append("── Manual Check ──────────────────────────────")
        parts.append("")
        parts.append(f'Check progress: client.get_status("{chat_id}")')
        parts.append(f'Get full history: client.get_history("{chat_id}")')

        return "\n".join(parts)

    def _build_operating_history_message(
        self,
        chat_id: str,
        formatted_output: str,
        delivered_count: int,
    ) -> str:
        """Build message for get_history() on a chat that's still operating."""
        parts = []

        parts.append(f'⏳ CellCog is still working on chat "{chat_id}"')
        parts.append("")
        parts.append(
            "The history below shows all messages so far. "
            "CellCog has not finished processing."
        )

        parts.append("")
        parts.append("── History So Far ────────────────────────────")
        parts.append("")
        parts.append(formatted_output)

        parts.append("── Chat Details ──────────────────────────────")
        parts.append("")
        parts.append(f"Chat ID: {chat_id}")
        parts.append(f"Messages so far: {delivered_count}")

        parts.append("")
        parts.append("── Next Steps ────────────────────────────────")
        parts.append("")
        parts.append(f'To wait for completion: client.wait_for_completion("{chat_id}")')
        parts.append(f'To send follow-up: client.send_message(chat_id="{chat_id}", message="...")')

        return "\n".join(parts)

    def _build_timeout_result(self, chat_id: str, timeout: int) -> dict:
        """Build timeout response with progress from daemon's interim updates."""
        progress = []

        # Read interim updates file written by daemon
        try:
            updates_file = Path("~/.cellcog/chats").expanduser() / chat_id / ".interim_updates.json"
            if updates_file.exists():
                raw = json.loads(updates_file.read_text())
                now = time.time()
                # Take last 10, newest first
                for update in reversed(raw[-10:]):
                    elapsed = now - update["timestamp"]
                    if elapsed < 60:
                        time_str = "just now"
                    elif elapsed < 3600:
                        time_str = f"{int(elapsed / 60)}m ago"
                    else:
                        time_str = f"{int(elapsed / 3600)}h ago"
                    progress.append({"text": update["text"], "timestamp": time_str})
        except Exception:
            pass

        # Build guidance message
        lines = [f"Timeout reached ({timeout}s). CellCog is still working on this task."]

        if progress:
            lines.append("")
            lines.append("Recent progress (newest first):")
            for p in progress:
                lines.append(f"  • [{p['timestamp']}] {p['text']}")

        lines.extend([
            "",
            "If the progress above looks like the task is heading in the right direction,",
            "you can continue waiting:",
            f"  client.wait_for_completion(\"{chat_id}\", timeout=1800)",
            "",
            "If the task appears stuck (no recent activity or repeated updates),",
            "consider creating a new chat with a refined prompt.",
            "",
            f"Chat ID: {chat_id}",
        ])

        return {
            "chat_id": chat_id,
            "is_operating": True,
            "status": "timeout",
            "message": "\n".join(lines),
        }

    # ==================== Tickets ====================

    def create_ticket(
        self,
        type: str,
        title: str,
        description: str,
        chat_id: str | None = None,
        tags: list[str] | None = None,
        priority: str = "medium",
    ) -> dict:
        """
        Submit feedback, bug report, support request, or feature request to CellCog.

        Use after completing a task to share what went well, what didn't,
        or what capabilities would be useful.

        Args:
            type: "support", "feedback", "feature_request", or "bug_report"
            title: Short summary (max 200 chars)
            description: Detailed description (max 5000 chars)
            chat_id: Optional chat ID for context
            tags: Optional tags for categorization (max 10)
            priority: "low", "medium", "high", or "critical" (default: "medium")

        Returns:
            {
                "ticket_id": str,
                "ticket_number": int,
                "status": "open",
                "message": str
            }

        Example:
            client.create_ticket(
                type="feedback",
                title="Image generation quality is excellent",
                description="Generated 15 product images, all matched style accurately.",
                chat_id="abc123",
                tags=["image_generation", "positive"]
            )
        """
        self.config.require_configured()

        data = {
            "type": type,
            "title": title,
            "description": description,
            "priority": priority,
        }
        if chat_id:
            data["chat_id"] = chat_id
        if tags:
            data["tags"] = tags

        return self._chat._request("POST", "/cellcog/tickets", data)

    # ==================== Projects ====================

    def list_projects(self) -> dict:
        """
        List all projects accessible to the current user.

        Returns:
            {"projects": [{"id", "name", "is_admin", "context_tree_id", "files_count", "created_at", ...}]}
        """
        self.config.require_configured()
        return self._chat._request("GET", "/cellcog/projects")

    def create_project(self, name: str, instructions: str = "") -> dict:
        """
        Create a new CellCog project.

        A project is a knowledge workspace with its own document collection
        (context tree) and optional AI agent instructions.

        Args:
            name: Project name (max 200 chars)
            instructions: Optional instructions for AI agents working in this project (max 5000 chars)

        Returns:
            {"id": str, "name": str, "context_tree_id": str, "created_at": str, ...}

        Note:
            The creator is automatically an admin. Use cellcog.ai to manage
            members and agent roles.
        """
        self.config.require_configured()
        data = {"name": name}
        if instructions:
            data["project_instructions"] = instructions
        return self._chat._request("POST", "/cellcog/projects", data)

    def get_project(self, project_id: str) -> dict:
        """
        Get project details including context_tree_id.

        Args:
            project_id: Project ID

        Returns:
            {"id", "name", "project_instructions", "context_tree_id", "is_admin", "created_at", ...}

        The context_tree_id is needed for document operations and context tree retrieval.
        """
        self.config.require_configured()
        return self._chat._request("GET", f"/cellcog/projects/{project_id}")

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
    ) -> dict:
        """
        Update project name and/or instructions (admin only).

        Args:
            project_id: Project ID
            name: New name (optional)
            instructions: New instructions (optional)

        Returns:
            {"message": "Project updated successfully"}
        """
        self.config.require_configured()
        data = {}
        if name is not None:
            data["name"] = name
        if instructions is not None:
            data["project_instructions"] = instructions
        return self._chat._request("PUT", f"/cellcog/projects/{project_id}", data)

    def delete_project(self, project_id: str) -> dict:
        """
        Delete a project (admin only). Soft delete — can be recovered by CellCog support.

        Args:
            project_id: Project ID

        Returns:
            {"message": "Project deleted successfully"}
        """
        self.config.require_configured()
        return self._chat._request("DELETE", f"/cellcog/projects/{project_id}")

    # ==================== Agent Roles (Read-Only) ====================

    def list_agent_roles(self, project_id: str) -> list:
        """
        List all active agent roles in a project (read-only).

        Use this to discover available agent_role_id values for create_chat().
        Agent role creation/editing is done by humans at cellcog.ai.

        Args:
            project_id: Project ID

        Returns:
            [{"id", "title", "role_description", "context_tree_id", "created_at", ...}]
        """
        self.config.require_configured()
        return self._chat._request("GET", f"/cellcog/projects/{project_id}/agent-roles")

    # ==================== Documents ====================

    def list_documents(self, context_tree_id: str) -> dict:
        """
        List all documents in a context tree.

        Args:
            context_tree_id: Context tree ID (from get_project() or create_project() response)

        Returns:
            {"documents": [{"id", "original_filename", "file_type", "file_size", "status", ...}]}
        """
        self.config.require_configured()
        return self._chat._request("GET", f"/cellcog/context-trees/{context_tree_id}/documents")

    def upload_document(
        self,
        context_tree_id: str,
        file_path: str,
        brief_context: Optional[str] = None,
    ) -> dict:
        """
        Upload a document to a context tree (admin only).

        Handles the full upload flow: request URL, upload file, confirm.
        After upload, CellCog processes the document and adds it to the
        context tree (may take a few minutes for large files).

        Args:
            context_tree_id: Context tree ID
            file_path: Absolute path to local file (max 100 MB)
            brief_context: Optional description of file contents (max 500 chars).
                Improves AI processing quality.

        Returns:
            {"file_id": str, "status": str, "message": str}

        Raises:
            FileUploadError: If file not found, too large, or upload fails
            APIError(403): If not a project admin
        """
        import mimetypes
        from pathlib import Path as _Path

        from .exceptions import FileUploadError

        self.config.require_configured()

        path = _Path(file_path)
        if not path.exists():
            raise FileUploadError(f"File not found: {file_path}")

        filename = path.name
        file_size = path.stat().st_size
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"

        # Client-side file size validation (100 MB limit)
        max_file_size = 100 * 1024 * 1024
        if file_size > max_file_size:
            raise FileUploadError(
                f"File too large: {file_size / (1024 * 1024):.1f} MB. "
                f"Maximum allowed: 100 MB."
            )

        # Step 1: Request upload URL
        request_data = {
            "filename": filename,
            "file_size": file_size,
            "mime_type": mime_type,
        }
        if brief_context:
            request_data["brief_context"] = brief_context

        upload_info = self._chat._request(
            "POST",
            f"/cellcog/context-trees/{context_tree_id}/documents/request-upload",
            request_data,
        )

        # Step 2: Upload to signed URL
        import requests

        try:
            with open(file_path, "rb") as f:
                put_resp = requests.put(
                    upload_info["upload_url"],
                    data=f,
                    headers={"Content-Type": mime_type},
                    timeout=300,
                )
                put_resp.raise_for_status()
        except requests.RequestException as e:
            raise FileUploadError(f"Failed to upload file to storage: {e}")

        # Step 3: Confirm upload
        confirm_result = self._chat._request(
            "POST",
            f"/cellcog/context-trees/{context_tree_id}/documents/confirm-upload/{upload_info['file_id']}",
        )

        return {
            "file_id": upload_info["file_id"],
            "status": confirm_result.get("status", "processing"),
            "message": (
                f"Document '{filename}' uploaded successfully. "
                f"CellCog is processing it — this may take a few minutes. "
                f"The document will appear in the context tree once processed."
            ),
        }

    def delete_document(self, context_tree_id: str, file_id: str) -> dict:
        """
        Delete a document from a context tree (admin only).

        Args:
            context_tree_id: Context tree ID
            file_id: File ID (from list_documents() or upload_document())

        Returns:
            {"message": "Document deleted successfully"}
        """
        self.config.require_configured()
        return self._chat._request(
            "DELETE",
            f"/cellcog/context-trees/{context_tree_id}/documents/{file_id}",
        )

    def bulk_delete_documents(self, context_tree_id: str, file_ids: list) -> dict:
        """
        Delete multiple documents at once (admin only).

        Args:
            context_tree_id: Context tree ID
            file_ids: List of file IDs to delete (max 100)

        Returns:
            {"deleted": int, "failed": int, "results": {...}}
        """
        self.config.require_configured()
        return self._chat._request(
            "POST",
            f"/cellcog/context-trees/{context_tree_id}/documents/bulk-delete",
            {"file_ids": file_ids},
        )

    # ==================== Context Tree ====================

    def get_context_tree_markdown(self, context_tree_id: str, include_long_description: bool = False) -> dict:
        """
        Get the AI-processed markdown view of a context tree.

        Returns the hierarchical document structure with descriptions,
        metadata, and organization. Use this to understand what documents
        are available before downloading specific files.

        Args:
            context_tree_id: Context tree ID
            include_long_description: If True, include detailed long descriptions
                for each file in addition to short summaries. Default False.

        Returns:
            {"context_tree_id": str, "owner_type": str, "markdown": str}
        """
        self.config.require_configured()
        path = f"/cellcog/context-trees/{context_tree_id}/markdown"
        if include_long_description:
            path += "?include_long_description=true"
        return self._chat._request("GET", path)

    def get_document_signed_urls(
        self,
        context_tree_id: str,
        file_ids: list,
        expiration_hours: int = 1,
    ) -> dict:
        """
        Get time-limited download URLs for documents.

        Signed URLs can be passed to other agents, tools, or humans
        for direct file access without CellCog authentication.

        Args:
            context_tree_id: Context tree ID
            file_ids: List of file IDs (max 100)
            expiration_hours: URL lifetime in hours (1-168, default 1)

        Returns:
            {"urls": {file_id: url_or_null}, "errors": {file_id: error_msg}}
        """
        self.config.require_configured()
        return self._chat._request(
            "POST",
            f"/cellcog/context-trees/{context_tree_id}/documents/signed-urls",
            {
                "file_ids": file_ids,
                "expiration_hours": expiration_hours,
            },
        )

    def get_document_signed_urls_by_path(
        self,
        context_tree_id: str,
        file_paths: list,
        expiration_hours: int = 1,
    ) -> dict:
        """
        Get time-limited download URLs for documents by their file path.

        Use paths as shown in get_context_tree_markdown() output
        (e.g., '/financials/earnings_report.pdf'). This is the recommended
        method — no file IDs needed.

        Args:
            context_tree_id: Context tree ID
            file_paths: List of file paths from the context tree markdown (max 100)
            expiration_hours: URL lifetime in hours (1-168, default 1)

        Returns:
            {"urls": {path: url_or_null}, "errors": {path: error_msg}}
        """
        self.config.require_configured()
        return self._chat._request(
            "POST",
            f"/cellcog/context-trees/{context_tree_id}/documents/signed-urls-by-path",
            {
                "file_paths": file_paths,
                "expiration_hours": expiration_hours,
            },
        )

    # ==================== Gateway Health Check ====================

    def _is_sessions_send_available(self, gateway_url: str) -> bool | None:
        """
        Check if sessions_send is available on the OpenClaw Gateway.

        OpenClaw 2026.4+ puts sessions_send on a hard deny list for the
        /tools/invoke HTTP endpoint by default. Without explicit
        gateway.tools.allow configuration, the daemon cannot deliver
        completion notifications to the agent's session.

        Uses a lightweight probe: invoke sessions_send with a dummy
        session key. If the tool is blocked we get a 404 with
        "Tool not available"; any other response means the tool is
        reachable (even if the session itself doesn't exist).

        Results are cached per gateway_url for 60 seconds.

        Args:
            gateway_url: OpenClaw Gateway URL

        Returns:
            True if available, False if blocked, None if check failed
        """
        # Check cache
        cached = self._sessions_send_cache.get(gateway_url)
        if cached:
            is_available, checked_at = cached
            if time.time() - checked_at < self._sessions_send_cache_ttl:
                return is_available

        # Resolve auth token
        gateway_auth = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
        headers = {"Content-Type": "application/json"}
        if gateway_auth:
            headers["Authorization"] = f"Bearer {gateway_auth}"

        try:
            resp = _requests.post(
                f"{gateway_url}/tools/invoke",
                headers=headers,
                json={
                    "tool": "sessions_send",
                    "args": {
                        "sessionKey": "__cellcog_preflight__",
                        "message": "preflight",
                        "timeoutSeconds": 0,
                    },
                },
                timeout=2.0,
            )

            if resp.status_code == 404:
                # 404 from /tools/invoke means tool is not available
                data = resp.json() if resp.text else {}
                error_msg = data.get("error", {}).get("message", "")
                if "not available" in error_msg.lower():
                    self._sessions_send_cache[gateway_url] = (False, time.time())
                    return False

            if resp.status_code == 401:
                # Auth issue — different problem, don't cache as blocked
                return None

            # Any other response (200 success, 400 bad args, etc.) means
            # the tool IS available on the gateway
            self._sessions_send_cache[gateway_url] = (True, time.time())
            return True

        except Exception:
            # Network error, timeout, etc. — can't determine, don't warn
            return None

    def _require_sessions_send(self, gateway_url: str) -> None:
        """
        Verify that sessions_send is available on the Gateway. Raises
        GatewayConfigError if the tool is blocked.

        Called at the start of create_chat() and send_message() to
        fail fast before spending credits on a chat whose results
        cannot be delivered.

        Args:
            gateway_url: OpenClaw Gateway URL to check

        Raises:
            GatewayConfigError: If sessions_send is on the deny list
        """
        available = self._is_sessions_send_available(gateway_url)
        if available is False:
            raise GatewayConfigError(gateway_url)

    # ==================== Daemon Management ====================

    def _has_tracked_chats(self) -> bool:
        """Check if there are any tracked chats on disk."""
        tracked_dir = Path("~/.cellcog/tracked_chats").expanduser()
        if not tracked_dir.exists():
            return False
        return any(tracked_dir.glob("*.json"))

    def _kill_daemon_if_running(self) -> bool:
        """
        Kill daemon process if it's running.
        
        Returns:
            True if a daemon was running and was killed, False otherwise
        """
        if not self._is_daemon_alive():
            return False
        
        try:
            pid = int(self._daemon_pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            # Wait for clean shutdown (daemon handles SIGTERM gracefully)
            time.sleep(1.5)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        finally:
            # Clean up PID file
            try:
                self._daemon_pid_file.unlink(missing_ok=True)
            except Exception:
                pass
        
        return True

    def _ensure_daemon_running(self) -> bool:
        """
        Ensure the daemon process is running with current SDK version.
        
        Called before create_chat() and send_message() to ensure
        the daemon is alive and running the same SDK version.
        If a version mismatch is detected (e.g., after pip install),
        the old daemon is killed and a fresh one is started.
        
        Uses a guard flag to prevent re-entrant calls (e.g., when
        _is_daemon_alive triggers _kill_daemon during concurrent operations).
        
        Returns:
            True if daemon is running (or was started)
        """
        if self._daemon_check_in_progress:
            return False  # Prevent recursion
        
        self._daemon_check_in_progress = True
        try:
            if self._is_daemon_alive():
                if self._is_daemon_version_stale():
                    from . import __version__
                    print(f"Daemon version mismatch detected, restarting with SDK v{__version__}...", file=sys.stderr)
                    self._kill_daemon_if_running()
                    return self._start_daemon()
                return True
            
            return self._start_daemon()
        finally:
            self._daemon_check_in_progress = False
    
    def _is_daemon_version_stale(self) -> bool:
        """
        Check if running daemon has a different SDK version than current.
        
        The daemon writes its version to ~/.cellcog/daemon.version on startup.
        If this file is missing (pre-version-check daemon) or contains a
        different version, the daemon is considered stale.
        
        Returns:
            True if daemon should be restarted with current SDK
        """
        version_file = Path("~/.cellcog/daemon.version").expanduser()
        if not version_file.exists():
            return True  # No version file = old daemon pre-dating this feature
        try:
            daemon_version = version_file.read_text().strip()
            from . import __version__
            return daemon_version != __version__
        except Exception:
            return True  # Can't read = assume stale
    
    def _is_daemon_alive(self) -> bool:
        """
        Check if daemon process is running AND responsive.
        
        Uses two checks:
        1. PID file exists and process is alive (existing)
        2. Heartbeat file is fresh (<120s old) (new — catches frozen daemons)
        """
        if not self._daemon_pid_file.exists():
            return False
        
        try:
            pid = int(self._daemon_pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if alive (doesn't actually kill)
        except (ValueError, ProcessLookupError, PermissionError):
            return False
        
        # Heartbeat check: daemon writes timestamp every 30s.
        # If stale (>120s), daemon is frozen (e.g., stuck after sleep).
        heartbeat_file = Path("~/.cellcog/daemon.heartbeat").expanduser()
        if heartbeat_file.exists():
            try:
                heartbeat_time = float(heartbeat_file.read_text().strip())
                age = time.time() - heartbeat_time
                if age > 120:
                    print(
                        f"Warning: Daemon heartbeat stale ({age:.0f}s old). "
                        f"Killing and restarting...",
                        file=sys.stderr
                    )
                    self._kill_daemon_if_running()
                    return False
            except (ValueError, IOError):
                pass  # Can't read heartbeat — don't block on this
        
        return True
    
    def _start_daemon(self) -> bool:
        """
        Start the daemon process.
        
        Returns:
            True if daemon was started successfully
        """
        try:
            # Ensure directory exists
            self._daemon_pid_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Start daemon as subprocess
            # Use the same Python interpreter and run daemon module
            daemon_cmd = [
                sys.executable,
                "-m", "cellcog.daemon.main",
                self.config.api_key,
                self.config.api_base_url
            ]
            
            # Start detached process
            if sys.platform == "win32":
                # Windows: use CREATE_NEW_PROCESS_GROUP
                proc = subprocess.Popen(
                    daemon_cmd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # Unix: start new session
                proc = subprocess.Popen(
                    daemon_cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            
            # Wait briefly for daemon to start
            time.sleep(0.5)
            
            # Verify it started
            if self._is_daemon_alive():
                return True
            
            # Check if process is still running
            if proc.poll() is None:
                return True
            
            return False
            
        except Exception as e:
            print(f"Warning: Could not start daemon: {e}", file=sys.stderr)
            return False

    def _track_chat(
        self,
        chat_id: str,
        delivery_mode: str = "notify_on_completion",
        session_key: Optional[str] = None,
        gateway_url: Optional[str] = None,
        task_label: str = "",
    ) -> dict:
        """
        Create or update tracking file for daemon.
        
        Args:
            chat_id: CellCog chat ID
            delivery_mode: "notify_on_completion" or "wait_for_completion"
            session_key: OpenClaw session key (required for notify mode)
            gateway_url: OpenClaw Gateway URL (required for notify mode)
            task_label: Human-readable label
        
        Returns:
            Tracking info dict
        """
        listeners = []
        if delivery_mode == "notify_on_completion" and session_key and gateway_url:
            listener = Listener(
                session_key=session_key,
                gateway_url=gateway_url,
                gateway_auth_source="env:OPENCLAW_GATEWAY_TOKEN",
                task_label=task_label,
            )
            listeners = [listener]
        
        # Check if chat already tracked
        chat_file = self._state.get_tracked_file_path(chat_id)
        
        if chat_file.exists():
            chat = TrackedChat.from_file(chat_file)
            if listeners:
                for listener in listeners:
                    chat.add_listener(listener)
            # Update delivery mode if upgrading from wait to notify
            if delivery_mode == "notify_on_completion":
                chat.delivery_mode = delivery_mode
            self._state.save_tracked(chat)
        else:
            chat = TrackedChat(
                chat_id=chat_id,
                listeners=listeners,
                delivery_mode=delivery_mode,
            )
            self._state.save_tracked(chat)
        
        return {
            "daemon_active": self._is_daemon_alive(),
            "listeners": len(chat.listeners),
            "delivery_mode": delivery_mode,
        }

    # ==================== Data Management ====================

    def delete_chat(self, chat_id: str) -> dict:
        """
        Permanently delete a chat and all associated data from CellCog's servers.

        This is irreversible. All server-side data is purged within ~15 seconds:
        messages, generated files, containers, metadata — everything.

        Local downloads (files saved to your machine during the chat) are NOT
        deleted — they belong to you.

        Args:
            chat_id: Chat to delete (must not be currently operating)

        Returns:
            {"success": True, "message": str, "chat_id": str}

        Raises:
            APIError(409): Chat is currently operating or already being deleted
            ChatNotFoundError: Chat not found

        Example:
            result = client.delete_chat("abc123")
            print(result["message"])  # "Chat deletion initiated..."
        """
        self.config.require_configured()

        try:
            result = self._chat._request(
                "DELETE",
                f"/cellcog/chat/{chat_id}?confirm=true"
            )
        except APIError as e:
            if e.status_code == 409:
                raise APIError(
                    409,
                    f"Cannot delete chat {chat_id}: {e.message}. "
                    f"Wait for it to finish operating first."
                )
            raise

        # Clean up local tracking state (NOT user's downloaded files)
        self._cleanup_tracking_state(chat_id)

        return result

    def _cleanup_tracking_state(self, chat_id: str):
        """
        Remove local tracking files for a deleted chat.
        Downloaded files are preserved — they belong to the user.
        """
        import shutil

        # Remove tracking file (daemon will stop monitoring)
        tracking_file = self._state.get_tracked_file_path(chat_id)
        if tracking_file.exists():
            tracking_file.unlink(missing_ok=True)

        # Remove seen indices (no longer relevant)
        seen_dir = Path("~/.cellcog/chats/{}/{}".format(chat_id, ".seen_indices")).expanduser()
        if seen_dir.exists():
            shutil.rmtree(seen_dir, ignore_errors=True)

    # ==================== Utility Methods ====================

    def list_chats(self, limit: int = 20) -> list:
        """List recent chats."""
        return self._chat.list_chats(limit)

    def check_pending_chats(self) -> list:
        """Check all chats and return recently completed ones."""
        return self._chat.check_pending()

    # ==================== Documentation ====================

    def get_support_docs(self) -> str:
        """
        Get CellCog support and troubleshooting documentation.

        Returns markdown covering error handling, recovery patterns,
        chat deletion, ticket submission, daemon troubleshooting,
        data privacy, and terms of service.

        Returns:
            str: Markdown documentation
        """
        return self._load_bundled_doc("support.md")

    def get_api_reference(self) -> str:
        """
        Get the complete CellCog SDK API reference.

        Returns markdown covering all method signatures, parameters,
        return types, and exception classes.

        Returns:
            str: Markdown documentation
        """
        return self._load_bundled_doc("api_reference.md")

    def _load_bundled_doc(self, filename: str) -> str:
        """Load a bundled documentation file from the SDK package."""
        import os
        docs_dir = os.path.join(os.path.dirname(__file__), "docs")
        filepath = os.path.join(docs_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"Documentation file '{filename}' not found. Try updating the SDK: pip install --upgrade cellcog"
