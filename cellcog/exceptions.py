"""
CellCog SDK Exceptions.

Custom exceptions for handling various error conditions when interacting with the CellCog API.
"""


class CellCogError(Exception):
    """Base exception for all CellCog SDK errors."""

    pass


class AuthenticationError(CellCogError):
    """Raised when authentication fails (invalid API key, expired token, etc.)."""

    pass


class PaymentRequiredError(CellCogError):
    """
    Raised when the user's account needs credits to proceed.

    The subscription_url can be sent to the human to add credits.
    """

    def __init__(self, subscription_url: str, email: str):
        self.subscription_url = subscription_url
        self.email = email
        super().__init__(
            f"Payment required. Send this URL to your human to add credits:\n"
            f"  {subscription_url}\n"
            f"  Account: {email}"
        )


class ChatNotFoundError(CellCogError):
    """Raised when a chat ID is not found or user doesn't have access."""

    pass


class FileUploadError(CellCogError):
    """Raised when file upload fails."""

    pass


class FileDownloadError(CellCogError):
    """Raised when file download fails."""

    pass


class ConfigurationError(CellCogError):
    """Raised when SDK is not properly configured (missing API key, etc.)."""

    pass


class APIError(CellCogError):
    """Raised when the CellCog API returns an unexpected error."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error ({status_code}): {message}")
