"""
CellCog SDK Chat Operations.

Handles chat creation, messaging, status, and history retrieval.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from .config import Config
from .exceptions import APIError, AuthenticationError, ChatNotFoundError, PaymentRequiredError
from .files import FileProcessor


class ChatManager:
    """
    Manages chat operations for CellCog SDK.

    Handles:
    - Creating new chats
    - Sending messages
    - Getting chat status
    - Retrieving and transforming chat history
    - Streaming unseen messages with per-session tracking
    - Efficient file downloads (only for unseen messages)
    - Main agent guardrails (max 2 minute timeout)
    """

    def __init__(self, config: Config, file_processor: FileProcessor):
        self.config = config
        self.files = file_processor
        self._chats_dir = Path("~/.cellcog/chats").expanduser()

    def _validate_main_agent_timeout(self, main_agent: bool, timeout_seconds: int) -> None:
        """
        Validate that main agent isn't waiting too long.
        
        Main agent should not block for more than 2 minutes.
        If they need longer, they should spawn a sub-session.
        
        Args:
            main_agent: Whether this is the main agent calling
            timeout_seconds: Requested timeout
            
        Raises:
            ValueError: If main_agent=True and timeout_seconds > 120
        """
        if main_agent and timeout_seconds > 120:
            raise ValueError(
                "Main agent cannot wait more than 2 minutes on CellCog. "
                "Create a sub-session using sessions_spawn to handle CellCog tasks."
            )

    def create(self, prompt: str, project_id: Optional[str] = None, chat_mode: str = "agent team") -> dict:
        """
        Create a new CellCog chat (without streaming).

        For most use cases, use create_chat_and_stream() instead.

        Args:
            prompt: Initial prompt (can include SHOW_FILE, GENERATE_FILE tags)
            project_id: Optional CellCog project ID
            chat_mode: "agent team" (deep reasoning) or "agent" (faster)

        Returns:
            {
                "chat_id": str,
                "status": "processing" | "ready",
                "uploaded_files": [{"local": str, "blob": str}]
            }
        """
        self.config.require_configured()

        mode_mapping = {
            "agent team": "agent_in_the_loop",
            "agent": "human_in_the_loop",
        }
        api_chat_mode = mode_mapping.get(chat_mode, chat_mode)

        transformed, uploaded = self.files.transform_outgoing(prompt)

        data = {"message": transformed, "chat_mode": api_chat_mode}
        if project_id:
            data["project_id"] = project_id

        resp = self._request("POST", "/cellcog/chat/new", data)

        return {
            "chat_id": resp["id"],
            "status": "processing" if resp["operating"] else "ready",
            "uploaded_files": uploaded,
        }

    def create_chat_and_stream(
        self,
        prompt: str,
        session_id: str,
        main_agent: bool,
        project_id: Optional[str] = None,
        chat_mode: str = "agent team",
        timeout_seconds: int = 600,
        poll_interval: int = 10,
    ) -> dict:
        """
        Create a new CellCog chat and stream responses until completion.

        This is the PRIMARY method for starting CellCog work. It:
        1. Creates the chat
        2. Immediately prints the chat_id
        3. Streams all messages as they arrive

        Args:
            prompt: Initial prompt (supports SHOW_FILE, GENERATE_FILE)
            session_id: Your OpenClaw session ID
            main_agent: True if calling from main session.
                       If True, timeout_seconds must be <= 120.
            project_id: Optional CellCog project ID
            chat_mode: "agent team" (deep reasoning) or "agent" (faster)
            timeout_seconds: Max wait time (default 10 min)
            poll_interval: Seconds between checks (default 10)

        Returns:
            {
                "chat_id": str,
                "status": "completed" | "timeout" | "error",
                "messages_delivered": int,
                "uploaded_files": [...],
                "elapsed_seconds": float,
                "error_type": str | None
            }

        Raises:
            ValueError: If main_agent=True and timeout_seconds > 120
        """
        # Validate guardrail
        self._validate_main_agent_timeout(main_agent, timeout_seconds)

        # Create the chat
        create_result = self.create(prompt, project_id, chat_mode)
        chat_id = create_result["chat_id"]

        # Immediately print chat_id so caller knows it
        print(f"Chat created: {chat_id}")
        print()

        # Stream responses
        stream_result = self.stream_unseen_messages_and_wait_for_completion(
            chat_id, session_id, main_agent, timeout_seconds, poll_interval
        )

        return {
            "chat_id": chat_id,
            "status": stream_result["status"],
            "messages_delivered": stream_result["messages_delivered"],
            "uploaded_files": create_result.get("uploaded_files", []),
            "elapsed_seconds": stream_result["elapsed_seconds"],
            "error_type": stream_result.get("error_type"),
        }

    def send_message(self, chat_id: str, message: str) -> dict:
        """
        Send a message to existing chat (without streaming).

        For most use cases, use send_message_and_stream() instead.

        Args:
            chat_id: The chat to send to
            message: Message content (can include SHOW_FILE, GENERATE_FILE tags)

        Returns:
            {"status": "sent", "uploaded_files": [...]}
        """
        self.config.require_configured()

        transformed, uploaded = self.files.transform_outgoing(message)
        self._request("POST", f"/cellcog/chat/{chat_id}/messages", {"message": transformed})

        return {"status": "sent", "uploaded_files": uploaded}

    def send_message_and_stream(
        self,
        chat_id: str,
        message: str,
        session_id: str,
        main_agent: bool,
        timeout_seconds: int = 600,
        poll_interval: int = 10,
    ) -> dict:
        """
        Send a message and stream responses until completion.

        This is the PRIMARY method for continuing CellCog conversations.

        Args:
            chat_id: The chat to send to
            message: Your message (supports SHOW_FILE, GENERATE_FILE)
            session_id: Your OpenClaw session ID
            main_agent: True if calling from main session.
                       If True, timeout_seconds must be <= 120.
            timeout_seconds: Max wait time (default 10 min)
            poll_interval: Seconds between checks (default 10)

        Returns:
            {
                "status": "completed" | "timeout" | "error",
                "messages_delivered": int,
                "uploaded_files": [...],
                "elapsed_seconds": float,
                "error_type": str | None
            }

        Raises:
            ValueError: If main_agent=True and timeout_seconds > 120
        """
        # Validate guardrail
        self._validate_main_agent_timeout(main_agent, timeout_seconds)

        # Send the message
        send_result = self.send_message(chat_id, message)

        # Stream responses
        stream_result = self.stream_unseen_messages_and_wait_for_completion(
            chat_id, session_id, main_agent, timeout_seconds, poll_interval
        )

        return {
            "status": stream_result["status"],
            "messages_delivered": stream_result["messages_delivered"],
            "uploaded_files": send_result.get("uploaded_files", []),
            "elapsed_seconds": stream_result["elapsed_seconds"],
            "error_type": stream_result.get("error_type"),
        }

    def get_status(self, chat_id: str) -> dict:
        """
        Get current status of a chat.

        Args:
            chat_id: The chat to check

        Returns:
            {
                "status": "processing" | "ready" | "error",
                "name": str,
                "is_operating": bool,
                "error_type": str | None
            }
        """
        self.config.require_configured()

        resp = self._request("GET", f"/cellcog/chat/{chat_id}")

        error_type = None
        if resp.get("is_security_threat"):
            error_type = "security_threat"
        elif resp.get("is_out_of_memory"):
            error_type = "out_of_memory"

        status = "error" if error_type else ("processing" if resp["operating"] else "ready")

        return {
            "status": status,
            "name": resp["name"],
            "is_operating": resp["operating"],
            "error_type": error_type,
        }

    def get_history(self, chat_id: str, session_id: str) -> dict:
        """
        Get full chat history. FALLBACK method for memory recovery.

        Use only when memory compaction lost information.
        For normal operation, use streaming methods instead.

        Args:
            chat_id: The chat to retrieve
            session_id: Your OpenClaw session ID (for efficient file downloads)

        Returns:
            {
                "chat_id": str,
                "messages": [{"role": str, "content": str, "created_at": str}],
                "created_at": str
            }
        """
        self.config.require_configured()

        resp = self._request("GET", f"/cellcog/chat/{chat_id}/history")

        seen_index = self._load_seen_index(chat_id, session_id)

        messages = self.files.transform_incoming_history(
            resp["messages"],
            resp.get("blob_name_to_url", {}),
            chat_id,
            skip_download_until_index=seen_index,
        )

        if messages:
            self._save_seen_index(chat_id, session_id, len(messages) - 1)

        return {
            "chat_id": resp["chat_id"],
            "messages": messages,
            "created_at": resp["createdAt"],
        }

    def list_chats(self, limit: int = 20) -> list:
        """List recent chats."""
        self.config.require_configured()

        resp = self._request("GET", f"/cellcog/chats?page=1&page_size={min(limit, 100)}")

        return [
            {
                "chat_id": c["id"],
                "name": c["name"],
                "status": "processing" if c["operating"] else "ready",
                "created_at": c.get("created_at"),
                "updated_at": c.get("updated_at"),
            }
            for c in resp["chats"]
        ]

    def stream_unseen_messages_and_wait_for_completion(
        self,
        chat_id: str,
        session_id: str,
        main_agent: bool,
        timeout_seconds: int = 600,
        poll_interval: int = 10,
    ) -> dict:
        """
        Stream unseen messages and wait for completion.

        Messages are printed as they arrive in standard format.
        Only downloads files for messages you haven't seen.

        Args:
            chat_id: The CellCog chat to watch
            session_id: Your OpenClaw session ID
            main_agent: True if calling from main session.
                       If True, timeout_seconds must be <= 120.
            timeout_seconds: Max wait time (default 10 min)
            poll_interval: Seconds between checks (default 10)

        Returns:
            {
                "status": "completed" | "timeout" | "error",
                "messages_delivered": int,
                "elapsed_seconds": float,
                "error_type": str | None
            }

        Raises:
            ValueError: If main_agent=True and timeout_seconds > 120
        """
        # Validate guardrail
        self._validate_main_agent_timeout(main_agent, timeout_seconds)

        start = time.time()
        delivered_count = 0
        last_delivered_index = self._load_seen_index(chat_id, session_id)

        while time.time() - start < timeout_seconds:
            status = self.get_status(chat_id)

            if status["error_type"]:
                return {
                    "status": "error",
                    "messages_delivered": delivered_count,
                    "elapsed_seconds": time.time() - start,
                    "error_type": status["error_type"],
                }

            is_operating = status["is_operating"]

            history = self._request("GET", f"/cellcog/chat/{chat_id}/history")

            messages = self.files.transform_incoming_history(
                history["messages"],
                history.get("blob_name_to_url", {}),
                chat_id,
                skip_download_until_index=last_delivered_index,
            )

            last_cellcog_idx = -1
            for i, msg in enumerate(messages):
                if msg["role"] == "cellcog":
                    last_cellcog_idx = i

            for i, msg in enumerate(messages):
                if i <= last_delivered_index:
                    continue

                role = msg["role"]
                timestamp = self._format_timestamp(msg["created_at"])

                print(f"<MESSAGE FROM {role} on Chat {chat_id} at {timestamp}>")
                print(msg["content"])
                print("<MESSAGE END>")

                if not is_operating and role == "cellcog" and i == last_cellcog_idx:
                    print(
                        f"[CellCog stopped operating on Chat {chat_id} - waiting for response via send_message_and_stream()]"
                    )

                print()
                delivered_count += 1

                last_delivered_index = i
                self._save_seen_index(chat_id, session_id, last_delivered_index)

            if not is_operating:
                return {
                    "status": "completed",
                    "messages_delivered": delivered_count,
                    "elapsed_seconds": time.time() - start,
                    "error_type": None,
                }

            time.sleep(poll_interval)

        return {
            "status": "timeout",
            "messages_delivered": delivered_count,
            "elapsed_seconds": timeout_seconds,
            "error_type": None,
        }

    def _get_seen_indices_dir(self, chat_id: str) -> Path:
        return self._chats_dir / chat_id / ".seen_indices"

    def _get_seen_index_path(self, chat_id: str, session_id: str) -> Path:
        return self._get_seen_indices_dir(chat_id) / session_id

    def _load_seen_index(self, chat_id: str, session_id: str) -> int:
        index_path = self._get_seen_index_path(chat_id, session_id)
        try:
            if index_path.exists():
                return int(index_path.read_text().strip())
        except (ValueError, IOError):
            pass
        return -1

    def _save_seen_index(self, chat_id: str, session_id: str, index: int) -> None:
        index_path = self._get_seen_index_path(chat_id, session_id)
        try:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(str(index))
        except IOError:
            pass

    def _format_timestamp(self, iso_timestamp: str) -> str:
        if not iso_timestamp:
            return "unknown time"
        try:
            if iso_timestamp.endswith("Z"):
                iso_timestamp = iso_timestamp[:-1] + "+00:00"
            dt = datetime.fromisoformat(iso_timestamp)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return iso_timestamp

    def check_pending(self) -> list:
        """Check all chats and return recently completed ones."""
        self.config.require_configured()

        chats = self.list_chats(limit=20)
        completed = []

        for chat in chats:
            if chat["status"] == "ready":
                try:
                    resp = self._request("GET", f"/cellcog/chat/{chat['chat_id']}/history")
                    messages = self.files.transform_incoming_history(
                        resp["messages"],
                        resp.get("blob_name_to_url", {}),
                        chat["chat_id"],
                        skip_download_until_index=len(resp["messages"]),
                    )
                    if messages:
                        last_msg = messages[-1]
                        preview = last_msg["content"][:200]
                        if len(last_msg["content"]) > 200:
                            preview += "..."
                        completed.append({
                            "chat_id": chat["chat_id"],
                            "name": chat["name"],
                            "last_message_preview": preview,
                        })
                except Exception:
                    pass

        return completed

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        try:
            resp = requests.request(
                method=method,
                url=f"{self.config.api_base_url}{path}",
                headers={"X-API-Key": self.config.api_key},
                json=data,
                timeout=60,
            )
        except requests.RequestException as e:
            raise APIError(0, f"Request failed: {e}")

        if resp.status_code == 402:
            raise PaymentRequiredError(
                subscription_url="https://cellcog.ai/billing",
                email=self.config.email or "unknown",
            )

        if resp.status_code == 401:
            raise AuthenticationError("Invalid or expired API key")

        if resp.status_code == 404:
            raise ChatNotFoundError(f"Chat not found: {path}")

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)

        return resp.json()
