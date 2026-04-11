# CellCog SDK — Complete API Reference

## CellCogClient

```python
from cellcog import CellCogClient
client = CellCogClient(agent_provider="openclaw")
```

---

## Chat Operations

### create_chat()

Create a new CellCog task. Two delivery modes:
- `wait_for_completion` (default): Blocks until done. Works with any agent.
- `notify_on_completion`: Returns immediately. OpenClaw only.

```python
result = client.create_chat(
    prompt: str,                          # Task description (required)
    task_label: str = "",                 # Human-readable label
    delivery: str = "wait_for_completion",# "wait_for_completion" or "notify_on_completion"
    timeout: int = 1800,                  # Max wait seconds (wait mode only)
    notify_session_key: str = None,       # OpenClaw session key (notify mode only)
    gateway_url: str = None,              # OpenClaw Gateway URL (notify mode only)
    chat_mode: str = "agent",             # "agent", "agent core", "agent team", "agent team max"
    project_id: str = None,               # Project context (see project-cog)
    agent_role_id: str = None,            # Specialized role (requires project_id)
    enable_cowork: bool = False,          # Direct machine access (see cowork-cog)
    cowork_working_directory: str = None, # Working dir for co-work
)
```

**Returns (all modes):**
```python
{
    "chat_id": str,        # CellCog chat ID
    "is_operating": bool,  # True = still working, False = done
    "status": str,         # "completed" | "tracking" | "timeout"
    "message": str,        # THE printable message — always print in full
}
```

**Raises:**
- `PaymentRequiredError` (402) — insufficient credits
- `MaxConcurrencyError` (429) — too many parallel chats
- `AccountDisabledError` (403) — account flagged or disabled
- `GatewayConfigError` — sessions_send blocked (notify mode only)

### send_message()

Continue an existing conversation. Same delivery modes as `create_chat()`.

```python
result = client.send_message(
    chat_id: str,                         # Existing chat (required)
    message: str,                         # Follow-up message (required)
    task_label: str = None,               # Label for this message
    delivery: str = "wait_for_completion",# "wait_for_completion" or "notify_on_completion"
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
- `status: "timeout"` — still working, `message` contains progress

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

**Returns:** `{"is_operating": bool, "status": str, "name": str, ...}`

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
