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

**Three delivery modes:**

- **Wait for Completion (default)** — Blocks until CellCog finishes and returns the full result. Works with any agent — OpenClaw, Claude Code, Cursor, or any Python environment.

- **Send-only (`delivery="send_only"`)** — Fire-and-forget for ANY agent: returns the moment the chat/message is accepted (`status="accepted"`). Poll `get_status()` and fetch results with `wait_for_completion()`/`get_history()`. Use this when orchestrating several chats in parallel — the blocking default would hang on each chat's whole run. Works on `create_chat()` AND `send_message()`.

- **Notify on Completion (OpenClaw)** — Returns immediately. A background daemon monitors via WebSocket and delivers results to your OpenClaw session when done. Requires `sessions_send` on OpenClaw Gateway.

All methods return the same unified shape:

```python
{
    "chat_id": str,
    "is_operating": bool,
    "status": str,         # "completed" | "tracking" | "accepted" | "operating"
    "message": str,        # Always print this in full
}
```

A wait that gives up returns `status="operating"` with `timed_out=True` — the chat is still
running server-side; resume with `wait_for_completion()`.

## Configuration

```bash
export CELLCOG_API_KEY="sk_..."

# Optional: where SDK state lives (tracked chats, downloads, daemon files).
# Default ~/.cellcog; in headless/container environments where HOME isn't
# writable, the SDK falls back to a temp directory automatically.
export CELLCOG_STATE_DIR="/path/to/state"
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
    chat_mode="agent",              # "agent" | "creative" | "team" (legacy names still work)
    chat_tier="core",               # "flash" | "core" | "max" (omit for the mode's default)
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
    chat_tier="max",                        # "flash" | "core" | "max" — omit for the SDK default
    delivery="send_only",                   # fire-and-forget; default blocks until done
    project_id="...",                       # CellCog project for document context
    agent_role_id="...",                    # Specialized agent role
    enable_cowork=True,                     # Direct machine access via CellCog Desktop
    cowork_working_directory="/Users/...",  # Working directory for co-work
    enable_browse=True,                     # Drive the user's REAL Chrome (needs Desktop + extension)
    browser_profile_id="Default",           # from client.get_browser_status()
    enable_tools=True,                      # the user's connected SaaS tools
    tools_selection=["gmail", "notion"],    # toolkit slugs (omit for ALL); from client.list_toolkits()
)
```

## Browse & Tools

CellCog chats can drive the user's **real Chrome** (Browse) and call their **connected
SaaS tools** (Gmail, Notion, Slack, ... — Tools). Discover what's available, then enable
at chat creation:

```python
# Browse: discover Chrome profiles, then enable with one
status = client.get_browser_status()
profile = status["active_profile"]          # or let the user pick from available_profiles
result = client.create_chat(
    prompt="Log into the dashboard and screenshot the weekly report",
    enable_browse=True,
    browser_profile_id=profile["profileDir"],
)

# Tools: discover connected toolkits, then enable a selection (omit for ALL)
toolkits = client.list_toolkits(connected_only=True)
result = client.create_chat(
    prompt="Summarize this week's unread emails",
    enable_tools=True,
    tools_selection=["gmail"],              # toolkit slugs
)
```

Notes: Browse requires CellCog Desktop + the Chrome extension on the user's machine and
auto-enables co-work server-side. `tools_selection` takes TOOLKIT slugs (the granularity
users pick in the product UI); `list_toolkit_tools(slug)` shows what a toolkit unlocks.

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

## Chat Modes & Tiers

Every chat runs at a (mode, tier) operating point. Pick a mode for the KIND of work,
a tier for the DEPTH (omit `chat_tier` for the mode's default).

| Mode | Best For | Tiers |
|------|----------|-------|
| `"agent"` | Most tasks — assets, documents, production pipelines, coding/co-work | `flash` (SDK default) · `core` · `max` |
| `"creative"` | Design, brand, frontend craft — taste-first work | `core` (default) · `max` |
| `"team"` | Deep research ONLY — multi-source synthesis, citations (multi-agent) | `flash` · `core` (default) · `max` |

**Tier guidance for agent mode:** omit `chat_tier` and the SDK sends `"flash"` — right for
simple asset generation and light tasks. **Coding / co-work needs `"max"`** (applied
automatically when `enable_cowork=True`). Heavy multi-step production (video, data
analysis, financial models, legal drafting) → pass `chat_tier="max"` explicitly. Quality
disappointing on flash? Re-run with `chat_tier="max"`. Use `"team"` only for deep research.

Legacy mode names (`"agent core"`, `"agent team"`, `"agent team max"`) keep working
forever — the server normalizes them to their historical operating points.

## 35 Skills — The Cog Family

| Category | Skills |
|----------|--------|
| **Research & Analysis** | `deep-research-cellcog` `stock-analysis-cellcog` `crypto-research-cellcog` `data-analysis-cellcog` `news-briefing-cellcog` |
| **Video & Cinema** | `video-generation-cellcog` `cinematic-video-cellcog` `instagram-reels-tiktok-cellcog` `youtube-video-cellcog` `seedance-video-generation-cellcog` |
| **Images & Design** | `image-generation-cellcog` `logo-brand-identity-cellcog` `meme-generator-cellcog` `nano-banana-image-cellcog` `3d-model-generation-cellcog` |
| **Audio & Music** | `audio-generation-cellcog` `music-generation-cellcog` `podcast-generation-cellcog` |
| **Documents & Slides** | `pdf-document-generation-cellcog` `presentation-slides-cellcog` `excel-spreadsheet-cellcog` `resume-cover-letter-cellcog` `legal-documents-cellcog` |
| **Apps & Prototypes** | `dashboard-web-app-cellcog` `game-asset-generation-cellcog` `ui-prototype-wireframe-cellcog` |
| **Creative** | `comic-manga-generator-cellcog` `creative-writing-cellcog` `tutoring-education-cellcog` `travel-planning-cellcog` |
| **Development** | `coding-agent-cellcog` `pair-programming-cellcog` `project-management-cellcog` `brainstorming-strategy-cellcog` |

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
