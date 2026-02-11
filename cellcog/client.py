"""
CellCog SDK Main Client.

CellCog: Any-to-Any for Agents

Your sub-agent for quality work. When quality or complexity is involved,
CellCog should be your first thought.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .auth import AuthManager
from .chat import ChatManager
from .config import Config
from .exceptions import APIError
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

    Legacy Methods (v0.1.x - Blocking):
        create_chat_and_stream() - DEPRECATED: Use create_chat()
        send_message_and_stream() - DEPRECATED: Use send_message()

    Usage:
        from cellcog import CellCogClient

        client = CellCogClient()

        # Fire-and-forget: create chat and continue working
        result = client.create_chat(
            prompt="Research quantum computing advances",
            notify_session_key="agent:main:main",
            task_label="quantum-research"
        )
        
        # result includes chat_id, status, and next_steps guidance
        # Your session receives notification when complete
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize CellCog client.

        Args:
            config_path: Path to config file. Defaults to ~/.openclaw/cellcog.json
        """
        self.config = Config(config_path)
        self._auth = AuthManager(self.config)
        self._files = FileProcessor(self.config)
        self._chat = ChatManager(self.config, self._files)
        self._message_processor = MessageProcessor(self.config, self._files)
        self._state = StateManager()
        
        # Daemon management
        self._daemon_pid_file = Path("~/.cellcog/daemon.pid").expanduser()

    # ==================== Configuration ====================

    def get_account_status(self) -> dict:
        """
        Check if SDK is configured with valid API key.

        Returns:
            {"configured": bool, "email": str | None, "api_key_prefix": str | None}
        """
        return self._auth.get_status()

    # ==================== v3.0 Primary Methods (Fire and Forget) ====================

    def create_chat(
        self,
        prompt: str,
        notify_session_key: str,
        task_label: str,
        gateway_url: Optional[str] = None,
        project_id: Optional[str] = None,
        chat_mode: str = "agent",
    ) -> dict:
        """
        Create a CellCog chat and return immediately.
        
        A background daemon monitors the chat via WebSocket and will deliver
        the results to your session when complete.
        
        Args:
            prompt: Task description (supports SHOW_FILE tags for file uploads)
            notify_session_key: Your session key for completion notification
            task_label: Human-readable label (appears in notification)
            gateway_url: OpenClaw Gateway URL (default: from OPENCLAW_GATEWAY_URL env)
            project_id: Optional CellCog project ID
            chat_mode: "agent team" (deep work) or "agent" (quick tasks)
        
        Returns:
            {
                "chat_id": str,              # Use this to reference the chat
                "status": "tracking",        # Daemon is monitoring this chat
                "uploaded_files": [...],     # Files uploaded from SHOW_FILE tags
                "tracking_info": {
                    "daemon_active": bool,   # Whether daemon process is running
                    "listeners": int,        # Number of sessions listening
                },
                "next_steps": str            # What to expect next
            }
        
        Example:
            result = client.create_chat(
                prompt="Research quantum computing advances in 2026",
                notify_session_key="agent:main:main",
                task_label="quantum-research"
            )
            
            # Continue with other work while CellCog processes...
            # You'll receive notification at your session when complete.
        """
        self.config.require_configured()
        
        # 1. Create the chat via API
        api_result = self._chat.create(prompt, project_id, chat_mode)
        chat_id = api_result["chat_id"]
        
        # Resolve gateway URL
        gateway_url = gateway_url or os.environ.get(
            "OPENCLAW_GATEWAY_URL", 
            "http://127.0.0.1:18789"
        )
        
        # 2. Write tracking file BEFORE starting daemon
        #    This ensures the daemon finds the tracking file during reconcile_state().
        #    If we started daemon first, it could exit before the tracking file exists.
        tracking_info = self._track_chat(
            chat_id=chat_id,
            session_key=notify_session_key,
            gateway_url=gateway_url,
            task_label=task_label
        )
        
        # 3. Now ensure daemon is running (tracking file already on disk)
        self._ensure_daemon_running()
        
        # Build helpful explanation
        explanation = (
            f"✓ Chat '{task_label}' created (ID: {chat_id})\n"
            f"✓ Daemon is monitoring via WebSocket\n"
            f"✓ You'll receive notification at '{notify_session_key}' when complete\n\n"
            f"You can continue with other work. Do NOT poll - the daemon will notify you automatically "
            f"with the full response and any generated files."
        )
        
        result = {
            "chat_id": chat_id,
            "status": "tracking",
            "daemon_listening": self._is_daemon_alive(),
            "listeners": tracking_info["listeners"],
            "explanation": explanation
        }
        
        # Only include uploaded_files if there actually were files uploaded
        if api_result.get("uploaded_files"):
            result["uploaded_files"] = api_result["uploaded_files"]
        
        return result

    def send_message(
        self,
        chat_id: str,
        message: str,
        notify_session_key: str,
        task_label: Optional[str] = None,
        gateway_url: Optional[str] = None,
    ) -> dict:
        """
        Send a message to existing chat and return immediately.
        
        Adds your session as a listener if not already listening.
        
        Args:
            chat_id: Chat to send to
            message: Your message (supports SHOW_FILE tags for file uploads)
            notify_session_key: Your session key for notification
            task_label: Label for notification (default: "continue-{chat_id[:8]}")
            gateway_url: OpenClaw Gateway URL
        
        Returns:
            {
                "status": "tracking",
                "uploaded_files": [...],
                "tracking_info": {...},
                "next_steps": str
            }
        """
        self.config.require_configured()
        
        # 1. Send message via API
        api_result = self._chat.send_message(chat_id, message)
        
        # Resolve gateway URL and task label
        gateway_url = gateway_url or os.environ.get(
            "OPENCLAW_GATEWAY_URL",
            "http://127.0.0.1:18789"
        )
        task_label = task_label or f"continue-{chat_id[:8]}"
        
        # 2. Write tracking file BEFORE starting daemon
        tracking_info = self._track_chat(
            chat_id=chat_id,
            session_key=notify_session_key,
            gateway_url=gateway_url,
            task_label=task_label
        )
        
        # 3. Now ensure daemon is running (tracking file already on disk)
        self._ensure_daemon_running()
        
        explanation = (
            f"✓ Message sent to chat {chat_id}\n"
            f"✓ Daemon is monitoring via WebSocket\n"
            f"✓ You'll receive notification at '{notify_session_key}' when complete\n\n"
            f"Do NOT poll - the daemon will automatically notify you with the response."
        )
        
        result = {
            "chat_id": chat_id,
            "status": "tracking",
            "daemon_listening": self._is_daemon_alive(),
            "listeners": tracking_info["listeners"],
            "explanation": explanation
        }
        
        # Only include uploaded_files if there actually were files uploaded
        if api_result.get("uploaded_files"):
            result["uploaded_files"] = api_result["uploaded_files"]
        
        return result

    def get_history(
        self,
        chat_id: str,
        download_files: bool = True
    ) -> dict:
        """
        Get full chat history (ignores seen indices).
        
        Use for manual inspection or memory recovery.
        Does NOT update seen indices.
        
        Args:
            chat_id: Chat to retrieve
            download_files: Whether to download files (default True)
        
        Returns:
            {
                "chat_id": str,
                "is_operating": bool,
                "formatted_output": str,    # Full formatted messages
                "message_count": int,
                "downloaded_files": [...],
                "status_message": str       # Operating status info
            }
        """
        self.config.require_configured()
        
        # Get status
        status = self.get_status(chat_id)
        
        # Get history from API
        history = self._chat._request("GET", f"/cellcog/chat/{chat_id}/history")
        
        # Process full history (ignores seen indices)
        result = self._message_processor.process_full_history(
            chat_id=chat_id,
            history=history,
            is_operating=status["is_operating"],
            download_files=download_files
        )
        
        # Build status message
        if status["is_operating"]:
            status_message = (
                f"⏳ Chat is still operating. "
                f"CellCog is working on your request. "
                f"The history above shows progress so far."
            )
        else:
            status_message = (
                f"✅ Chat completed. "
                f"All messages and files are shown above."
            )
        
        return {
            "chat_id": chat_id,
            "is_operating": status["is_operating"],
            "formatted_output": result.formatted_output,
            "message_count": result.delivered_count,
            "downloaded_files": result.downloaded_files,
            "status_message": status_message
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
        
        Returns:
            True if daemon is running (or was started)
        """
        if self._is_daemon_alive():
            # Check if running daemon matches current SDK version
            if self._is_daemon_version_stale():
                from . import __version__
                print(f"Daemon version mismatch detected, restarting with SDK v{__version__}...", file=sys.stderr)
                self._kill_daemon_if_running()
                return self._start_daemon()
            return True
        
        # Start daemon
        return self._start_daemon()
    
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
        """Check if daemon process is running."""
        if not self._daemon_pid_file.exists():
            return False
        
        try:
            pid = int(self._daemon_pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if alive (doesn't actually kill)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            return False
    
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
        session_key: str,
        gateway_url: str,
        task_label: str
    ) -> dict:
        """
        Create or update tracking file for daemon.
        
        Returns tracking info for feedback.
        """
        # Create listener
        listener = Listener(
            session_key=session_key,
            gateway_url=gateway_url,
            gateway_auth_source="env:OPENCLAW_GATEWAY_TOKEN",
            task_label=task_label
        )
        
        # Check if chat already tracked
        chat_file = self._state.get_tracked_file_path(chat_id)
        
        if chat_file.exists():
            # Load existing and add listener
            chat = TrackedChat.from_file(chat_file)
            added = chat.add_listener(listener)
            if added:
                self._state.save_tracked(chat)
            listeners_count = len(chat.listeners)
        else:
            # Create new tracking file
            chat = TrackedChat(
                chat_id=chat_id,
                listeners=[listener]
            )
            self._state.save_tracked(chat)
            listeners_count = 1
        
        return {
            "daemon_active": self._is_daemon_alive(),
            "listeners": listeners_count,
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
