# CellCog SDK — Complete API Reference

## CellCogClient

```python
from cellcog import CellCogClient
client = CellCogClient(config_path=None)
```

---

## Chat Operations

### create_chat()

Create a new CellCog task. Returns immediately — results delivered via daemon.

```python
result = client.create_chat(
    prompt: str,                          # Task description (required)
    notify_session_key: str,              # Where to deliver results (required)
    task_label: str,                      # Human-readable label (required)
    chat_mode: str = "agent",             # "agent", "agent core", "agent team", "agent team max"
    project_id: str = None,               # Project context (see project-cog)
    agent_role_id: str = None,            # Specialized role (requires project_id)
    enable_cowork: bool = False,          # Direct machine access (see cowork-cog)
    cowork_working_directory: str = None, # Working dir for co-work
)
```

**Returns:** `{"chat_id": str, "status": "tracking", "listeners": int, "explanation": str}`

**Raises:**
- `PaymentRequiredError` (402) — insufficient credits
- `MaxConcurrencyError` (429) — too many parallel chats
- `AccountDisabledError` (403) — account flagged or disabled

### send_message()

Continue an existing conversation.

```python
result = client.send_message(
    chat_id: str,                         # Existing chat (required)
    message: str,                         # Follow-up message (required)
    notify_session_key: str,              # Where to deliver results (required)
    task_label: str,                      # Label for this message (required)
)
```

**Returns:** `{"chat_id": str, "status": "tracking", "listeners": int, "explanation": str}`

### wait_for_completion()

Block until a chat finishes operating.

```python
completion = client.wait_for_completion(
    chat_id: str,
    timeout: int = 1800,                  # Seconds (default 30 min, max recommended 3600)
)
```

**Returns:**
```python
{
    "chat_id": str,
    "is_operating": bool,       # False = done, True = timeout reached
    "status": str,              # "completed" | "waiting"
    "status_message": str
}
```

### get_status()

Quick status check (no message content).

```python
status = client.get_status(chat_id: str)
```

**Returns:** `{"is_operating": bool, ...}`

### get_history()

Full chat history with formatted messages.

```python
result = client.get_history(chat_id: str)
```

**Returns:** `{"is_operating": bool, "formatted_output": str, "messages": list}`

### delete_chat()

Permanently delete a chat and all server-side data.

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
# {"connected": bool, ...}
```

### get_desktop_download_urls()

Get platform-specific download URLs and install commands.

```python
info = client.get_desktop_download_urls()
# {"platforms": {"darwin": {...}, "linux": {...}, "windows": {...}}}
```

---

## Projects & Documents

### list_projects()

```python
projects = client.list_projects()
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
project = client.update_project(project_id: str, name: str = None, instructions: str = None)
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
    target_path: str = None,
    brief_context: str = None,
)
```

### delete_document()

```python
result = client.delete_document(context_tree_id: str, file_id: str)
```

### get_context_tree_markdown()

```python
tree = client.get_context_tree_markdown(context_tree_id: str, include_long_description: bool = False)
```

### get_document_signed_urls()

```python
urls = client.get_document_signed_urls(context_tree_id: str, file_ids: list)
```

---

## Tickets

### create_ticket()

```python
result = client.create_ticket(
    type: str,              # "support", "feedback", "feature_request", "bug_report"
    title: str,
    description: str = "",
    chat_id: str = None,
    tags: list = None,
    priority: str = "medium",  # "low", "medium", "high", "critical"
)
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
    UpgradeRequiredError,      # SDK version too old
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
