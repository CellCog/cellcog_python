"""
CellCog SDK Basic Usage Example

This example demonstrates the core functionality of the CellCog SDK.
Requires: export CELLCOG_API_KEY="sk_..."
"""

from cellcog import CellCogClient, PaymentRequiredError, ConfigurationError


def main():
    client = CellCogClient()

    # Check if configured
    status = client.get_account_status()
    if not status["configured"]:
        print("CellCog not configured.")
        print('Set env var: export CELLCOG_API_KEY="sk_..."')
        print("Get your key from: https://cellcog.ai/profile?tab=api-keys")
        return

    # Fire-and-forget: returns immediately
    try:
        result = client.create_chat(
            prompt="What are the key differences between Python and JavaScript?",
            notify_session_key="agent:main:main",
            task_label="python-vs-js",
            chat_mode="agent"
        )

        print(f"Chat created: {result['chat_id']}")
        print(f"Status: {result['status']}")
        print("Results will be delivered to your session automatically.")

    except PaymentRequiredError as e:
        print(f"Payment required! Visit {e.subscription_url} to add credits")

    except ConfigurationError as e:
        print(f"Configuration error: {e}")


if __name__ == "__main__":
    main()
