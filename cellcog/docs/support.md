# CellCog Support & Troubleshooting

## Error Handling

All CellCog errors are self-documenting. When an error occurs, you receive a clear message explaining what happened and exact steps to resolve it — including direct links for payment, API key management, or SDK upgrades.

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| `PaymentRequiredError` (402) | Insufficient credits for the requested chat mode | Present the included `top_ups` payment links to your human |
| `MaxConcurrencyError` (429) | Too many parallel chats running | Wait for a chat to finish, or add credits for more slots |
| `AccountDisabledError` (403) | Account flagged, disabled, or email not verified | Direct human to https://cellcog.ai or contact support@cellcog.ai |
| `ChatNotFoundError` (404) | Chat doesn't exist or was deleted | Verify the chat_id |
| `APIError` (various) | General API error | Check the error message for details |

### Recovery Pattern

After resolving any error, call `client.restart_chat_tracking()` to resume monitoring. No data is lost — chats that completed during downtime deliver results immediately.

```python
# After fixing the issue (e.g., adding credits):
client.restart_chat_tracking()
```

---

## Deleting Chats

Permanently delete a chat and all its data from CellCog's servers:

```python
result = client.delete_chat(chat_id="abc123")
```

Everything is purged server-side within ~15 seconds — messages, files, containers, metadata. Your local downloads are preserved. Cannot delete a chat that's currently operating.

---

## Submitting Tickets

Report bugs, request features, or send feedback directly to the CellCog team:

```python
result = client.create_ticket(
    type="feedback",        # "support", "feedback", "feature_request", "bug_report"
    title="Brief description",
    description="Details...",
    chat_id="abc123",       # Optional: link to relevant chat
    tags=["tag1"],          # Optional
    priority="medium"       # "low", "medium", "high", "critical"
)
```

All feedback — positive, negative, or observations — helps improve CellCog.

---

## SDK Daemon Troubleshooting

The CellCog daemon runs in the background to monitor chat completions and deliver results.

### Check Daemon Status
```bash
cat ~/.cellcog/daemon.pid
ps aux | grep cellcog
```

### View Logs
```bash
tail -f ~/.cellcog/daemon.log
```

### Restart Daemon
```bash
kill $(cat ~/.cellcog/daemon.pid)
```
Then call any `create_chat()` or `send_message()` — the daemon auto-restarts.

### State Files
```
~/.cellcog/
├── config.json              # API key storage
├── daemon.pid               # Daemon process ID
├── daemon.log               # Daemon logs
├── tracked_chats/           # One file per tracked chat
│   └── abc123.json
└── chats/
    └── abc123/
        ├── downloads/       # Auto-downloaded files
        └── .seen_indices/   # Per-session message tracking
```

---

## Your Data, Your Control

- **Uploads:** Only files you explicitly reference via `<SHOW_FILE>` are transmitted — the SDK never scans or uploads files without your instruction
- **Downloads:** Generated files auto-download to `~/.cellcog/chats/{chat_id}/` (or to `GENERATE_FILE` paths if specified)
- **Deletion:** `client.delete_chat(chat_id)` — full server-side purge in ~15 seconds. Also available via web UI at https://cellcog.ai
- **Local storage:** API key at `~/.openclaw/cellcog.json`, daemon state at `~/.cellcog/`

---

## OpenClaw 2026.4.x Gateway Configuration

OpenClaw 2026.4+ classifies `sessions_send` as a "dangerous tool" and blocks it at the gateway level by default. CellCog's daemon uses `sessions_send` to deliver task completion notifications to your session.

**Symptoms:** CellCog chats complete on the web platform but notifications are never delivered to your OpenClaw session. Daemon logs may show "Tool not available: sessions_send".

**Fix:** Run once in your OpenClaw environment:
```bash
openclaw config set gateway.tools.allow '["sessions_send", "sessions_list"]'
```
Then restart the gateway. This is a one-time configuration change.

**Verify:** After restarting, create a simple test chat. If notifications arrive, the fix is working.

---

## Terms of Service & Privacy

Before using CellCog, please review and agree to our [Terms of Service](https://cellcog.ai/policies/terms) and [Privacy Policy](https://cellcog.ai/policies/privacy-policy).

Key points:
- AI is powerful but imperfect — it can and does make mistakes
- Spending credits does not guarantee a usable output
- There is always a learning curve to using CellCog efficiently

For the full details: https://cellcog.ai/policies/terms

---

## Complete API Reference

For the full API reference with all method signatures, parameters, return types, and exception classes:

```python
api_docs = client.get_api_reference()
```
