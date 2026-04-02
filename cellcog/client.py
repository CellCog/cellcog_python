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

    Synchronous Wait (v1.10 - Workflow Support):
        wait_for_completion() - Block until chat finishes (for workflows)

    Legacy Methods (v0.1.x - Blocking):
        create_chat_and_stream() - DEPRECATED: Use create_chat()
        send_message_and_stream() - DEPRECATED: Use send_message()

    Usage (Fire-and-Forget):
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
        notify_session_key: str,
        task_label: str,
        gateway_url: Optional[str] = None,
        project_id: Optional[str] = None,
        agent_role_id: Optional[str] = None,
        chat_mode: str = "agent",
        enable_cowork: bool = False,
        cowork_working_directory: Optional[str] = None,
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
            project_id: Optional CellCog project ID for document context
            agent_role_id: Optional agent role ID within the project. Requires project_id.
                Specializes agent behavior with custom instructions and role-specific memory.
            chat_mode: "agent" (fast, most tasks), "agent core" (coding/co-work), "agent team" (deep reasoning), or "agent team max" (high-stakes)
            enable_cowork: Enable co-work on user's PC. When True, CellCog agents can
                run commands on the user's machine via the CellCog Desktop app.
                All commands are auto-approved for SDK/agent users.
            cowork_working_directory: Working directory on user's machine for co-work
                commands. Only used when enable_cowork=True.
        
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
                prompt="Fix the bug in main.py at line 42",
                notify_session_key="agent:main:main",
                task_label="fix-bug",
                enable_cowork=True,
                cowork_working_directory="/Users/me/project"
            )
            
            # Continue with other work while CellCog processes...
            # You'll receive notification at your session when complete.
        """
        self.config.require_configured()
        
        # 1. Create the chat via API
        api_result = self._chat.create(
            prompt, project_id, chat_mode,
            agent_role_id=agent_role_id,
            hc_enabled=enable_cowork,
            hc_working_directory=cowork_working_directory,
        )
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

    # ==================== Synchronous Wait ====================

    def wait_for_completion(self, chat_id: str, timeout: int = 1800) -> dict:
        """
        Block until a CellCog chat finishes operating or timeout is reached.

        Composes with create_chat() and send_message() to enable synchronous
        workflow patterns. The daemon continues to handle result delivery to
        your session — this method simply blocks your thread until that
        delivery is complete.

        If timeout is reached, the chat continues processing and the daemon
        will deliver results to your session automatically. You can call
        wait_for_completion() again to resume waiting.

        Args:
            chat_id: Chat to wait on
            timeout: Maximum seconds to wait (default: 1800 = 30 min).
                     Use 1800 for simple jobs, 3600 for complex jobs.

        Returns:
            {
                "chat_id": str,
                "is_operating": bool,       # False = done, True = still working
                "status": str,              # "completed" | "waiting"
                "status_message": str       # Human-readable status
            }

        Example:
            # Create chat (fire-and-forget as usual)
            result = client.create_chat(
                prompt="Research quantum computing advances",
                notify_session_key="agent:main:main",
                task_label="quantum-research"
            )

            # Block until done (daemon delivers results to your session)
            completion = client.wait_for_completion(
                result["chat_id"], timeout=1800
            )

            if not completion["is_operating"]:
                # Done — results already delivered to your session
                proceed_with_next_step()

        Workflow Example:
            # Step 1
            r1 = client.create_chat(prompt="Research X", ...)
            client.wait_for_completion(r1["chat_id"], timeout=1800)

            # Step 2 (uses results from step 1 via chat context)
            r2 = client.send_message(chat_id=r1["chat_id"],
                message="Now create a PDF summary", ...)
            client.wait_for_completion(r1["chat_id"], timeout=1800)
        """
        self.config.require_configured()

        tracking_file = self._state.get_tracked_file_path(chat_id)
        start_time = time.time()

        completed_message = (
            "✅ Chat completed. All processing is finished and any "
            "generated files have already been created. "
            "You will receive the full response in your session "
            "within the next few seconds."
        )

        # If tracking file doesn't already exist, the chat may have
        # completed before we started waiting.  Do one status check.
        if not tracking_file.exists():
            try:
                status = self.get_status(chat_id)
                if not status["is_operating"]:
                    return {
                        "chat_id": chat_id,
                        "is_operating": False,
                        "status": "completed",
                        "status_message": completed_message,
                    }
            except Exception:
                pass  # Proceed to wait loop; may still resolve

        # Simple wait loop — check every 2 seconds if the daemon has
        # finished processing (it removes the tracking file after
        # delivering results to all listeners).
        while time.time() - start_time < timeout:
            if not tracking_file.exists():
                return {
                    "chat_id": chat_id,
                    "is_operating": False,
                    "status": "completed",
                    "status_message": completed_message,
                }

            remaining = timeout - (time.time() - start_time)
            time.sleep(min(2, max(0, remaining)))

        # Timeout reached — chat is still operating
        return {
            "chat_id": chat_id,
            "is_operating": True,
            "status": "waiting",
            "status_message": (
                f"Timeout reached ({timeout}s). CellCog is still working.\n"
                f"The daemon will deliver results to your session "
                f"automatically.\n"
                f"To wait again: "
                f"client.wait_for_completion('{chat_id}')"
            ),
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
