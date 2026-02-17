"""
CellCog SDK Message Formatter.

Handles formatting of messages for delivery to OpenClaw sessions.
Preserves the exact format from v0.1.9.
"""

from datetime import datetime
from typing import Optional


def format_timestamp(iso_timestamp: str) -> str:
    """
    Format ISO timestamp for display.
    
    Args:
        iso_timestamp: ISO 8601 timestamp string
        
    Returns:
        Formatted string like "2026-02-04 14:30 UTC"
    """
    if not iso_timestamp:
        return "unknown time"
    try:
        if iso_timestamp.endswith("Z"):
            iso_timestamp = iso_timestamp[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_timestamp


def format_single_message(
    role: str,
    content: str,
    chat_id: str,
    created_at: str,
    is_last_cellcog: bool = False,
    is_operating: bool = True
) -> str:
    """
    Format a single message for delivery.
    
    Output format (preserved from v0.1.9):
    ```
    <MESSAGE FROM {role} on Chat {chat_id} at {timestamp}>
    {content}
    <MESSAGE END>
    
    [CellCog stopped operating...] (only for last cellcog msg when not operating)
    ```
    
    Args:
        role: "cellcog" or "openclaw"
        content: Message content with local paths
        chat_id: Chat ID
        created_at: ISO timestamp
        is_last_cellcog: Whether this is the last CellCog message
        is_operating: Whether chat is still operating
        
    Returns:
        Formatted message string
    """
    timestamp = format_timestamp(created_at)
    
    lines = [
        f"<MESSAGE FROM {role} on Chat {chat_id} at {timestamp}>",
        content,
        "<MESSAGE END>",
    ]
    
    # Completion indicator removed — "Next Steps" section in daemon notification handles this.
    # This avoids duplicate YOUR TURN blocks in the notification output.
    
    lines.append("")  # Blank line between messages
    
    return "\n".join(lines)


def format_messages_for_delivery(
    messages: list[dict],
    chat_id: str,
    is_operating: bool,
    start_index: int = 0
) -> tuple[str, int]:
    """
    Format multiple messages for delivery.
    
    Only formats messages starting from start_index (for unseen filtering).
    
    Args:
        messages: List of {"role": str, "content": str, "created_at": str}
        chat_id: Chat ID for formatting
        is_operating: Whether chat is still operating
        start_index: First message index to include (for unseen filtering)
    
    Returns:
        Tuple of (formatted_output, last_message_index)
    """
    if not messages:
        return "", -1
    
    # Find last CellCog message index (in full list)
    last_cellcog_idx = -1
    for i, msg in enumerate(messages):
        if msg["role"] == "cellcog":
            last_cellcog_idx = i
    
    formatted_parts = []
    last_idx = start_index - 1
    
    for i, msg in enumerate(messages):
        if i < start_index:
            continue
        
        is_last_cellcog = (msg["role"] == "cellcog" and i == last_cellcog_idx)
        
        formatted = format_single_message(
            role=msg["role"],
            content=msg["content"],
            chat_id=chat_id,
            created_at=msg["created_at"],
            is_last_cellcog=is_last_cellcog,
            is_operating=is_operating
        )
        formatted_parts.append(formatted)
        last_idx = i
    
    return "\n".join(formatted_parts), last_idx


def session_key_to_filename(session_key: str) -> str:
    """
    Convert session key to file-safe name for seen indices.
    
    Examples:
        "agent:main:main" → "agent_main_main"
        "agent:main:subagent:8c980d81-cec5-48a3-926f-2b04053dfde1" → "agent_main_subagent_8c980d81"
        
    Args:
        session_key: OpenClaw session key
        
    Returns:
        File-safe string for use as filename
    """
    # Replace colons with underscores
    safe = session_key.replace(":", "_")
    
    # Truncate UUIDs to first segment for readability
    parts = safe.split("_")
    if len(parts) > 4:  # Has UUID
        uuid_part = parts[-1]
        if len(uuid_part) > 8:
            parts[-1] = uuid_part[:8]
    
    return "_".join(parts)
