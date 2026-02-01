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

    # Wait for completion
    final = client.wait_for_completion(result["chat_id"])

    # View results
    for msg in final["history"]["messages"]:
        print(f"{msg['from']}: {msg['content'][:200]}")

File Handling:
    # Send local files
    client.create_chat('''
        Analyze this: <SHOW_FILE>/path/to/data.csv</SHOW_FILE>
    ''')

    # Request output at specific location
    client.create_chat('''
        Create report: <GENERATE_FILE>/path/to/output.pdf</GENERATE_FILE>
    ''')

    # Files are automatically uploaded/downloaded - you only see local paths

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

__version__ = "0.1.1"
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
