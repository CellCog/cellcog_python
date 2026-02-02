"""
CellCog Python SDK

Create complex multimodal content through AI orchestration - reports, apps, videos, images, documents.

Basic Usage:
    from cellcog import CellCogClient

    client = CellCogClient()

    # First-time setup
    client.setup_account("email@example.com", "password")

    # Create a chat
    result = client.create_chat("Research Tesla Q4 earnings and create an analysis report")
    chat_id = result["chat_id"]

    # Wait with streaming - messages print automatically
    client.wait_for_completion_with_streaming(chat_id)

    # Or wait without streaming - get history at end
    final = client.wait_for_completion(chat_id)
    for msg in final["history"]["messages"]:
        print(f"{msg['role']}: {msg['content'][:200]}")

File Handling:
    # Send local files
    client.create_chat('''
        Analyze this: <SHOW_FILE>/path/to/data.csv</SHOW_FILE>
    ''')

    # Request output at specific location
    client.create_chat('''
        Create report: <GENERATE_FILE>/path/to/output.pdf</GENERATE_FILE>
    ''')

    # Files without GENERATE_FILE auto-download to ~/.cellcog/chats/{chat_id}/...

For more information: https://cellcog.ai/developer/docs
"""

from .client import CellCogClient
from .exceptions import (
    APIError,
    AuthenticationError,
    CellCogError,
    ChatNotFoundError,
    ConfigurationError,
    FileDownloadError,
    FileUploadError,
    PaymentRequiredError,
)

__version__ = "0.1.7"
__all__ = [
    "CellCogClient",
    "CellCogError",
    "AuthenticationError",
    "PaymentRequiredError",
    "ChatNotFoundError",
    "FileUploadError",
    "FileDownloadError",
    "ConfigurationError",
    "APIError",
]
