"""
CellCog Python SDK

CellCog: Any-to-Any for Agents

Your sub-agent for quality work. Create complex multimodal content through AI orchestration.

v3.0 - Fire-and-Forget Pattern:
    # Set env var: export CELLCOG_API_KEY="sk_..."
    from cellcog import CellCogClient

    client = CellCogClient()
    
    # Create chat - returns immediately
    result = client.create_chat(
        prompt="Research Tesla Q4 earnings",
        notify_session_key="agent:main:main",  # Your OpenClaw session
        task_label="tesla-research"
    )
    
    # Continue with other work...
    # You'll receive notification at your session when complete

File Handling:
    # Send local files
    client.create_chat(
        prompt='Analyze this: <SHOW_FILE>/path/to/data.csv</SHOW_FILE>',
        notify_session_key="agent:main:main",
        task_label="data-analysis"
    )

    # Generated files auto-download to ~/.cellcog/chats/{chat_id}/...
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
    SDKUpgradeRequiredError,
)

__version__ = "1.1.1"
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
    "SDKUpgradeRequiredError",
]
