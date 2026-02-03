"""
CellCog SDK Authentication.

Handles authentication status checking.
"""

from .config import Config


class AuthManager:
    """
    Manages authentication for CellCog SDK.
    
    Simplified - only checks configuration status.
    API keys are managed via the CellCog web UI.
    """

    def __init__(self, config: Config):
        self.config = config

    def get_status(self) -> dict:
        """
        Get current authentication status.

        Returns:
            {
                "configured": bool,
                "email": str | None,
                "api_key_prefix": str | None  # e.g., "sk_..."
            }
        """
        api_key = self.config.api_key
        return {
            "configured": self.config.is_configured,
            "email": self.config.email,
            "api_key_prefix": f"{api_key[:6]}..." if api_key else None,
        }
