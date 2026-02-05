"""
CellCog Daemon Delivery Module.

Handles notification delivery to OpenClaw sessions via Gateway API.
Implements parent session fallback for resilient delivery.
"""

import logging
import os
from pathlib import Path
from typing import Callable, Optional

import aiohttp

from .state import Listener

log = logging.getLogger(__name__)


def get_parent_session_key(session_key: str) -> Optional[str]:
    """
    Get parent session key for fallback delivery.
    
    Session key formats and their parents:
    - agent:<agentId>:main                          → None (is root)
    - agent:<agentId>:subagent:<uuid>               → agent:<agentId>:main
    - agent:<agentId>:subagent:<u1>:subagent:<u2>   → agent:<agentId>:subagent:<u1>
    - agent:<agentId>:telegram:dm:<id>              → agent:<agentId>:main
    - agent:<agentId>:discord:group:<id>            → agent:<agentId>:main
    
    Args:
        session_key: OpenClaw session key
        
    Returns:
        Parent session key, or None if already at root
    """
    parts = session_key.split(":")
    
    # agent:X:main → no parent (is root)
    if len(parts) == 3 and parts[2] == "main":
        return None
    
    # Handle nested subagents: find last "subagent" and remove it
    if "subagent" in parts:
        # Find index of last "subagent"
        last_idx = len(parts) - 1 - parts[::-1].index("subagent")
        if last_idx >= 2:
            parent_parts = parts[:last_idx]
            if len(parent_parts) == 2:
                # Was agent:X:subagent:Y → parent is agent:X:main
                return f"{parent_parts[0]}:{parent_parts[1]}:main"
            # Was agent:X:subagent:Y:subagent:Z → parent is agent:X:subagent:Y
            return ":".join(parent_parts)
    
    # Other patterns (telegram, discord, etc.) → parent is main
    if len(parts) >= 3 and parts[0] == "agent":
        return f"{parts[0]}:{parts[1]}:main"
    
    return None


def get_gateway_auth(auth_source: str) -> Optional[str]:
    """
    Resolve gateway auth token from source specification.
    
    Formats:
    - "env:VAR_NAME"           → os.environ.get("VAR_NAME")
    - "config:gateway.auth.token" → load from OpenClaw config file
    - "literal:token_value"    → use literal value
    
    Args:
        auth_source: Source specification string
        
    Returns:
        Auth token string, or None if not found
    """
    if auth_source.startswith("env:"):
        var_name = auth_source[4:]
        return os.environ.get(var_name)
    
    elif auth_source.startswith("config:"):
        config_path_str = auth_source[7:]
        # Load from ~/.openclaw/openclaw.json
        config_file = Path("~/.openclaw/openclaw.json").expanduser()
        if config_file.exists():
            try:
                import json
                config = json.loads(config_file.read_text())
                # Navigate path like "gateway.auth.token"
                value = config
                for key in config_path_str.split("."):
                    if isinstance(value, dict):
                        value = value.get(key, {})
                    else:
                        return None
                return value if isinstance(value, str) else None
            except Exception:
                pass
        return None
    
    elif auth_source.startswith("literal:"):
        return auth_source[8:]
    
    return None


def find_session(sessions: list[dict], session_key: str) -> Optional[dict]:
    """
    Find a session by key in the sessions list.
    
    Args:
        sessions: List of session dictionaries from Gateway
        session_key: Session key to find
        
    Returns:
        Session dict if found, None otherwise
    """
    for s in sessions:
        # OpenClaw Gateway returns "key", not "sessionKey"
        if s.get("key") == session_key:
            return s
    return None


def has_delivery_context(session: dict) -> bool:
    """
    Check if session can actually deliver messages to a user.
    
    Sessions with channels like "internal" or "unknown" cannot deliver.
    
    Args:
        session: Session dictionary from Gateway
        
    Returns:
        True if session has a valid delivery channel
    """
    ctx = session.get("deliveryContext", {})
    channel = ctx.get("channel") or session.get("channel")
    return channel and channel not in ("internal", "unknown", None)


async def list_sessions(
    gateway_url: str,
    auth: Optional[str],
    timeout: float = 30.0
) -> list[dict]:
    """
    List active sessions from OpenClaw Gateway.
    
    Args:
        gateway_url: Gateway URL
        auth: Authorization token (optional)
        timeout: Request timeout in seconds
        
    Returns:
        List of session dictionaries
    """
    headers = {"Authorization": f"Bearer {auth}"} if auth else {}
    
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"{gateway_url}/tools/invoke",
                headers=headers,
                json={
                    "tool": "sessions_list",
                    "args": {"limit": 100, "activeMinutes": 120}
                },
                timeout=aiohttp.ClientTimeout(total=timeout)
            )
            if resp.status == 200:
                data = await resp.json()
                # OpenClaw Gateway wraps response in result.details
                return data.get("result", {}).get("details", {}).get("sessions", [])
    except Exception as e:
        log.error(f"Error listing sessions from {gateway_url}: {e}")
    
    return []


async def send_to_session(
    gateway_url: str,
    gateway_auth: Optional[str],
    session_key: str,
    message: str,
    timeout: float = 30.0
) -> bool:
    """
    Send message to a session via Gateway.
    
    Args:
        gateway_url: Gateway URL
        gateway_auth: Authorization token (optional)
        session_key: Target session key
        message: Message to send
        timeout: Request timeout in seconds
        
    Returns:
        True if message was sent successfully
    """
    headers = {"Authorization": f"Bearer {gateway_auth}"} if gateway_auth else {}
    
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"{gateway_url}/tools/invoke",
                headers=headers,
                json={
                    "tool": "sessions_send",
                    "args": {
                        "sessionKey": session_key,
                        "message": message,
                        "timeoutSeconds": 0  # Non-blocking
                    }
                },
                timeout=aiohttp.ClientTimeout(total=timeout)
            )
            
            # Check both HTTP status and response body for errors
            if resp.status == 200:
                data = await resp.json()
                result = data.get("result", {})
                details = result.get("details", {})
                
                # Check if the actual delivery failed
                if details.get("status") == "error":
                    log.error(f"Gateway returned error for {session_key}: {details}")
                    return False
                
                return True
            
            return False
    except Exception as e:
        log.error(f"Error sending to {session_key}: {e}")
    
    return False


async def deliver_with_fallback(
    gateway_url: str,
    gateway_auth: Optional[str],
    session_key: str,
    message: str,
    active_sessions: list[dict]
) -> bool:
    """
    Deliver message to session with parent fallback chain.
    
    Walks up the parent chain until delivery succeeds or we reach root.
    
    Args:
        gateway_url: Gateway URL
        gateway_auth: Authorization token
        session_key: Target session key
        message: Message to deliver
        active_sessions: Pre-fetched list of active sessions
        
    Returns:
        True if message was delivered to any session in the chain
    """
    current_key = session_key
    attempted = set()
    
    while current_key and current_key not in attempted:
        attempted.add(current_key)
        
        # Check if session exists and can deliver
        session = find_session(active_sessions, current_key)
        
        if session and has_delivery_context(session):
            # Modify message if delivering to parent (not original target)
            deliver_message = message
            if current_key != session_key:
                deliver_message = f"[Originally for: {session_key}]\n\n{message}"
            
            success = await send_to_session(
                gateway_url=gateway_url,
                gateway_auth=gateway_auth,
                session_key=current_key,
                message=deliver_message
            )
            
            if success:
                if current_key != session_key:
                    log.info(f"Delivered to parent {current_key} (target was {session_key})")
                else:
                    log.info(f"Delivered to {current_key}")
                return True
        
        # Try parent session
        current_key = get_parent_session_key(current_key)
    
    log.warning(f"Could not deliver to {session_key} or any parent. Attempted: {attempted}")
    return False


async def deliver_to_all_listeners(
    listeners: list[Listener],
    message: str
) -> dict[str, bool]:
    """
    Deliver message to all listeners with parent fallback.
    
    Groups listeners by gateway URL for efficient session listing.
    
    Args:
        listeners: List of Listener objects
        message: Message to deliver to all
        
    Returns:
        Dictionary of session_key → delivery_success
    """
    results = {}
    
    # Group listeners by gateway URL for efficient session listing
    by_gateway: dict[str, list[Listener]] = {}
    for listener in listeners:
        url = listener.gateway_url
        if url not in by_gateway:
            by_gateway[url] = []
        by_gateway[url].append(listener)
    
    # Process each gateway
    for gateway_url, gateway_listeners in by_gateway.items():
        # Get auth from first listener (all should use same auth for same gateway)
        auth = get_gateway_auth(gateway_listeners[0].gateway_auth_source)
        
        # Fetch active sessions once per gateway
        active_sessions = await list_sessions(gateway_url, auth)
        
        # Deliver to each listener
        for listener in gateway_listeners:
            success = await deliver_with_fallback(
                gateway_url=gateway_url,
                gateway_auth=auth,
                session_key=listener.session_key,
                message=message,
                active_sessions=active_sessions
            )
            results[listener.session_key] = success
    
    return results
