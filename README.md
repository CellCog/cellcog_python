# CellCog Python SDK

**CellCog: Any-to-Any AI for Agents** — Your sub-agent for quality work.

When you need depth, accuracy, or complex deliverables — research reports, interactive apps, videos, images, podcasts, documents, spreadsheets, and more — use CellCog.

## Installation

```bash
pip install cellcog
```

## Quick Start

```bash
export CELLCOG_API_KEY="sk_..."  # Get from https://cellcog.ai/profile?tab=api-keys
```

**Any agent (blocks until done):**

```python
from cellcog import CellCogClient

client = CellCogClient(agent_provider="openclaw")

result = client.create_chat(
    prompt="Research quantum computing advances in 2026",
    task_label="quantum-research",
    chat_mode="agent",
)
# Blocks until done — result contains everything
print(result["message"])
```

**OpenClaw agents (fire-and-forget):**

```python
result = client.create_chat(
    prompt="Research quantum computing advances in 2026",
    notify_session_key="agent:main:main",  # OpenClaw session key
    task_label="quantum-research",
    chat_mode="agent",
)
# Returns immediately — daemon delivers results to your session
```

## How It Works

**Two delivery modes:**

- **Wait for Completion (default)** — Blocks until CellCog finishes and returns the full result. Works with any agent — OpenClaw, Claude Code, Cursor, or any Python environment.

- **Fire-and-Forget (OpenClaw)** — Returns immediately. A background daemon monitors via WebSocket and delivers results to your OpenClaw session when done. Requires `sessions_send` on OpenClaw Gateway.

All methods return the same unified shape:

```python
{
    "chat_id": str,
    "is_operating": bool,
    "status": str,         # "completed" | "tracking" | "timeout" | "operating"
    "message": str,        # Always print this in full
}
```

## Configuration

```bash
export CELLCOG_API_KEY="sk_..."
```

**Get your API key:**
1. Create account: https://cellcog.ai/signup
2. Add payment: https://cellcog.ai/profile?tab=billing
3. Get API key: https://cellcog.ai/profile?tab=api-keys

## API Reference

### Core Methods

```python
# Create chat — wait mode (default, universal)
result = client.create_chat(
    prompt="Your task...",
    task_label="my-task",
    chat_mode="agent",              # "agent" | "agent core" | "agent team" | "agent team max"
    timeout=1800,                   # 30 min default; use 3600 for complex jobs
)

# Create chat — notify mode (OpenClaw only)
result = client.create_chat(
    prompt="Your task...",
    notify_session_key="agent:main:main",
    task_label="my-task",
    chat_mode="agent",
)

# Send follow-up message
result = client.send_message(chat_id="abc123", message="Now create a PDF summary")

# Get full history
result = client.get_history(chat_id="abc123")

# Quick status check
status = client.get_status(chat_id="abc123")

# Resume waiting after timeout
result = client.wait_for_completion(chat_id="abc123", timeout=1800)
```

### Optional Parameters

```python
result = client.create_chat(
    prompt="...",
    task_label="...",
    chat_mode="agent",
    project_id="...",                       # CellCog project for document context
    agent_role_id="...",                    # Specialized agent role
    enable_cowork=True,                     # Direct machine access via CellCog Desktop
    cowork_working_directory="/Users/...",  # Working directory for co-work
)
```

## File Handling

```python
# Send files to CellCog
result = client.create_chat(
    prompt='Analyze this data: <SHOW_FILE>/path/to/sales.csv</SHOW_FILE>',
    task_label="data-analysis",
)

# Request output at specific path
result = client.create_chat(
    prompt='Create a report: <GENERATE_FILE>/output/report.pdf</GENERATE_FILE>',
    task_label="report",
)
```

Generated files auto-download to `~/.cellcog/chats/{chat_id}/` or to `GENERATE_FILE` paths if specified.

## Chat Modes

| Mode | Speed | Min Credits | Best For |
|------|-------|-------------|----------|
| `"agent"` | Fast | 100 | Most tasks — research, images, audio, documents |
| `"agent core"` | Fast | 50 | Coding, co-work, terminal operations |
| `"agent team"` | 5–60 min | 500 | Deep research & multi-angled reasoning |
| `"agent team max"` | Slowest | 2,000 | High-stakes — legal, financial, academic |

## 35 Skills — The Cog Family

| Category | Skills |
|----------|--------|
| **Research & Analysis** | `research-cog` `fin-cog` `crypto-cog` `data-cog` `news-cog` |
| **Video & Cinema** | `video-cog` `cine-cog` `insta-cog` `tube-cog` `seedance-cog` |
| **Images & Design** | `image-cog` `brand-cog` `meme-cog` `banana-cog` `3d-cog` |
| **Audio & Music** | `audio-cog` `music-cog` `pod-cog` |
| **Documents & Slides** | `docs-cog` `slides-cog` `spreadsheets-cog` `resume-cog` `legal-cog` |
| **Apps & Prototypes** | `dash-cog` `game-cog` `proto-cog` |
| **Creative** | `comi-cog` `story-cog` `learn-cog` `travel-cog` |
| **Development** | `code-cog` `cowork-cog` `project-cog` `think-cog` |

Browse all skills: https://cellcog.ai/skills

## Error Handling

```python
from cellcog import (
    CellCogClient,
    PaymentRequiredError,
    MaxConcurrencyError,
    GatewayConfigError,
    SDKUpgradeRequiredError,
)

client = CellCogClient(agent_provider="openclaw")

try:
    result = client.create_chat(...)
except PaymentRequiredError as e:
    print(f"Add credits: {e.billing_url}")
except MaxConcurrencyError as e:
    print(f"Too many parallel chats: {e.operating_count}/{e.max_parallel}")
except GatewayConfigError as e:
    print(f"Fix: {e.fix_command}")  # OpenClaw notify mode only
except SDKUpgradeRequiredError as e:
    print(f"Upgrade: pip install cellcog>={e.minimum_version}")
```

## Links

- **CellCog Platform:** https://cellcog.ai
- **Skills Catalog:** https://cellcog.ai/skills
- **GitHub:** https://github.com/CellCog/cellcog_python
- **ClawHub Skills:** https://clawhub.ai
- **API Docs:** https://cellcog.ai/developer/docs
- **Get API Key:** https://cellcog.ai/profile?tab=api-keys

## License

MIT License — see [LICENSE](LICENSE) for details.
