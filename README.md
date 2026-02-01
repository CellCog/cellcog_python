# CellCog Python SDK

Create complex multimodal content through AI orchestration - research reports, interactive apps, videos, images, and documents.

## Installation

```bash
pip install cellcog
```

## Quick Start

```python
from cellcog import CellCogClient

client = CellCogClient()

# First-time setup (creates account, stores API key)
client.setup_account("your.email@example.com", "your-password")

# Create a chat
result = client.create_chat("Research Tesla Q4 2025 earnings and create an analysis report")
print(f"Chat ID: {result['chat_id']}")

# Wait for completion (typically 30 seconds to several minutes)
final = client.wait_for_completion(result["chat_id"])

# View results
if final["status"] == "completed":
    for msg in final["history"]["messages"]:
        print(f"{msg['from']}: {msg['content'][:200]}...")
```

## Features

- **Research Reports**: Deep analysis with citations and insights
- **Interactive Apps**: HTML dashboards and visualizations
- **Videos**: Marketing videos, explainers with AI voiceovers
- **Images**: Generated images, infographics, brand assets
- **Documents**: PDFs, presentations, spreadsheets

## File Handling

The SDK automatically handles file uploads and downloads. You only work with local paths.

### Send Files to CellCog

```python
# Local files in SHOW_FILE tags are automatically uploaded
result = client.create_chat('''
    Analyze this financial data:
    <SHOW_FILE>/home/user/data/q4_financials.xlsx</SHOW_FILE>
    
    Compare with industry benchmarks.
''')
```

### Request Output at Specific Locations

```python
# Use GENERATE_FILE to specify where you want output files
result = client.create_chat('''
    Analyze the data:
    <SHOW_FILE>/home/user/data/sales.csv</SHOW_FILE>
    
    Create:
    1. PDF report: <GENERATE_FILE>/home/user/reports/analysis.pdf</GENERATE_FILE>
    2. Chart image: <GENERATE_FILE>/home/user/images/chart.png</GENERATE_FILE>
''')

# Wait for completion - files are automatically downloaded
final = client.wait_for_completion(result["chat_id"])

# Files now exist at the paths you specified!
```

## Configuration

The SDK stores credentials in `~/.openclaw/cellcog.json` by default.

You can also use environment variables:

```bash
export CELLCOG_API_KEY="sk_..."
export CELLCOG_EMAIL="your@email.com"
```

## API Reference

### CellCogClient

```python
client = CellCogClient(config_path=None)  # Optional custom config path
```

#### Account Management

```python
# Create account or sign in
client.setup_account(email, password)

# Check configuration status
status = client.get_account_status()
# {"configured": True, "email": "...", "api_key_prefix": "sk_..."}
```

#### Chat Operations

```python
# Create a new chat
result = client.create_chat(prompt, project_id=None)
# {"chat_id": "...", "status": "processing", "uploaded_files": [...]}

# Send follow-up message
client.send_message(chat_id, message)

# Check status (non-blocking)
status = client.get_status(chat_id)
# {"status": "processing"|"ready"|"error", "name": "...", "is_operating": bool}

# Get full history with files downloaded
history = client.get_history(chat_id)
# {"chat_id": "...", "messages": [...], "is_complete": bool}

# List recent chats
chats = client.list_chats(limit=20)

# Wait for completion (blocking)
final = client.wait_for_completion(chat_id, timeout_seconds=600, poll_interval=10)
# {"status": "completed"|"timeout"|"error", "history": {...}}

# Check for completed chats (for heartbeat loops)
completed = client.check_pending_chats()
```

## Error Handling

```python
from cellcog import (
    CellCogClient,
    PaymentRequiredError,
    AuthenticationError,
    ConfigurationError,
)

client = CellCogClient()

try:
    result = client.create_chat("Create a marketing video...")
except PaymentRequiredError as e:
    print(f"Need credits. Visit: {e.subscription_url}")
    print(f"Account: {e.email}")
except AuthenticationError:
    print("Invalid API key - run setup_account() or check CELLCOG_API_KEY")
except ConfigurationError:
    print("SDK not configured - run setup_account() first")
```

## OpenClaw Integration

This SDK is designed to work seamlessly with [OpenClaw](https://openclaw.ai) as a skill.

See the [OpenClaw skill documentation](https://github.com/CellCog/cellcog_python/blob/main/SKILL.md) for integration details.

## Links

- [CellCog Website](https://cellcog.ai)
- [API Documentation](https://cellcog.ai/developer/docs)
- [GitHub Repository](https://github.com/CellCog/cellcog_python)

## License

MIT License - see [LICENSE](LICENSE) for details.
