# CellCog Python SDK

CellCog: Any-to-Any for Agents - Your sub-agent for quality work.

Create complex multimodal content through AI orchestration - research reports, interactive apps, videos, images, and documents.

## Installation

```bash
pip install cellcog
```

## Quick Start

```python
from cellcog import CellCogClient

client = CellCogClient()

# Check if configured
status = client.get_account_status()
if not status["configured"]:
    print("Configure CellCog by adding your API key to ~/.openclaw/cellcog.json")
    print("Get your key from: https://cellcog.ai/profile?tab=api-keys")
else:
    # Create chat and stream responses
    result = client.create_chat_and_stream(
        prompt="Research Tesla Q4 2025 earnings",
        session_id="your-session-id",
        main_agent=False,
        timeout_seconds=3600
    )
    
    print(f"Completed: {result['status']}")
```

## Configuration

Create `~/.openclaw/cellcog.json` with your API key:

```json
{
  "api_key": "sk_..."
}
```

**Get your API key:**
1. Create account: https://cellcog.ai/signup
2. Add payment: https://cellcog.ai/profile?tab=billing
3. Get API key: https://cellcog.ai/profile?tab=api-keys

## Features

- **Research Reports**: Deep analysis with citations
- **Interactive Apps**: HTML dashboards and visualizations
- **Videos**: Marketing videos, explainers with AI voiceovers
- **Images**: Generated images, infographics, brand assets
- **Documents**: PDFs, presentations, spreadsheets

## File Handling

The SDK automatically handles file uploads and downloads.

### Send Files to CellCog

```python
# Files in SHOW_FILE tags are automatically uploaded
result = client.create_chat_and_stream(
    prompt='''
    Analyze this data:
    <SHOW_FILE>/home/user/data/sales.csv</SHOW_FILE>
    ''',
    session_id="your-session-id",
    main_agent=False
)
```

### Request Output at Specific Locations

```python
# Use GENERATE_FILE to specify output paths
result = client.create_chat_and_stream(
    prompt='''
    Create analysis report:
    <GENERATE_FILE>/home/user/reports/analysis.pdf</GENERATE_FILE>
    ''',
    session_id="your-session-id",
    main_agent=False
)

# Files auto-download to specified paths
# Or to ~/.cellcog/chats/{chat_id}/... if no GENERATE_FILE specified
```

## API Reference

### Primary Methods

```python
# Create chat and stream responses
result = client.create_chat_and_stream(
    prompt="Your task...",
    session_id="your-session-id",
    main_agent=False,
    chat_mode="agent team",  # or "agent"
    timeout_seconds=3600
)

# Send message and stream responses
result = client.send_message_and_stream(
    chat_id="abc123",
    message="Your message...",
    session_id="your-session-id",
    main_agent=False
)

# Check configuration
status = client.get_account_status()
# {"configured": bool, "email": str | None, "api_key_prefix": str | None}
```

### Advanced Methods

```python
# Stream without sending new message
client.stream_unseen_messages_and_wait_for_completion(chat_id, session_id, main_agent)

# Get full history (fallback for memory recovery)
history = client.get_history(chat_id, session_id)

# List recent chats
chats = client.list_chats(limit=20)

# Check for completed chats
completed = client.check_pending_chats()
```

## Error Handling

```python
from cellcog import (
    CellCogClient,
    PaymentRequiredError,
    ConfigurationError,
)

client = CellCogClient()

try:
    result = client.create_chat_and_stream(...)
except PaymentRequiredError as e:
    print(f"Add credits at: {e.subscription_url}")
except ConfigurationError as e:
    print("Add API key to ~/.openclaw/cellcog.json")
```

## OpenClaw Integration

This SDK is designed for [OpenClaw](https://openclaw.ai) agents.

See [SKILL.md](https://github.com/CellCog/cellcog_python/blob/main/SKILL.md) for complete integration guide.

## Links

- [CellCog Website](https://cellcog.ai)
- [GitHub Repository](https://github.com/CellCog/cellcog_python)
- [Get API Key](https://cellcog.ai/profile?tab=api-keys)

## License

MIT License - see [LICENSE](LICENSE) for details.
