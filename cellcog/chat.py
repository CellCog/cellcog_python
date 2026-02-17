"""
CellCog SDK Chat Operations.

Handles chat creation, messaging, status, and history retrieval.
"""

from pathlib import Path
from typing import Optional

import requests

from .config import Config
from .exceptions import (
    AccountDisabledError,
    APIError,
    AuthenticationError,
    ChatNotFoundError,
    PaymentRequiredError,
)
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

    def create(self, prompt: str, project_id: Optional[str] = None, chat_mode: str = "agent") -> dict:
        """
        Create a new CellCog chat (without streaming).

        Args:
            prompt: Initial prompt (can include SHOW_FILE tags for file uploads)
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

    def send_message(self, chat_id: str, message: str) -> dict:
        """
        Send a message to existing chat (without streaming).

        Args:
            chat_id: The chat to send to
            message: Message content (can include SHOW_FILE tags for file uploads)

        Returns:
            {"status": "sent", "uploaded_files": [...]}
        """
        self.config.require_configured()

        transformed, uploaded = self.files.transform_outgoing(message)
        self._request("POST", f"/cellcog/chat/{chat_id}/messages", {"message": transformed})

        return {"status": "sent", "uploaded_files": uploaded}

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
                        completed.append(
                            {
                                "chat_id": chat["chat_id"],
                                "name": chat["name"],
                                "last_message_preview": preview,
                            }
                        )
                except Exception:
                    pass

        return completed

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        try:
            resp = requests.request(
                method=method,
                url=f"{self.config.api_base_url}{path}",
                headers=self.config.get_request_headers(),
                json=data,
                timeout=60,
            )
        except requests.RequestException as e:
            raise APIError(0, f"Request failed: {e}")

        if resp.status_code == 402:
            # Parse structured 402 response with payment recovery options and credit context
            top_ups = []
            billing_url = "https://cellcog.ai/profile?tab=billing"
            min_credits_required = None
            current_balance = None
            chat_mode = None
            chat_mode_display = None
            try:
                error_data = resp.json()
                detail = error_data.get("detail", {})
                if isinstance(detail, dict):
                    payment_options = detail.get("payment_options", {})
                    top_ups = payment_options.get("top_ups", [])
                    billing_url = payment_options.get("billing_url", billing_url)
                    credit_context = detail.get("credit_context", {})
                    if credit_context:
                        min_credits_required = credit_context.get("min_credits_required")
                        current_balance = credit_context.get("current_balance")
                        chat_mode = credit_context.get("chat_mode")
                        chat_mode_display = credit_context.get("chat_mode_display")
            except (ValueError, KeyError, AttributeError):
                pass  # Fall back to defaults

            raise PaymentRequiredError(
                subscription_url=billing_url,
                email=self.config.email or "unknown",
                top_ups=top_ups,
                billing_url=billing_url,
                min_credits_required=min_credits_required,
                current_balance=current_balance,
                chat_mode=chat_mode,
                chat_mode_display=chat_mode_display,
            )

        if resp.status_code == 403:
            try:
                error_data = resp.json()
                error_type = error_data.get("error_type", "")
                if error_type in ("email_not_verified", "account_security_flagged", "account_disabled"):
                    raise AccountDisabledError(
                        error_type=error_type,
                        detail=error_data.get("detail", "Account disabled"),
                        action_url=error_data.get("action_url", "https://cellcog.ai"),
                        email=error_data.get("email", "unknown"),
                    )
            except (ValueError, KeyError):
                pass
            # Fall through to generic handler for non-account 403s

        if resp.status_code == 401:
            raise AuthenticationError("Invalid or expired API key")

        if resp.status_code == 404:
            raise ChatNotFoundError(f"Chat not found: {path}")

        if resp.status_code == 426:
            # SDK upgrade required
            try:
                error_data = resp.json()
                from .exceptions import SDKUpgradeRequiredError

                raise SDKUpgradeRequiredError(
                    current_version=error_data.get("current_version", "unknown"),
                    minimum_version=error_data.get("minimum_version", "unknown"),
                    upgrade_instructions=error_data.get(
                        "upgrade_instructions",
                        "Please upgrade your cellcog skill and SDK version mentioned in the updated skill",
                    ),
                )
            except ValueError:
                # JSON parsing failed
                raise APIError(426, "SDK upgrade required")

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)

        return resp.json()
