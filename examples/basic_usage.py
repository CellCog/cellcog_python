"""
CellCog SDK Basic Usage Example

This example demonstrates the core functionality of the CellCog SDK.
"""

from cellcog import CellCogClient, PaymentRequiredError, ConfigurationError


def main():
    # Initialize client
    client = CellCogClient()

    # Check if already configured
    status = client.get_account_status()
    if not status["configured"]:
        print("CellCog not configured.")
        print("Add your API key to ~/.openclaw/cellcog.json:")
        print('{"api_key": "sk_..."}')
        print("\nGet your key from: https://cellcog.ai/profile?tab=api-keys")
        return

    # Simple example with streaming
    print("\nExample: Simple query with streaming")
    print("-" * 50)

    try:
        # Create chat and stream responses
        result = client.create_chat_and_stream(
            prompt="What are the key differences between Python and JavaScript?",
            session_id="example-session",
            main_agent=False,
            chat_mode="agent",
            timeout_seconds=120
        )

        print(f"\nCompleted with status: {result['status']}")
        print(f"Messages delivered: {result['messages_delivered']}")

    except PaymentRequiredError as e:
        print(f"\nPayment required!")
        print(f"Visit {e.subscription_url} to add credits")

    except ConfigurationError as e:
        print(f"\nConfiguration error: {e}")


if __name__ == "__main__":
    main()
