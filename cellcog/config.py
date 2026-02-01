"""
CellCog SDK Configuration.

Handles credential storage and configuration loading.
"""

import json
import os
from pathlib import Path
from typing import Optional

from .exceptions import ConfigurationError


class Config:
    """
    Configuration manager for CellCog SDK.

    Stores and retrieves API credentials from a JSON file.
    Default location: ~/.openclaw/cellcog.json

    Can also read from environment variables:
    - CELLCOG_API_KEY
    - CELLCOG_EMAIL
    """

    DEFAULT_CONFIG_PATH = "~/.openclaw/cellcog.json"
    API_BASE_URL = "https://cellcog.ai/api"
    FIREBASE_API_KEY = "AIzaSyDrVR2rktn3xPbThNJNDf6mZTtESF5XMgA"

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config file. Defaults to ~/.openclaw/cellcog.json
        """
        self.config_path = Path(config_path or self.DEFAULT_CONFIG_PATH).expanduser()
        self._config_data: dict = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file if it exists."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    self._config_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._config_data = {}

    def _save_config(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._config_data, f, indent=2)
        # Secure the file (readable only by owner)
        os.chmod(self.config_path, 0o600)

    @property
    def api_key(self) -> Optional[str]:
        """Get API key from environment or config file."""
        return os.environ.get("CELLCOG_API_KEY") or self._config_data.get("api_key")

    @api_key.setter
    def api_key(self, value: str) -> None:
        """Set API key in config file."""
        self._config_data["api_key"] = value
        self._save_config()

    @property
    def email(self) -> Optional[str]:
        """Get email from environment or config file."""
        return os.environ.get("CELLCOG_EMAIL") or self._config_data.get("email")

    @email.setter
    def email(self, value: str) -> None:
        """Set email in config file."""
        self._config_data["email"] = value
        self._save_config()

    @property
    def api_base_url(self) -> str:
        """Get API base URL."""
        return os.environ.get("CELLCOG_API_URL") or self.API_BASE_URL

    @property
    def is_configured(self) -> bool:
        """Check if SDK has valid configuration."""
        return bool(self.api_key)

    def require_configured(self) -> None:
        """Raise error if SDK is not configured."""
        if not self.is_configured:
            raise ConfigurationError(
                "CellCog SDK not configured. Either:\n"
                "  1. Run client.setup_account(email, password) to create an account\n"
                "  2. Set CELLCOG_API_KEY environment variable\n"
                "  3. Add api_key to ~/.openclaw/cellcog.json"
            )

    def clear(self) -> None:
        """Clear stored credentials."""
        self._config_data = {}
        if self.config_path.exists():
            self.config_path.unlink()
