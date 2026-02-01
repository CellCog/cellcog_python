"""
CellCog SDK Main Client.

This is the primary interface for interacting with CellCog from OpenClaw or any Python environment.
"""

from typing import Optional

from .auth import AuthManager
from .chat import ChatManager
from .config import Config
from .files import FileProcessor


class CellCogClient:
    """
    Main client for interacting with CellCog.

    Provides a simple interface for:
    - Account setup and authentication
    - Creating and managing chats
    - Automatic file upload/download with path translation

    Usage:
        from cellcog import CellCogClient

        client = CellCogClient()

        # First-time setup (creates account and stores API key)
        client.setup_account("email@example.com", "password")

        # Create a chat
        result = client.create_chat("Research Tesla Q4 earnings...")

        # Wait for completion
        final = client.wait_for_completion(result["chat_id"])

        # All files automatically downloaded to specified paths
        print(final["history"]["messages"])

    File Handling:
        The SDK automatically handles file translation between local paths and CellCog storage.

        Outgoing (your messages):
            <SHOW_FILE>/local/path/file.csv</SHOW_FILE>
            → File uploaded, path tracked

        Outgoing (request output location):
            <GENERATE_FILE>/local/path/output.pdf</GENERATE_FILE>
            → Passed to CellCog agent as output hint

        Incoming (CellCog responses):
            Files automatically downloaded to the paths you specified
            All SHOW_FILE tags show local paths
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize CellCog client.

        Args:
            config_path: Path to config file. Defaults to ~/.openclaw/cellcog.json
                        Can also use CELLCOG_API_KEY environment variable.
        """
        self.config = Config(config_path)
        self._auth = AuthManager(self.config)
        self._files = FileProcessor(self.config)
        self._chat = ChatManager(self.config, self._files)

    # ==================== Account Setup ====================

    def setup_account(self, email: str, password: str) -> dict:
        """
        Create a new CellCog account or sign in to existing one.

        Generates an API key and stores it for future use.

        Args:
            email: Email for the account
            password: Password (min 6 characters)

        Returns:
            {
                "status": "success",
                "email": str,
                "message": str
            }

        Raises:
            AuthenticationError: If account creation/signin fails
        """
        return self._auth.setup_account(email, password)

    def get_account_status(self) -> dict:
        """
        Check if SDK is configured with valid credentials.

        Returns:
            {
                "configured": bool,
                "email": str | None,
                "api_key_prefix": str | None
            }
        """
        return self._auth.get_status()

    # ==================== Chat Operations ====================

    def create_chat(self, prompt: str, project_id: Optional[str] = None, chat_mode: str = "agent team") -> dict:
        """
        Create a new CellCog chat.

        Local files in <SHOW_FILE> tags are automatically uploaded.
        Use <GENERATE_FILE> to specify where you want output files.

        Args:
            prompt: Initial prompt. Can include:
                - <SHOW_FILE>/path/to/input.csv</SHOW_FILE> (uploaded automatically)
                - <GENERATE_FILE>/path/for/output.pdf</GENERATE_FILE> (output location hint)
            project_id: Optional CellCog project ID for context
            chat_mode: "agent team" (deep reasoning, multi-agent) or "agent" (single agent, faster)

        Returns:
            {
                "chat_id": str,
                "status": "processing" | "ready",
                "uploaded_files": [{"local": str, "blob": str}]
            }

        Raises:
            PaymentRequiredError: If account needs credits
            AuthenticationError: If API key is invalid
            ConfigurationError: If SDK not configured

        Example:
            result = client.create_chat('''
                Analyze this data:
                <SHOW_FILE>/home/user/data/sales.csv</SHOW_FILE>

                Create a PDF report:
                <GENERATE_FILE>/home/user/reports/analysis.pdf</GENERATE_FILE>
            ''')
        """
        return self._chat.create(prompt, project_id, chat_mode)

    def send_message(self, chat_id: str, message: str) -> dict:
        """
        Send a follow-up message to an existing chat.

        Args:
            chat_id: The chat to send to
            message: Message content (supports SHOW_FILE, GENERATE_FILE)

        Returns:
            {"status": "sent", "uploaded_files": [...]}
        """
        return self._chat.send_message(chat_id, message)

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
        return self._chat.get_status(chat_id)

    def get_history(self, chat_id: str) -> dict:
        """
        Get chat history with all files downloaded.

        Files from CellCog are automatically downloaded to the paths
        you specified with GENERATE_FILE, or to a default location.
        All SHOW_FILE tags in messages contain local paths.

        Args:
            chat_id: The chat to retrieve

        Returns:
            {
                "chat_id": str,
                "messages": [
                    {"from": "user"|"cellcog", "content": str, "created_at": str}
                ],
                "created_at": str,
                "is_complete": bool
            }
        """
        return self._chat.get_history(chat_id)

    def list_chats(self, limit: int = 20) -> list:
        """
        List recent chats.

        Args:
            limit: Maximum number of chats (1-100)

        Returns:
            [
                {
                    "chat_id": str,
                    "name": str,
                    "status": "processing" | "ready",
                    "created_at": str,
                    "updated_at": str
                }
            ]
        """
        return self._chat.list_chats(limit)

    def wait_for_completion(
        self,
        chat_id: str,
        timeout_seconds: int = 600,
        poll_interval: int = 10,
    ) -> dict:
        """
        Poll until chat completes or timeout.

        This is a blocking call that waits for CellCog to finish processing.
        Use for simple workflows where you want to wait for results.

        Args:
            chat_id: The chat to wait for
            timeout_seconds: Max wait time (default 10 minutes)
            poll_interval: Seconds between checks (default 10)

        Returns:
            {
                "status": "completed" | "timeout" | "error",
                "history": dict | None,  # Full history with downloaded files
                "elapsed_seconds": float,
                "error_type": str | None
            }

        Example:
            result = client.create_chat("Generate a marketing video...")
            final = client.wait_for_completion(result["chat_id"])

            if final["status"] == "completed":
                print(final["history"]["messages"][-1]["content"])
        """
        return self._chat.wait_for_completion(chat_id, timeout_seconds, poll_interval)

    def check_pending_chats(self) -> list:
        """
        Check all chats and return recently completed ones.

        Useful for OpenClaw's heartbeat loop to find completed work
        without blocking.

        Returns:
            [
                {
                    "chat_id": str,
                    "name": str,
                    "last_message_preview": str
                }
            ]
        """
        return self._chat.check_pending()
