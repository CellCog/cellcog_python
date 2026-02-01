"""
CellCog SDK Authentication.

Handles Firebase account creation and API key generation.
"""

import requests
from typing import Optional

from .config import Config
from .exceptions import AuthenticationError


class AuthManager:
    """
    Manages authentication for CellCog SDK.

    Handles:
    - Creating new accounts via Firebase REST API
    - Generating API keys
    - Storing credentials
    """

    FIREBASE_SIGNUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
    FIREBASE_SIGNIN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"

    def __init__(self, config: Config):
        self.config = config

    def setup_account(self, email: str, password: str) -> dict:
        """
        Create a new CellCog account and store API key.

        If account already exists, signs in instead.

        Args:
            email: Email for the account
            password: Password (min 6 characters for Firebase)

        Returns:
            {"status": "success", "email": str, "message": str}

        Raises:
            AuthenticationError: If account creation/signin fails
        """
        # Try to create new account first
        try:
            id_token = self._create_firebase_account(email, password)
        except AuthenticationError as e:
            if "EMAIL_EXISTS" in str(e):
                # Account exists, try to sign in
                id_token = self._signin_firebase(email, password)
            else:
                raise

        # Generate API key using the ID token
        api_key = self._generate_api_key(id_token)

        # Store credentials
        self.config.email = email
        self.config.api_key = api_key

        return {
            "status": "success",
            "email": email,
            "message": f"Account configured. API key stored in {self.config.config_path}",
        }

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

    def _create_firebase_account(self, email: str, password: str) -> str:
        """
        Create Firebase account using REST API.

        Returns:
            Firebase ID token for subsequent API calls

        Raises:
            AuthenticationError: If account creation fails
        """
        response = requests.post(
            f"{self.FIREBASE_SIGNUP_URL}?key={self.config.FIREBASE_API_KEY}",
            json={"email": email, "password": password, "returnSecureToken": True},
        )

        if response.status_code != 200:
            error = response.json().get("error", {})
            error_message = error.get("message", "Unknown error")
            raise AuthenticationError(f"Account creation failed: {error_message}")

        return response.json()["idToken"]

    def _signin_firebase(self, email: str, password: str) -> str:
        """
        Sign in to existing Firebase account.

        Returns:
            Firebase ID token

        Raises:
            AuthenticationError: If signin fails
        """
        response = requests.post(
            f"{self.FIREBASE_SIGNIN_URL}?key={self.config.FIREBASE_API_KEY}",
            json={"email": email, "password": password, "returnSecureToken": True},
        )

        if response.status_code != 200:
            error = response.json().get("error", {})
            error_message = error.get("message", "Unknown error")
            raise AuthenticationError(f"Sign in failed: {error_message}")

        return response.json()["idToken"]

    def _generate_api_key(self, id_token: str) -> str:
        """
        Generate CellCog API key using Firebase ID token.

        Args:
            id_token: Firebase ID token from signup/signin

        Returns:
            CellCog API key (sk_...)

        Raises:
            AuthenticationError: If API key generation fails
        """
        response = requests.post(
            f"{self.config.api_base_url}/cellcog/user/api-key/generate",
            headers={"Authorization": f"Bearer {id_token}"},
        )

        if response.status_code == 409:
            # User already has an API key - this is fine for SDK setup
            # We need to get the existing key or have user revoke it
            raise AuthenticationError(
                "Account already has an API key. Either:\n"
                "  1. Set CELLCOG_API_KEY environment variable with your existing key\n"
                "  2. Visit https://cellcog.ai/profile to view/revoke your key"
            )

        if response.status_code != 200:
            raise AuthenticationError(f"API key generation failed: {response.text}")

        return response.json()["api_key"]
