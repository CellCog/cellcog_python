"""
Basic CellCog SDK Usage Example

This example demonstrates the core functionality of the CellCog SDK.
"""

from cellcog import CellCogClient, PaymentRequiredError, ConfigurationError


def main():
    # Initialize client
    client = CellCogClient()

    # Check if already configured
    status = client.get_account_status()
    if not status["configured"]:
        print("Setting up account...")
        # Replace with your email and password
        client.setup_account("your.email@example.com", "your-password")
        print(f"Account configured: {client.get_account_status()}")

    # Create a simple chat
    print("\nCreating chat...")
    try:
        result = client.create_chat(
            "What are the key differences between Python and JavaScript? "
            "Provide a brief comparison table."
        )
        print(f"Chat created: {result['chat_id']}")
        print(f"Status: {result['status']}")

        # Wait for completion
        print("\nWaiting for completion...")
        final = client.wait_for_completion(
            result["chat_id"],
            timeout_seconds=120,
            poll_interval=5,
        )

        if final["status"] == "completed":
            print("\n" + "=" * 50)
            print("RESULT:")
            print("=" * 50)
            for msg in final["history"]["messages"]:
                print(f"\n[{msg['from'].upper()}]:")
                print(msg["content"][:500])
                if len(msg["content"]) > 500:
                    print("... (truncated)")
        else:
            print(f"Chat did not complete: {final['status']}")
            if final.get("error_type"):
                print(f"Error: {final['error_type']}")

    except PaymentRequiredError as e:
        print(f"\nPayment required!")
        print(f"Visit {e.subscription_url} to add credits")
        print(f"Account: {e.email}")

    except ConfigurationError as e:
        print(f"\nConfiguration error: {e}")
        print("Run setup_account() first or set CELLCOG_API_KEY")


if __name__ == "__main__":
    main()
