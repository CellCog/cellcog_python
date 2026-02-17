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

    Attributes:
        top_ups: List of top-up options with direct Stripe Payment Link URLs.
                 Each: {"amount_dollars": int, "credits": int, "url": str}
        billing_url: URL to CellCog billing page for subscription management.
        subscription_url: Alias for billing_url (backward compatibility).
        email: User's email address.
        min_credits_required: Minimum credits required for the attempted chat mode.
        current_balance: User's current effective credit balance.
        chat_mode: The chat mode that was attempted ('human_in_the_loop' or 'agent_in_the_loop').
        chat_mode_display: Human-readable chat mode name ('Agent' or 'Agent-Team').

    The top-up URLs are direct Stripe payment links — the human clicks, pays,
    and credits are added automatically. No login required.
    """

    def __init__(
        self,
        subscription_url: str,
        email: str,
        top_ups: list | None = None,
        billing_url: str | None = None,
        min_credits_required: int | None = None,
        current_balance: int | None = None,
        chat_mode: str | None = None,
        chat_mode_display: str | None = None,
    ):
        self.top_ups = top_ups or []
        self.billing_url = billing_url or subscription_url
        self.subscription_url = self.billing_url  # backward compatibility
        self.email = email
        self.min_credits_required = min_credits_required
        self.current_balance = current_balance
        self.chat_mode = chat_mode
        self.chat_mode_display = chat_mode_display

        # Build agent-friendly message with actionable links
        lines = ["Payment required. Your CellCog account needs credits to proceed.\n"]

        if self.min_credits_required is not None and self.chat_mode_display:
            lines.append(
                f"{self.chat_mode_display} mode requires at least "
                f"{self.min_credits_required} credits."
            )
            if self.current_balance is not None:
                lines.append(f"Your current balance: {self.current_balance} credits.\n")

        if self.top_ups:
            lines.append("Send one of these links to your human for instant credits:")
            for option in self.top_ups:
                lines.append(
                    f"  • ${option['amount_dollars']} top-up "
                    f"({option['credits']} credits): {option['url']}"
                )
            lines.append("")

        lines.append(f"Manage subscription: {self.billing_url}")
        lines.append(f"Account: {email}")

        super().__init__("\n".join(lines))


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


class AccountDisabledError(CellCogError):
    """
    Raised when the user's CellCog account is disabled.

    Provides agent-friendly guidance with clear action steps for the human.
    """

    def __init__(self, error_type: str, detail: str, action_url: str, email: str):
        self.error_type = error_type
        self.action_url = action_url
        self.email = email

        # Agent-friendly messages with clear action steps
        if error_type == "email_not_verified":
            self.human_action = (
                f"Your CellCog account ({email}) needs email verification.\n\n"
                f"Please:\n"
                f"1. Go to {action_url}\n"
                f"2. You'll see a 'Verify your email' screen\n"
                f"3. Click 'Resend Verification Email' if needed\n"
                f"4. Check your inbox and click the verification link\n"
                f"5. Once verified, retry this request"
            )
        elif error_type == "account_security_flagged":
            self.human_action = (
                f"Your CellCog account ({email}) has been flagged for security review.\n\n"
                f"This is an automated process and can sometimes be incorrect.\n"
                f"Please contact CellCog support: support@cellcog.ai"
            )
        else:
            self.human_action = (
                f"Your CellCog account ({email}) is disabled.\n"
                f"Please contact support: support@cellcog.ai"
            )

        super().__init__(self.human_action)


class SDKUpgradeRequiredError(CellCogError):
    """Raised when Python SDK version is too old and backend requires upgrade."""
    
    def __init__(self, current_version: str, minimum_version: str, upgrade_instructions: str):
        self.current_version = current_version
        self.minimum_version = minimum_version
        self.upgrade_instructions = upgrade_instructions
        super().__init__(
            f"SDK upgrade required: v{current_version} → v{minimum_version} or later\n\n{upgrade_instructions}"
        )
