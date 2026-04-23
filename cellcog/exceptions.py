"""
CellCog SDK Exceptions.

Custom exceptions for handling various error conditions when interacting with the CellCog API.
"""

from __future__ import annotations


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
        chat_mode: The chat mode that was attempted ('human_in_the_loop', 'agent_in_the_loop', or 'agent_team_max').
        chat_mode_display: Human-readable chat mode name ('Agent', 'Agent Team', or 'Agent Team Max').

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

        # Two-option recovery structure matching the gold standard
        lines.append("**Option 1 — Upgrade subscription (recommended, instant credits):**")
        lines.append(f"Manage subscription: {self.billing_url}")
        lines.append(
            "Upgrading gives instant prorated credits right now, plus more credits"
        )
        lines.append(
            "per dollar (100 cr/$1 vs 90 cr/$1 for top-ups). Best if usage has"
        )
        lines.append("permanently increased.\n")

        if self.top_ups:
            lines.append("**Option 2 — One-time top-up (instant credits):**")
            for option in self.top_ups:
                lines.append(
                    f"  • ${option['amount_dollars']} top-up "
                    f"({option['credits']} credits): {option['url']}"
                )
            lines.append(
                "Top-ups are best for temporary spikes in usage. Credits are added instantly"
            )
            lines.append("but cost slightly more per credit than a subscription.\n")

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


class MaxConcurrencyError(CellCogError):
    """
    Raised when user has too many parallel chats for their credit balance.

    CellCog limits parallel chats to ensure reliable performance for all users.
    Each 500 credits of effective balance allows 1 parallel chat slot
    (minimum 1, maximum 8).

    This is NOT a payment error — it's a temporary condition. Either:
    1. Wait for a running chat to finish (frees up a slot)
    2. Add credits to unlock more parallel slots

    Attributes:
        operating_count: Number of currently running chats.
        max_parallel: Maximum parallel chats allowed with current balance.
        effective_balance: User's current effective credit balance.
        credits_per_slot: Credits required per additional parallel chat.
    """

    def __init__(
        self,
        message: str,
        operating_count: int = 0,
        max_parallel: int = 0,
        effective_balance: int = 0,
        credits_per_slot: int = 500,
    ):
        self.operating_count = operating_count
        self.max_parallel = max_parallel
        self.effective_balance = effective_balance
        self.credits_per_slot = credits_per_slot

        # Build agent-friendly message with context
        lines = [message, ""]
        lines.append(
            f"Concurrency: {operating_count} running / {max_parallel} max "
            f"(balance: {effective_balance} credits, {credits_per_slot} credits per slot)"
        )
        lines.append("")
        lines.append("Options:")
        lines.append("  1. Wait for a running chat to finish")
        lines.append(f"  2. Add credits ({credits_per_slot}+ credits unlocks another slot)")
        lines.append("")
        lines.append(
            "This limit ensures reliable compute for all users. "
            "It is NOT a payment error — do not present payment links."
        )

        super().__init__("\n".join(lines))


class SDKUpgradeRequiredError(CellCogError):
    """Raised when Python SDK version is too old and backend requires upgrade."""
    
    def __init__(self, current_version: str, minimum_version: str, upgrade_instructions: str):
        self.current_version = current_version
        self.minimum_version = minimum_version
        self.upgrade_instructions = upgrade_instructions
        super().__init__(
            f"SDK upgrade required: v{current_version} → v{minimum_version} or later\n\n{upgrade_instructions}"
        )


class GatewayConfigError(CellCogError):
    """
    Raised when the OpenClaw Gateway blocks the session tools CellCog's
    notify mode needs to deliver results back to your session.

    Notify mode (fire-and-forget) requires OpenClaw's sessions_send tool
    to deliver task completions back to your agent session. On OpenClaw
    2026.4+, sessions_send is disabled by default to enforce strict
    per-user session isolation (a security hardening introduced after
    CVE-2026-27004, which affected shared-agent deployments).

    The error message walks the caller through two clear options:
    enable the tool (for single-user environments), or switch to wait
    mode (works on any gateway without config changes).

    Attributes:
        gateway_url: The Gateway URL that was checked.
    """

    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url

        super().__init__(
            "CellCog notify mode cannot deliver results on this OpenClaw gateway.\n"
            "\n"
            "WHY YOU'RE SEEING THIS:\n"
            "Notify mode (fire-and-forget) delivers CellCog's results back to your\n"
            "OpenClaw session via the gateway's session-messaging tool. OpenClaw 2026.4+\n"
            "disables that tool by default to enforce strict per-user session isolation\n"
            "(a security hardening introduced after CVE-2026-27004, which affected\n"
            "shared-agent deployments). Until it's re-enabled on this gateway, notify\n"
            "mode's completion delivery cannot reach your session.\n"
            "\n"
            "If you're running in a single-user environment, it's safe to re-enable.\n"
            "If you're in a shared or multi-user environment, do not re-enable — use\n"
            "wait mode instead.\n"
            "\n"
            "YOU HAVE TWO OPTIONS:\n"
            "\n"
            "Option 1 — Re-enable the session-messaging tool on your gateway\n"
            "(single-user environments only):\n"
            "\n"
            "  The OpenClaw command for this has historically looked like:\n"
            "    openclaw config set gateway.tools.allow \\\n"
            "      '[\"sessions_send\", \"sessions_list\"]'\n"
            "\n"
            "  This command may change across OpenClaw versions. The above is shown\n"
            "  as a starting point only — check your installed OpenClaw version's\n"
            "  current CLI documentation for the correct command to allow the\n"
            "  sessions_send and sessions_list tools, then restart your gateway and\n"
            "  retry this call.\n"
            "\n"
            "Option 2 — Use wait mode instead (no gateway changes, works everywhere):\n"
            "\n"
            "  Notify mode is an opt-in optimization for keeping your agent free during\n"
            "  long CellCog tasks. Wait mode has identical functionality — it just\n"
            "  blocks until the result is ready. You can get the same agent-free\n"
            "  behavior by running the wait-mode call inside a background thread or\n"
            "  asyncio task.\n"
            "\n"
            "  Sync example (drop notify_session_key):\n"
            "    result = client.create_chat(\n"
            "        prompt='your task',\n"
            "        task_label='my-task',\n"
            "        chat_mode='agent',\n"
            "    )\n"
            "    # Blocks until done, returns the full result.\n"
            "\n"
            "  Background-thread example (agent stays free):\n"
            "    import threading\n"
            "    def _run_cellcog():\n"
            "        r = client.create_chat(prompt='your task', task_label='my-task')\n"
            "        # handle r however you want — print, queue, callback, etc.\n"
            "    threading.Thread(target=_run_cellcog, daemon=True).start()\n"
            "\n"
            "Option 3 — Fallback to the web:\n"
            "  Every CellCog chat is also viewable at https://cellcog.ai regardless of\n"
            "  gateway configuration. You can continue the conversation from the web UI.\n"
            "\n"
            f"(Gateway checked: {gateway_url})"
        )
