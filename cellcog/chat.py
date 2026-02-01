"""
CellCog SDK Chat Operations.

Handles chat creation, messaging, status, and history retrieval.
"""

import time
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
    - Polling for completion
    """

    def __init__(self, config: Config, file_processor: FileProcessor):
        self.config = config
        self.files = file_processor

    def create(self, prompt: str, project_id: Optional[str] = None) -> dict:
        """
        Create a new CellCog chat.

        Local files in SHOW_FILE tags are automatically uploaded.
        GENERATE_FILE tags are passed through for CellCog agent.

        Args:
            prompt: Initial prompt (can include SHOW_FILE, GENERATE_FILE tags)
            project_id: Optional CellCog project ID

        Returns:
            {
                "chat_id": str,
                "status": "processing" | "ready",
                "uploaded_files": [{"local": str, "blob": str}]
            }

        Raises:
            PaymentRequiredError: If account needs credits
            AuthenticationError: If API key is invalid
            APIError: For other API errors
        """
        self.config.require_configured()

        # Transform outgoing message - upload local files
        transformed, uploaded = self.files.transform_outgoing(prompt)

        # Create chat
        data = {"message": transformed}
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
        Send a message to an existing chat.

        Args:
            chat_id: The chat to send to
            message: Message content (can include SHOW_FILE, GENERATE_FILE tags)

        Returns:
            {"status": "sent", "uploaded_files": [...]}

        Raises:
            ChatNotFoundError: If chat doesn't exist
            PaymentRequiredError: If account needs credits
            AuthenticationError: If API key is invalid
        """
        self.config.require_configured()

        # Transform outgoing message - upload local files
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
                "error_type": str | None  # "security_threat" or "out_of_memory"
            }

        Raises:
            ChatNotFoundError: If chat doesn't exist
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

    def get_history(self, chat_id: str) -> dict:
        """
        Get chat history with all files downloaded and paths resolved.

        All SHOW_FILE tags in returned messages contain local paths.
        Files from CellCog are automatically downloaded.

        Args:
            chat_id: The chat to retrieve

        Returns:
            {
                "chat_id": str,
                "messages": [
                    {"from": "user"|"cellcog", "content": str, "created_at": str}
                ],
                "created_at": str,
                "is_complete": bool  # False if messages still queued
            }

        Raises:
            ChatNotFoundError: If chat doesn't exist
        """
        self.config.require_configured()

        resp = self._request("GET", f"/cellcog/chat/{chat_id}/history")

        # Transform incoming messages - download files, replace blob_names with local paths
        messages = self.files.transform_incoming_history(
            resp["messages"],
            resp.get("blob_name_to_url", {}),
            chat_id,
        )

        return {
            "chat_id": resp["chat_id"],
            "messages": messages,
            "created_at": resp["createdAt"],
            "is_complete": not resp.get("letterbox_messages"),
        }

    def list_chats(self, limit: int = 20) -> list:
        """
        List recent chats.

        Args:
            limit: Maximum number of chats to return (1-100)

        Returns:
            [
                {
                    "chat_id": str,
                    "name": str,
                    "status": "processing" | "ready",
                    "created_at": str | None,
                    "updated_at": str | None
                }
            ]
        """
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

    def wait_for_completion(
        self,
        chat_id: str,
        timeout_seconds: int = 600,
        poll_interval: int = 10,
    ) -> dict:
        """
        Poll until chat completes or timeout.

        Args:
            chat_id: The chat to wait for
            timeout_seconds: Max wait time (default 10 minutes)
            poll_interval: Seconds between status checks (default 10)

        Returns:
            {
                "status": "completed" | "timeout" | "error",
                "history": dict | None,  # Same as get_history() if completed
                "elapsed_seconds": float,
                "error_type": str | None  # If status is "error"
            }
        """
        start = time.time()

        while time.time() - start < timeout_seconds:
            status = self.get_status(chat_id)

            if status["error_type"]:
                return {
                    "status": "error",
                    "history": None,
                    "elapsed_seconds": time.time() - start,
                    "error_type": status["error_type"],
                }

            if not status["is_operating"]:
                return {
                    "status": "completed",
                    "history": self.get_history(chat_id),
                    "elapsed_seconds": time.time() - start,
                    "error_type": None,
                }

            time.sleep(poll_interval)

        return {
            "status": "timeout",
            "history": None,
            "elapsed_seconds": timeout_seconds,
            "error_type": None,
        }

    def check_pending(self) -> list:
        """
        Check all user's chats and return recently completed ones.

        Useful for OpenClaw's heartbeat loop to find completed work.

        Returns:
            [
                {
                    "chat_id": str,
                    "name": str,
                    "last_message_preview": str,  # Truncated last message
                }
            ]
        """
        self.config.require_configured()

        chats = self.list_chats(limit=20)
        completed = []

        for chat in chats:
            if chat["status"] == "ready":
                # Get last message preview
                try:
                    history = self.get_history(chat["chat_id"])
                    if history["messages"]:
                        last_msg = history["messages"][-1]
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
                    # Skip if we can't get history
                    pass

        return completed

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        """
        Make API request with error handling.

        Args:
            method: HTTP method
            path: API path (e.g., "/cellcog/chat/new")
            data: Optional request body

        Returns:
            Response JSON

        Raises:
            PaymentRequiredError: If 402 response
            AuthenticationError: If 401 response
            ChatNotFoundError: If 404 response
            APIError: For other errors
        """
        try:
            resp = requests.request(
                method=method,
                url=f"{self.config.api_base_url}{path}",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
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
