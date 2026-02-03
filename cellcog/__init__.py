"""
CellCog Python SDK

CellCog: Any-to-Any for Agents

Your sub-agent for quality work. Create complex multimodal content through AI orchestration.

Basic Usage:
    from cellcog import CellCogClient

    client = CellCogClient()

    # Configure with API key from human
    client.set_api_key("sk_...")  # Get from https://cellcog.ai/profile?tab=api-keys
    
    # Create chat and stream - messages print automatically
    result = client.create_chat_and_stream(
        prompt="Research Tesla Q4 earnings",
        session_id="your-session-id",
        main_agent=False
    )

File Handling:
    # Send local files
    client.create_chat_and_stream(
        prompt='Analyze this: <SHOW_FILE>/path/to/data.csv</SHOW_FILE>',
        session_id="your-session-id",
        main_agent=False
    )

    # Request output at specific location
    client.create_chat_and_stream(
        prompt='Create report: <GENERATE_FILE>/path/to/output.pdf</GENERATE_FILE>',
        session_id="your-session-id",
        main_agent=False
    )

    # Files without GENERATE_FILE auto-download to ~/.cellcog/chats/{chat_id}/...
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

__version__ = "0.1.9"
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
