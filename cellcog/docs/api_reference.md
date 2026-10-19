# CellCog SDK — Complete API Reference

## CellCogClient

```python
from cellcog import CellCogClient
client = CellCogClient(agent_provider="openclaw")
```

`agent_provider` (required) identifies the agent framework calling CellCog — lowercase
letters/numbers/hyphens. Common values: `"openclaw"`, `"cursor"`, `"claude-code"`,
`"codex"`, `"aider"`, `"windsurf"`, `"script"` (standalone scripts), `"cellcog"`
(CellCog's own agents orchestrating sub-chats).

**State directory:** all SDK state (tracked chats, downloads, daemon files) lives under
`~/.cellcog` by default. Set `CELLCOG_STATE_DIR` to override. In headless/container
environments where the home directory isn't writable (e.g. `HOME=/`), the SDK falls back
to a temp directory automatically instead of crashing.

---

## Chat Operations

### create_chat()

Create a new CellCog task. Three delivery modes:
- `wait_for_completion` (default): Blocks until done. Works with any agent.
- `send_only`: Fire-and-forget. Returns the moment the chat is accepted (`status="accepted"`);
  poll `get_status()` / `wait_for_completion()` yourself. Best for orchestrating several chats.
- `notify_on_completion`: Returns immediately. OpenClaw only.

```python
result = client.create_chat(
    prompt: str,                          # Task description (required)
    task_label: str = "",                 # Human-readable label
    delivery: str = "wait_for_completion",# "wait_for_completion" | "send_only" | "notify_on_completion"
    timeout: int = 1800,                  # Max wait seconds (wait mode only)
    notify_session_key: str = None,       # OpenClaw session key (notify mode only)
    gateway_url: str = None,              # OpenClaw Gateway URL (notify mode only)
    chat_mode: str = "agent",             # "agent", "creative", "team" (legacy names still work)
    chat_tier: str = None,                # "flash" | "core" | "max". Agent mode + None -> SDK default:
                                          #   "flash" ("max" when enable_cowork=True — coding needs depth).
                                          #   Other modes + None -> server default. Creative has no flash.
    project_id: str = None,               # Project context (see project-management-cellcog)
    agent_role_id: str = None,            # Specialized role (requires project_id)
    enable_cowork: bool = False,          # Direct machine access (see pair-programming-cellcog)
    cowork_working_directory: str = None, # Working dir for co-work
    enable_browse: bool = False,          # Drive the user's REAL Chrome (needs Desktop + extension;
                                          #   auto-enables co-work server-side)
    browser_profile_id: str = None,       # profileDir from get_browser_status() (None = "Default")
    enable_tools: bool = False,           # The user's connected SaaS tools (Gmail, Notion, ...)
    tools_selection: list = None,         # Toolkit slugs to restrict to (None = ALL connected tools)
)
```

**Returns (all modes):**
```python
{
    "chat_id": str,        # CellCog chat ID
    "is_operating": bool,  # True = still working, False = done
    "status": str,         # "completed" | "tracking" | "accepted" | "operating"
    "message": str,        # THE printable message — always print in full
}
```
A wait that gives up returns `status="operating"` with `timed_out=True` — the chat is
STILL running server-side; resume with `wait_for_completion()`. `"timeout"` is no longer
returned (it read as failure and misfired retry logic).

**Raises:**
- `PaymentRequiredError` (402) — insufficient credits
- `MaxConcurrencyError` (429) — too many parallel chats
- `AccountDisabledError` (403) — account flagged or disabled
- `GatewayConfigError` — sessions_send blocked (notify mode only)

#### File references in prompts (<SHOW_FILE>...</SHOW_FILE>)

Prompts may embed files for the agent with `<SHOW_FILE>/abs/path</SHOW_FILE>` tags. Two rules specific to SDK-launched chats:

- **`hc://` paths do NOT resolve in SDK-created chats.** hc:// resolution is scoped to the chat that owns the Desktop (Co-work) session; a chat created via `create_chat()` has no such session, even when your own orchestrating chat does. The working pattern: stage the files into a workspace the new chat can reach first (e.g. FileTransfer them into your container), then reference the CONTAINER paths in the prompt — the platform uploads and renders them for the sub-agent. This also keeps prompts small (a 6-file design brief shrank 143K to 10K chars vs embedding sources inline).
- **Prompt size cap: 50,000 characters** (`create_chat` returns 422 `string_too_long` beyond it). Embedding source files inline is the usual way to hit it — use the staging pattern above instead.

### send_message()

Continue an existing conversation. Same delivery modes as `create_chat()`.

⚠️ The default BLOCKS until the chat's entire next run completes. When relaying messages
to several chats, pass `delivery="send_only"` — otherwise the first send hangs your
script for that chat's whole run.

```python
result = client.send_message(
    chat_id: str,                         # Existing chat (required)
    message: str,                         # Follow-up message (required)
    task_label: str = None,               # Label for this message
    delivery: str = "wait_for_completion",# "wait_for_completion" | "send_only" | "notify_on_completion"
    timeout: int = 1800,                  # Max wait seconds (wait mode only)
    notify_session_key: str = None,       # OpenClaw session key (notify mode only)
    gateway_url: str = None,              # OpenClaw Gateway URL (notify mode only)
)
```

**Returns:** Same `{chat_id, is_operating, status, message}` shape.

### wait_for_completion()

Block until a chat finishes operating. Use to resume waiting after a timeout.

```python
completion = client.wait_for_completion(
    chat_id: str,
    timeout: int = 1800,                  # Seconds (default 30 min, max recommended 3600)
)
```

**Returns:** Same `{chat_id, is_operating, status, message}` shape.
- `status: "completed"` — chat finished, `message` contains full results
- `status: "operating"` + `timed_out: True` — still working server-side, `message` contains progress; resume with another `wait_for_completion()`

### get_history()

Full chat history. Use when original delivery was missed or for manual inspection.

```python
result = client.get_history(
    chat_id: str,
    download_files: bool = True,
)
```

**Returns:** Same `{chat_id, is_operating, status, message}` shape with full history.

### get_status()

Quick status check (no message content).

```python
status = client.get_status(chat_id: str)
```

**Returns:** `{"is_operating": bool, "status": str, "name": str, "latest_update": str | None, ...}`

`latest_update` carries the agent's most recent progress one-liner — poll it for live
orchestration dashboards. `None` until the agent posts its first update of a run.

### get_browser_status()

Browse availability on the user's machine — populate a profile picker from this.

```python
status = client.get_browser_status()
# {
#   "extension_installed": bool,
#   "chrome_running": bool,
#   "active_profile": {...} | None,
#   "available_profiles": [
#     {"profileDir": "Default", "profileName": "Nitish", "hostedDomain": None,
#      "hasExtension": True, "connected": True}, ...
#   ],
#   "agent_tab_count": int,
# }
```

Pass a profile's `profileDir` as `browser_profile_id` in `create_chat(enable_browse=True)`.

### list_toolkits()

The SaaS toolkit catalog with the user's connection state — populate a tool picker from this.

```python
toolkits = client.list_toolkits(connected_only=True)   # only what the user connected
# [{"slug": "gmail", "name": "Gmail", "connection": {...}, ...}, ...]
```

Pass toolkit `slug` values as `tools_selection` in `create_chat(enable_tools=True)`.

### list_toolkit_tools()

The individual tools a toolkit carries (for showing what enabling it unlocks).
`tools_selection` itself takes TOOLKIT slugs, not tool slugs.

```python
tools = client.list_toolkit_tools("gmail")
```

### delete_chat()

Permanently delete a chat and all server-side data (~15 seconds).

```python
result = client.delete_chat(chat_id: str)
```

**Returns:** `{"success": True, "message": str, "chat_id": str}`
**Raises:** `APIError(409)` if chat is currently operating.

### list_chats()

List recent chats.

```python
chats = client.list_chats(limit: int = 20)
```

### restart_chat_tracking()

Resume daemon monitoring after error recovery.

```python
result = client.restart_chat_tracking()
```

---

## AI Employees

An AI employee is addressed by `employee_id` and works in numbered shifts. Every payload carries `employee_id`, `shift_number` and the shift's `chat_id`. You can instruct an employee you own, or one shared with you in your organization (`access: "team"`, acting as its owner; the owner's credits pay).

### list_employees()

```python
client.list_employees() -> {"employees": [{"employee_id", "name", "title", "email", "access", "owner_name",
                                           "status", "current_shift": {"shift_number", "chat_id", "state"}, "url"}],
                            "count": int}
```

### get_employee()

```python
client.get_employee(employee_id: str, shifts_limit: int = 20, before_shift: int | None = None)
```
The list row plus `shifts` (newest first: `shift_number`, `chat_id`, `started_at`, `ended_at`, `stop_reason`, `trigger`, `is_current`), `shifts_total`, `next_before_shift` (pass it as `before_shift` for the next page).

### hire_employee()

```python
client.hire_employee(brief: str, name: str | None = None, chat_tier: str = "core")
    -> {"employee_id", "shift_number", "chat_id", "url", "next"}
```

Hire a new AI employee (SDK 2.6.0+). `brief` is the role in plain words, as typed on the hire page. The mode is
always agent; the employee starts with the owner's approval level and no Cowork, Browse or Tools access (it asks for
access itself). Read its first reply with `get_result(employee_id=...)`. To change its settings later, message it;
pausing and deleting stay on the web. Raises `PaymentRequiredError` when the account needs credits.

### message_employee()

```python
client.message_employee(employee_id: str, message: str)
```
Returns at once: `{"employee_id", "shift_number", "chat_id", "started_new_shift", "paused", "queued", "delivery", "next", "uploaded_files"}`. `delivery` is `live_shift`, `woke_shift`, `new_shift`, `held_paused` or `queued`. Files ride as SHOW_FILE tags, as in `send_message()`. **Raises:** `PaymentRequiredError` (the owner needs credits), `APIError(404)`.

### get_result()

```python
client.get_result(chat_id: str | None = None, employee_id: str | None = None,
                  shift_number: int | None = None, again: bool = False)
```
One-shot, never waits. Pass `chat_id` OR `employee_id` (+ optional `shift_number`, default the current shift). Not finished: `complete: False`, the progress notes since your last read, `next`. Finished: `complete: True`, `message`, `files`, `credits_used`, `finished`, `already_delivered` (the final message is delivered once; `again=True` reads it once more). The employee form adds `shift_number`, `is_current_shift`, `shift_state`, `employee_status` and `newer_shift_number` when a later shift exists.

### get_employee_history()

```python
client.get_employee_history(employee_id: str, shift_number: int | None = None, limit: int = 50)
```
One shift's messages (latest shift by default) plus `shift_number`, `is_current_shift`, `shifts_total`, `shift`, `messages_total`, `messages_returned`.

### wait_for_employee()

```python
client.wait_for_employee(employee_id: str, timeout: int = 1800, poll_interval: int = 30)
```
Polls `get_result(employee_id=...)` until the current shift has a finished reply. On timeout returns the last unfinished payload with `timed_out: True`.

---

## Account & Configuration

### get_account_status()

Check SDK configuration and authentication.

```python
status = client.get_account_status()
# {"configured": bool, "email": str, ...}
```

---

## Co-work (Desktop App)

### get_desktop_status()

Check if CellCog Desktop is connected.

```python
status = client.get_desktop_status()
# {"connected": bool, "system_info": {...} | None, ...}
```

### get_desktop_download_urls()

Get platform-specific download URLs and install commands.

```python
info = client.get_desktop_download_urls()
# {"mac": {"url": str, "install_commands": [...]}, "windows": {...}, "linux": {...}, "post_install": str}
```

---

## Projects & Documents

### list_projects()

```python
projects = client.list_projects()
# {"projects": [{"id", "name", "is_admin", "context_tree_id", ...}]}
```

### create_project()

```python
project = client.create_project(name: str, instructions: str = "")
```

### get_project()

```python
project = client.get_project(project_id: str)
```

### update_project()

```python
result = client.update_project(project_id: str, name: str = None, instructions: str = None)
```

### delete_project()

```python
result = client.delete_project(project_id: str)
```

### list_agent_roles()

```python
roles = client.list_agent_roles(project_id: str)
```

### list_documents()

```python
docs = client.list_documents(context_tree_id: str)
```

### upload_document()

```python
result = client.upload_document(
    context_tree_id: str,
    file_path: str,
    brief_context: str = None,
)
```

### delete_document()

```python
result = client.delete_document(context_tree_id: str, file_id: str)
```

### bulk_delete_documents()

```python
result = client.bulk_delete_documents(context_tree_id: str, file_ids: list)
# {"deleted": int, "failed": int, "results": {...}}
```

### get_context_tree_markdown()

```python
tree = client.get_context_tree_markdown(context_tree_id: str, include_long_description: bool = False)
```

### get_document_signed_urls()

```python
urls = client.get_document_signed_urls(context_tree_id: str, file_ids: list, expiration_hours: int = 1)
# {"urls": {file_id: url_or_null}, "errors": {file_id: error_msg}}
```

### get_document_signed_urls_by_path()

Get signed URLs using file paths from the context tree markdown (no file IDs needed).

```python
urls = client.get_document_signed_urls_by_path(
    context_tree_id: str,
    file_paths: list,
    expiration_hours: int = 1,
)
# {"urls": {path: url_or_null}, "errors": {path: error_msg}}
```

---

## Tickets

### create_ticket()

```python
result = client.create_ticket(
    type: str,              # "support", "feedback", "feature_request", "bug_report"
    title: str,
    description: str,
    chat_id: str = None,
    tags: list = None,
    priority: str = "medium",  # "low", "medium", "high", "critical"
)
```

---

## Documentation

### get_support_docs()

```python
docs = client.get_support_docs()  # Returns markdown string
```

### get_api_reference()

```python
docs = client.get_api_reference()  # Returns markdown string
```

---

## Exception Classes

```python
from cellcog.exceptions import (
    CellCogError,              # Base exception
    ConfigurationError,        # SDK not configured
    APIError,                  # General API error (status_code, message)
    ChatNotFoundError,         # Chat doesn't exist
    PaymentRequiredError,      # Insufficient credits (includes top_ups, billing_url)
    MaxConcurrencyError,       # Too many parallel chats
    AccountDisabledError,      # Account flagged or disabled
    SDKUpgradeRequiredError,   # SDK version too old
    GatewayConfigError,        # sessions_send blocked on OpenClaw Gateway
    FileUploadError,           # File upload failed
    FileDownloadError,         # File download failed
)
```

### PaymentRequiredError Attributes
- `top_ups`: List of `{"amount_dollars": int, "credits": int, "url": str}`
- `billing_url`: Direct link to billing page
- `min_credits_required`: Minimum credits for attempted mode
- `current_balance`: User's current balance
- `chat_mode` / `chat_mode_display`: Mode that was attempted

### MaxConcurrencyError Attributes
- `operating_count`: Currently running chats
- `max_parallel`: Maximum allowed with current balance
- `effective_balance`: Current credit balance
- `credits_per_slot`: Credits per additional slot (500)

### GatewayConfigError Attributes
- `gateway_url`: The Gateway URL that was checked
- `fix_command`: The exact command to run to fix the issue
