# CellCog Python SDK

**CellCog: Any-to-Any for Agents** — Your sub-agent for quality work.

When you need depth, accuracy, or complex deliverables — research reports, interactive apps, videos, images, podcasts, memes, documents, and more — use CellCog.

## Installation

```bash
pip install cellcog
```

## Quick Start

```bash
export CELLCOG_API_KEY="sk_..."  # Get from https://cellcog.ai/profile?tab=api-keys
```

```python
from cellcog import CellCogClient

client = CellCogClient()

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

For sequential workflows, add `wait_for_completion()` after any call to block until CellCog finishes:

```python
completion = client.wait_for_completion(result["chat_id"], timeout=1800)
# Results delivered to your session; proceed with next action
```

## Configuration

Set the `CELLCOG_API_KEY` environment variable:

```bash
export CELLCOG_API_KEY="sk_..."
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
    chat_mode="agent",          # "agent" (fast) | "agent team" (deep) | "agent team max" (high-stakes)
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

### Synchronous Wait (for Workflows)

```python
# Block until CellCog finishes — daemon delivers results to your session
completion = client.wait_for_completion(
    chat_id="abc123",
    timeout=1800                # 30 min default; use 3600 for complex jobs
)
# Returns: {"chat_id", "is_operating", "status", "status_message"}
# is_operating=False → done; is_operating=True → timed out, still working
```

Composes with `create_chat()` and `send_message()` for sequential workflows. See the [cellcog skill](skills/cellcog/SKILL.md) for detailed guidance.

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

### Generated Files

Generated files (PDFs, images, etc.) are automatically downloaded to `~/.cellcog/chats/{chat_id}/`.

## Chat Modes

| Mode | Speed | Cost | Best For |
|------|-------|------|----------|
| `"agent"` | Fast (seconds–minutes) | 1x | Most tasks — research, images, audio, documents |
| `"agent team"` | Slower (5–60 minutes) | 4x | Deep research & multi-angled reasoning, every modality |
| `"agent team max"` | Slowest | 8x+ | High-stakes work — legal, financial, cutting-edge academic |

**Default to `"agent"`.** Use `"agent team"` for deep multi-angled reasoning. Use `"agent team max"` only for high-stakes work where the extra quality justifies the cost (≥2,000 credits).

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
| 🎬 Cinematics | `cine-cog` | Grand widescreen cinematics, short films, brand films |
| 🎶 Music | `music-cog` | Original music — instrumentals, vocals, scores, jingles |
| 💰 Finance | `fin-cog` | Stock analysis, valuation models, portfolio optimization |
| ✏️ Prototyping | `proto-cog` | UI/UX wireframes, interactive HTML prototypes |
| 🪙 Crypto | `crypto-cog` | Token analysis, DeFi research, on-chain metrics |
| 🔢 Data Science | `data-cog` | Data cleaning, statistical analysis, visualization, ML |
| 🧊 3D Models | `3d-cog` | 3D model generation — any input to production-ready GLB |
| 📝 Resumes | `resume-cog` | ATS-optimized resumes, cover letters, career documents |
| ⚖️ Legal | `legal-cog` | Contracts, NDAs, terms of service, privacy policies |
| 🍌 Nano Banana | `nano-banana-cog` | Nano Banana × CellCog image generation |
| 🌱 Seedance | `seedance-cog` | Seedance × CellCog video production |
| ✈️ Travel | `travel-cog` | Trip itineraries, travel research, destination planning |
| 📰 News | `news-cog` | News briefings, competitive intel, trend monitoring |

## OpenClaw Integration

This SDK is designed for [OpenClaw](https://openclaw.ai) agents. Install skills from ClawHub:

```bash
# Core SDK skill (required)
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
    print("Set CELLCOG_API_KEY env var")
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
