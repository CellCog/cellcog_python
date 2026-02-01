# CellCog

---
name: cellcog
description: Create complex multimodal content through deep AI research and orchestration - reports, apps, videos, images, documents
metadata:
  openclaw:
    requires:
      env: ["CELLCOG_API_KEY"]
      bins: ["python3"]
    primaryEnv: CELLCOG_API_KEY
    install: "pip install cellcog"
user-invocable: true
---

## What is CellCog?

CellCog is a multi-agent AI platform that creates complex outputs through deep research:

- **Research Reports**: Deep analysis with citations, charts, and insights
- **Interactive Apps**: HTML dashboards, calculators, visualizations
- **Videos**: Marketing videos, explainers with AI avatars and voiceovers
- **Images**: Generated images, infographics, brand assets
- **Documents**: PDFs, presentations, spreadsheets

## Setup

### First Time (Create Account)

```python
from cellcog import CellCogClient

client = CellCogClient()
client.setup_account("your.email@example.com", "your-password")
# API key automatically stored in ~/.openclaw/cellcog.json
```

### Verify Setup

```python
status = client.get_account_status()
print(f"Configured: {status['configured']}, Email: {status['email']}")
```

## Basic Usage

### Create a Chat

```python
from cellcog import CellCogClient

client = CellCogClient()

# Simple prompt
result = client.create_chat("Research Tesla's Q4 2025 earnings and create an analysis report")
print(f"Chat ID: {result['chat_id']}, Status: {result['status']}")
```

### Wait for Completion

```python
# Blocking wait (up to 10 minutes)
final = client.wait_for_completion(result["chat_id"])

if final["status"] == "completed":
    for msg in final["history"]["messages"]:
        print(f"{msg['from']}: {msg['content'][:200]}...")
```

### Check Status (Non-blocking)

```python
status = client.get_status(chat_id)
if status["status"] == "ready":
    history = client.get_history(chat_id)
```

## File Input/Output

### Send Local Files to CellCog

Use `<SHOW_FILE>` tags with local paths - they're automatically uploaded:

```python
result = client.create_chat("""
Analyze this financial data:
<SHOW_FILE>/home/user/data/q4_financials.xlsx</SHOW_FILE>

And compare with industry benchmarks.
""")
```

### Request Files at Specific Locations

Use `<GENERATE_FILE>` tags to specify where you want output files:

```python
result = client.create_chat("""
Analyze the attached data:
<SHOW_FILE>/home/user/data/sales.csv</SHOW_FILE>

Generate:
1. Analysis PDF: <GENERATE_FILE>/home/user/reports/analysis.pdf</GENERATE_FILE>
2. Chart: <GENERATE_FILE>/home/user/images/sales_chart.png</GENERATE_FILE>
""")

# Wait for completion - files automatically downloaded to specified paths
final = client.wait_for_completion(result["chat_id"])
# Files now exist at /home/user/reports/analysis.pdf and /home/user/images/sales_chart.png
```

## Handling Payment Required (402)

If the CellCog account needs credits:

```python
from cellcog import CellCogClient, PaymentRequiredError

client = CellCogClient()

try:
    result = client.create_chat("Create a marketing video...")
except PaymentRequiredError as e:
    # Send to human
    print(f"CellCog needs credits. Tell your human to visit: {e.subscription_url}")
    print(f"Account: {e.email}")
    # Wait for them to add credits, then retry
```

## Examples

**Research & Report:**
> "Research the top 5 CRM tools for small businesses. Compare features, pricing, and user reviews. Create a detailed comparison report with recommendation."

**Data Analysis:**
> "Analyze this CSV <SHOW_FILE>/data/metrics.csv</SHOW_FILE> and create an interactive dashboard showing trends and anomalies."

**Video Creation:**
> "Create a 30-second product demo video for a todo app. Professional voiceover, screen recordings, and upbeat background music."

**Document Generation:**
> "Create a professional resume PDF for a software engineer with 5 years experience in Python and cloud infrastructure."

## API Reference

### CellCogClient Methods

| Method | Description |
|--------|-------------|
| `setup_account(email, password)` | Create account and store API key |
| `get_account_status()` | Check if configured |
| `create_chat(prompt, project_id=None)` | Start new chat |
| `send_message(chat_id, message)` | Send follow-up |
| `get_status(chat_id)` | Check if processing |
| `get_history(chat_id)` | Get messages and files |
| `list_chats(limit=20)` | List recent chats |
| `wait_for_completion(chat_id, timeout=600)` | Block until done |
| `check_pending_chats()` | Find completed chats |

## Tips

- CellCog chats typically take 30 seconds to several minutes depending on complexity
- Generated files are automatically downloaded when you call `get_history()` or `wait_for_completion()`
- Use `<GENERATE_FILE>` to control exactly where output files are saved
- For long-running tasks, use `check_pending_chats()` in your heartbeat loop
