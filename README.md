# CellCog Python SDK

**CellCog: Any-to-Any for Agents** — Your sub-agent for quality work.

When you need depth, accuracy, or complex deliverables — research reports, interactive apps, videos, images, podcasts, memes, documents, and more — use CellCog.

## Installation

```bash
pip install cellcog
```

## Quick Start

```python
from cellcog import CellCogClient

client = CellCogClient()
client.set_api_key("sk_...")  # Get from https://cellcog.ai/profile?tab=api-keys

# Fire-and-forget: returns immediately
result = client.create_chat(
    prompt="Research quantum computing advances in 2026",
    notify_session_key="agent:main:main",
    task_label="quantum-research",
    chat_mode="agent"
)

# Continue with other work — daemon notifies you when complete
print(result["explanation"])
```

## How It Works

1. **You call `create_chat()`** — SDK sends request to CellCog, returns immediately
2. **Background daemon monitors** — WebSocket connection watches for progress and completion
3. **Interim updates every 4 minutes** — for long-running tasks, your session gets progress updates
4. **Completion notification** — daemon delivers full response + downloaded files to your session

No polling. No blocking. Fire and forget.

## Configuration

```python
client = CellCogClient()
client.set_api_key("sk_...")  # SDK handles storage automatically
```

**Get your API key:**
1. Create account: https://cellcog.ai/signup
2. Add payment: https://cellcog.ai/profile?tab=billing
3. Get API key: https://cellcog.ai/profile?tab=api-keys

## API Reference

### Primary Methods (Fire-and-Forget)

```python
# Create new chat — returns immediately
result = client.create_chat(
    prompt="Your task...",
    notify_session_key="agent:main:main",
    task_label="my-task",
    chat_mode="agent",          # "agent" (fast) or "agent team" (deep work)
    project_id=None             # Optional CellCog project ID
)
# Returns: {"chat_id", "status", "explanation", "daemon_listening", "listeners"}

# Send follow-up to existing chat — returns immediately
result = client.send_message(
    chat_id="abc123",
    message="Now create a PDF summary",
    notify_session_key="agent:main:main",
    task_label="summary"
)

# Manual inspection (ignores seen indices)
history = client.get_history(chat_id="abc123")

# Quick status check
status = client.get_status(chat_id="abc123")
# Returns: {"status", "name", "is_operating", "error_type"}

# List recent chats
chats = client.list_chats(limit=20)
```

## File Handling

### Send Files to CellCog

```python
result = client.create_chat(
    prompt="""
    Analyze this data:
    <SHOW_FILE>/path/to/sales.csv</SHOW_FILE>
    """,
    notify_session_key="agent:main:main",
    task_label="data-analysis"
)
# SDK automatically uploads local files
```

### Request Output at Specific Locations

```python
result = client.create_chat(
    prompt="""
    Create analysis report:
    <GENERATE_FILE>/path/to/output/report.pdf</GENERATE_FILE>
    """,
    notify_session_key="agent:main:main",
    task_label="report"
)
# SDK transforms GENERATE_FILE → external_local_path
# CellCog generates the file, SDK downloads to your specified path
```

## Chat Modes

| Mode | Speed | Cost | Best For |
|------|-------|------|----------|
| `"agent"` | Fast (seconds–minutes) | 1x | Most tasks — research, images, audio, documents |
| `"agent team"` | Slower (5–60 minutes) | 4x | Deep work — multi-source research, complex videos, investor decks |

**Default to `"agent"`.** Use `"agent team"` when quality requires multiple reasoning passes.

## What You Can Create

| Capability | Skill | Description |
|-----------|-------|-------------|
| 🔬 Research | `research-cog` | Deep analysis with citations |
| 🎬 Video | `video-cog` | Marketing videos, explainers, lipsync |
| 🎨 Images | `image-cog` | Generated images, style transfer, consistent characters |
| 🎵 Audio | `audio-cog` | Text-to-speech (8 voices), music generation |
| 🎙️ Podcasts | `pod-cog` | Multi-voice dialogue + intro/outro music |
| 😂 Memes | `meme-cog` | AI meme generation with quality curation |
| 📊 Dashboards | `dash-cog` | Interactive HTML apps and visualizations |
| 📽️ Slides | `slides-cog` | Presentations (PDF default) |
| 📈 Spreadsheets | `sheet-cog` | Excel files, financial models |
| 📄 Documents | `docs-cog` | PDFs — resumes, contracts, reports |
| 🏷️ Branding | `brand-cog` | Logos, color palettes, brand kits |
| 📚 Comics | `comi-cog` | Manga, webtoons, comic strips |
| 🎮 Games | `game-cog` | Game assets, sprites, GDDs |
| 📸 Social | `insta-cog` | Instagram/TikTok content |
| 📚 Learning | `learn-cog` | Tutoring, study guides |
| 📖 Stories | `story-cog` | Fiction, screenplays, world building |
| 💭 Thinking | `think-cog` | Collaborative problem-solving |
| 📺 YouTube | `tube-cog` | Shorts, tutorials, thumbnails |

## OpenClaw Integration

This SDK is designed for [OpenClaw](https://openclaw.ai) agents. Install skills from ClawHub:

```bash
# Mothership (required)
clawhub install cellcog

# Install capability-specific skills as needed
clawhub install research-cog
clawhub install video-cog
clawhub install pod-cog
# ... etc.
```

See individual skill SKILL.md files for detailed usage guides.

## Error Handling

```python
from cellcog import (
    CellCogClient,
    PaymentRequiredError,
    ConfigurationError,
    SDKUpgradeRequiredError,
)

client = CellCogClient()

try:
    result = client.create_chat(...)
except PaymentRequiredError as e:
    print(f"Add credits at: {e.subscription_url}")
except ConfigurationError:
    print("Run client.set_api_key('sk_...')")
except SDKUpgradeRequiredError as e:
    print(f"Upgrade: pip install cellcog=={e.minimum_version}")
```

## Links

- **CellCog Platform:** https://cellcog.ai
- **GitHub:** https://github.com/CellCog/cellcog_python
- **ClawHub Skills:** https://clawhub.ai
- **API Docs:** https://cellcog.ai/developer/docs
- **Get API Key:** https://cellcog.ai/profile?tab=api-keys

## License

MIT License — see [LICENSE](LICENSE) for details.
