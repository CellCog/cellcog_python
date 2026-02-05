"""
CellCog Daemon Main Module.

Forever-running daemon that monitors CellCog chats via WebSocket
and notifies OpenClaw sessions upon completion.

Includes:
- Fallback polling mechanism for reliability
- Interim updates delivery every ~4 minutes for long-running tasks
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import aiohttp
import requests

from .state import StateManager, TrackedChat, Listener
from .delivery import deliver_to_all_listeners, get_gateway_auth, send_to_session

log = logging.getLogger(__name__)


class CellCogDaemon:
    """
    Forever-running daemon that monitors CellCog chats via WebSocket.
    
    Responsibilities:
    - Watch ~/.cellcog/tracked_chats/ for new files
    - Maintain WebSocket connection when tracking > 0 chats
    - Fallback polling when WebSocket fails
    - Collect and deliver interim agent updates every ~4 minutes
    - On CHAT_COMPLETED: process and notify all listeners
    - Survive system restart (reconcile state on startup)
    """
    
    def __init__(
        self,
        api_key: str,
        api_base_url: str = "https://cellcog.ai/api",
        base_dir: Optional[Path] = None
    ):
        """
        Initialize daemon.
        
        Args:
            api_key: CellCog API key
            api_base_url: CellCog API base URL
            base_dir: Base directory for state files
        """
        self.api_key = api_key
        self.api_base_url = api_base_url
        
        # State management
        self.state = StateManager(base_dir)
        self.tracked_chats: dict[str, TrackedChat] = {}
        
        # WebSocket state
        self.ws_connected = False
        self.ws_task: Optional[asyncio.Task] = None
        self.ws_healthy = False  # Track if WS is actually working
        
        # Polling state
        self.poll_task: Optional[asyncio.Task] = None
        self.poll_interval = 30  # seconds
        
        # File watcher state
        self.watcher_task: Optional[asyncio.Task] = None
        
        # Interim updates state
        # Each update is {"text": str, "timestamp": float}
        self.agent_updates: dict[str, list[dict]] = {}  # chat_id → list of update dicts
        self.last_update_delivery: dict[str, float] = {}  # chat_id → timestamp
        self.interim_update_interval = 240  # 4 minutes
        self.max_updates_per_chat = 50  # Prevent memory bloat on very long tasks
        self.interim_task: Optional[asyncio.Task] = None
        
        # Control flag
        self.running = True
        
        # Import message processor lazily to avoid circular imports
        self._message_processor = None
    
    def _get_message_processor(self):
        """Get or create message processor (lazy initialization)."""
        if self._message_processor is None:
            from ..config import Config
            from ..files import FileProcessor
            from ..message_processor import MessageProcessor
            
            config = Config()
            config._config_data["api_key"] = self.api_key
            file_processor = FileProcessor(config)
            self._message_processor = MessageProcessor(config, file_processor)
        return self._message_processor
    
    async def run(self):
        """
        Main daemon entry point.
        
        Runs forever until shutdown signal received.
        """
        log.info("CellCog Daemon starting...")
        
        # 1. Reconcile state (handle restart/crash recovery)
        await self.reconcile_state()
        
        # 2. Start file watcher
        self.watcher_task = asyncio.create_task(self._file_watcher_loop())
        
        # 3. Connect WebSocket if we have chats to track
        await self._maybe_connect_websocket()
        
        # 4. Start fallback polling (always runs as backup)
        self.poll_task = asyncio.create_task(self._fallback_poll_loop())
        
        # 5. Start interim update loop
        self.interim_task = asyncio.create_task(self._interim_update_loop())
        
        # 6. Run forever
        log.info(f"Daemon running. Tracking {len(self.tracked_chats)} chats.")
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        
        # Cleanup
        await self._shutdown()
        log.info("Daemon shutdown complete.")
    
    async def reconcile_state(self):
        """
        Reconcile file-based state with actual CellCog state.
        
        Called on startup to handle system restart/crash recovery.
        For each tracked chat:
        - If still operating: add to active tracking
        - If completed: process completion immediately
        """
        log.info("Reconciling state...")
        
        # Load all tracked chats from disk
        tracked_from_disk = self.state.load_all_tracked()
        
        for chat_id, chat in tracked_from_disk.items():
            try:
                # Check actual status from CellCog
                status = self._get_chat_status(chat_id)
                
                if status.get("is_operating", False):
                    # Still operating - add to active tracking
                    self.tracked_chats[chat_id] = chat
                    chat.update_verified_at()
                    self.state.save_tracked(chat)
                    log.info(f"Resuming tracking: {chat_id} ({len(chat.listeners)} listeners)")
                else:
                    # Already completed while daemon was down
                    log.info(f"Chat {chat_id} completed while daemon was down, processing...")
                    await self._handle_completion(chat_id, chat)
                    
            except Exception as e:
                log.error(f"Error reconciling chat {chat_id}: {e}")
                # Keep in tracking - will retry later
                self.tracked_chats[chat_id] = chat
        
        log.info(f"Reconciliation complete. Active chats: {len(self.tracked_chats)}")
    
    async def _handle_completion(self, chat_id: str, chat: Optional[TrackedChat] = None):
        """
        Handle chat completion.
        
        1. IMMEDIATELY remove from tracking to prevent duplicate processing
        2. Clear interim state
        3. Get full history (guaranteed to have all blob URLs)
        4. For each listener: process messages with seen index, notify
        5. Remove tracking file
        """
        # IMMEDIATELY remove from tracking to prevent duplicate processing
        # This is critical because CellCog may send CHAT_COMPLETED twice
        if chat is None:
            chat = self.tracked_chats.pop(chat_id, None)
        else:
            self.tracked_chats.pop(chat_id, None)
        
        # Clear interim state
        self._clear_interim_state(chat_id)
        
        if chat is None:
            log.warning(f"handle_completion called for unknown/already-processed chat: {chat_id}")
            return
        
        log.info(f"Processing completion for {chat_id} ({len(chat.listeners)} listeners)")
        
        try:
            # 1. Get full history
            history = self._get_chat_history(chat_id)
            
            # 2. Process and notify each listener
            processor = self._get_message_processor()
            
            for listener in chat.listeners:
                try:
                    # Process messages for this listener (respects their seen index)
                    result = processor.process_for_delivery(
                        chat_id=chat_id,
                        session_key=listener.session_key,
                        history=history,
                        is_operating=False  # Chat is completed
                    )
                    
                    # Build notification message
                    notification = self._build_notification(
                        chat_id=chat_id,
                        task_label=listener.task_label,
                        result=result
                    )
                    
                    # Deliver to this listener
                    log.info(f"Delivering notification to {listener.session_key}...")
                    log.debug(f"Gateway URL: {listener.gateway_url}")
                    log.debug(f"Auth source: {listener.gateway_auth_source}")
                    
                    delivery_results = await deliver_to_all_listeners(
                        listeners=[listener],
                        message=notification
                    )
                    
                    success = delivery_results.get(listener.session_key, False)
                    if success:
                        log.info(f"✓ Notified {listener.session_key}: {result.delivered_count} messages")
                    else:
                        log.warning(f"✗ Failed to notify {listener.session_key}")
                    
                except Exception as e:
                    log.error(f"Error notifying {listener.session_key}: {e}", exc_info=True)
            
            # 3. Remove tracking file AFTER successful delivery
            self.state.remove_tracked(chat_id)
            log.info(f"Completed processing for {chat_id}")
            
        except Exception as e:
            log.error(f"Error handling completion for {chat_id}: {e}", exc_info=True)
            # Remove tracking file anyway to prevent stuck state
            self.state.remove_tracked(chat_id)
        
        await self._maybe_disconnect_websocket()
    
    def _build_notification(
        self,
        chat_id: str,
        task_label: str,
        result
    ) -> str:
        """Build notification message for delivery."""
        
        # Header
        header = f"✅ {task_label} completed!"
        
        # Stats
        stats = f"Chat ID: {chat_id}"
        stats += f"\nMessages delivered: {result.delivered_count}"
        
        # Files
        if result.downloaded_files:
            files_list = "\n".join(f"  - {f}" for f in result.downloaded_files)
            stats += f"\nFiles downloaded:\n{files_list}"
        
        # Formatted messages
        content = result.formatted_output
        
        # Footer
        footer = f'Use `client.get_history("{chat_id}")` to view full conversation.'
        
        return f"{header}\n\n{stats}\n\n{content}\n{footer}"
    
    # =========================================================================
    # Interim Updates
    # =========================================================================
    
    def _collect_update(self, chat_id: str, text: str):
        """Collect an agent update for a chat with deduplication."""
        if chat_id not in self.agent_updates:
            self.agent_updates[chat_id] = []
            self.last_update_delivery[chat_id] = time.time()
        
        updates = self.agent_updates[chat_id]
        
        # Deduplicate: skip if same as last update
        if updates and updates[-1]["text"] == text:
            log.debug(f"Skipping duplicate update for {chat_id}: {text[:30]}...")
            return
        
        # Prevent unbounded memory growth
        if len(updates) < self.max_updates_per_chat:
            updates.append({
                "text": text,
                "timestamp": time.time()
            })
        
        log.debug(f"Collected update for {chat_id}: {text[:50]}...")
    
    def _clear_interim_state(self, chat_id: str):
        """Clear interim state for a chat."""
        self.agent_updates.pop(chat_id, None)
        self.last_update_delivery.pop(chat_id, None)
    
    async def _interim_update_loop(self):
        """
        Periodically deliver collected agent updates to listeners.
        
        Checks every minute, delivers if:
        1. At least interim_update_interval seconds passed since last delivery
        2. There are updates to deliver
        """
        log.info(f"Interim update loop started (interval: {self.interim_update_interval}s)")
        
        while self.running:
            await asyncio.sleep(60)  # Check every minute
            
            if not self.tracked_chats:
                continue
            
            now = time.time()
            
            for chat_id in list(self.agent_updates.keys()):
                # Skip if chat no longer tracked
                if chat_id not in self.tracked_chats:
                    self._clear_interim_state(chat_id)
                    continue
                
                last_delivery = self.last_update_delivery.get(chat_id, 0)
                updates = self.agent_updates.get(chat_id, [])
                
                # Deliver if interval passed AND we have updates
                if updates and (now - last_delivery) >= self.interim_update_interval:
                    log.info(f"Delivering {len(updates)} interim updates for {chat_id}")
                    await self._deliver_interim_updates(chat_id, updates)
                    
                    # Clear delivered updates and reset timer
                    self.agent_updates[chat_id] = []
                    self.last_update_delivery[chat_id] = now
    
    async def _deliver_interim_updates(self, chat_id: str, updates: list[dict]):
        """Deliver interim agent updates to all listeners."""
        chat = self.tracked_chats.get(chat_id)
        if not chat or not chat.listeners:
            return
        
        task_label = chat.listeners[0].task_label
        message = self._build_interim_message(chat_id, task_label, updates)
        
        for listener in chat.listeners:
            try:
                auth = get_gateway_auth(listener.gateway_auth_source)
                success = await send_to_session(
                    gateway_url=listener.gateway_url,
                    gateway_auth=auth,
                    session_key=listener.session_key,
                    message=message
                )
                
                if success:
                    log.info(f"✓ Delivered interim update to {listener.session_key}")
                else:
                    log.warning(f"✗ Failed interim delivery to {listener.session_key}")
                    
            except Exception as e:
                log.error(f"Error delivering interim update to {listener.session_key}: {e}")
    
    def _build_interim_message(
        self,
        chat_id: str,
        task_label: str,
        updates: list[dict]
    ) -> str:
        """Build interim status update message."""
        
        # Take last 10 and REVERSE (newest first)
        display_updates = list(reversed(updates[-10:]))
        
        now = time.time()
        update_lines = []
        
        for update in display_updates:
            text = update["text"]
            ts = update["timestamp"]
            
            # Truncate long updates
            if len(text) > 100:
                text = text[:97] + "..."
            
            # Format relative time
            elapsed = now - ts
            if elapsed < 60:
                time_str = "just now"
            elif elapsed < 3600:
                mins = int(elapsed / 60)
                time_str = f"{mins}m ago"
            else:
                hours = int(elapsed / 3600)
                time_str = f"{hours}h ago"
            
            update_lines.append(f"  • [{time_str}] {text}")
        
        # Build final message
        lines = [
            f"⏳ {task_label} - CellCog is still working",
            "",
            "Your request is still being processed. The final response is not ready yet.",
            "",
            "Recent activity from CellCog (newest first):",
        ]
        
        lines.extend(update_lines)
        
        if len(updates) > 10:
            lines.append(f"  ... and {len(updates) - 10} earlier updates")
        
        lines.extend([
            "",
            f"Chat ID: {chat_id}",
            "",
            "We'll deliver the complete response when CellCog finishes processing."
        ])
        
        return "\n".join(lines)
    
    # =========================================================================
    # WebSocket Management
    # =========================================================================
    
    async def _maybe_connect_websocket(self):
        """Connect WebSocket if we have chats to track and not connected."""
        if len(self.tracked_chats) > 0 and not self.ws_connected:
            self.ws_task = asyncio.create_task(self._websocket_loop())
            self.ws_connected = True
            log.info(f"WebSocket connecting, tracking {len(self.tracked_chats)} chats")
    
    async def _maybe_disconnect_websocket(self):
        """Disconnect WebSocket if no more chats to track."""
        if len(self.tracked_chats) == 0 and self.ws_connected:
            if self.ws_task:
                self.ws_task.cancel()
                try:
                    await self.ws_task
                except asyncio.CancelledError:
                    pass
                self.ws_task = None
            self.ws_connected = False
            self.ws_healthy = False
            log.info("WebSocket disconnected, no active chats")
    
    async def _websocket_loop(self):
        """Main WebSocket loop with auto-reconnect."""
        # Build WebSocket URL
        ws_base = self.api_base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_base}/cellcog/ws/user/stream?api_key={self.api_key}"
        
        # Log URL without exposing full API key
        safe_url = f"{ws_base}/cellcog/ws/user/stream?api_key={self.api_key[:10]}..."
        log.info(f"WebSocket URL: {safe_url}")
        
        while self.ws_connected and self.running:
            try:
                import websockets
                from websockets.exceptions import InvalidStatusCode
                
                log.info("Attempting WebSocket connection...")
                
                async with websockets.connect(
                    ws_url,
                    ping_interval=30,
                    ping_timeout=10,
                    additional_headers={"User-Agent": "CellCog-SDK/0.1.10"}
                ) as ws:
                    log.info("✓ WebSocket connected successfully!")
                    self.ws_healthy = True
                    
                    async for message in ws:
                        if message == "pong":
                            continue
                        
                        try:
                            msg = json.loads(message)
                            await self._handle_ws_message(msg)
                        except json.JSONDecodeError:
                            log.warning(f"Invalid JSON from WebSocket: {message[:100]}")
                            
            except asyncio.CancelledError:
                log.info("WebSocket loop cancelled")
                break
            except Exception as e:
                self.ws_healthy = False
                error_name = type(e).__name__
                
                # Check for specific HTTP status codes
                if hasattr(e, 'status_code'):
                    status = e.status_code
                    log.error(f"WebSocket rejected with HTTP {status}: {e}")
                    if status in (401, 403):
                        log.error(
                            f"Authentication error ({status}). "
                            "Check if API key is valid and WebSocket endpoint is accessible. "
                            "Falling back to polling."
                        )
                        # Don't retry auth errors quickly
                        await asyncio.sleep(300)  # 5 minutes
                        continue
                
                if self.running:
                    log.warning(f"WebSocket error ({error_name}): {e}")
                    log.info("Falling back to polling mechanism...")
                    await asyncio.sleep(30)  # Wait before retry
    
    async def _handle_ws_message(self, msg: dict):
        """Handle incoming WebSocket message."""
        msg_type = msg.get("type")
        data = msg.get("data", {})
        chat_id = data.get("chat_id")
        
        if not chat_id or chat_id not in self.tracked_chats:
            return
        
        log.debug(f"WS message: type={msg_type}, chat_id={chat_id}")
        
        if msg_type == "CHAT_COMPLETED":
            log.info(f"[WebSocket] CHAT_COMPLETED received for {chat_id}")
            await self._handle_completion(chat_id)
        
        elif msg_type == "CHAT_STREAM_CHUNK":
            inner_type = data.get("message_type")
            
            if inner_type == "AGENT_UPDATE":
                update_text = data.get("text", "").strip()
                if update_text:
                    self._collect_update(chat_id, update_text)
    
    # =========================================================================
    # Fallback Polling (when WebSocket fails)
    # =========================================================================
    
    async def _fallback_poll_loop(self):
        """
        Fallback polling loop that checks chat status periodically.
        
        This ensures completion is detected even if WebSocket fails.
        Runs regardless of WebSocket status as a backup.
        """
        log.info(f"Fallback polling started (interval: {self.poll_interval}s)")
        
        while self.running:
            await asyncio.sleep(self.poll_interval)
            
            if not self.tracked_chats:
                continue
            
            # Log polling status
            ws_status = "healthy" if self.ws_healthy else "unhealthy/disconnected"
            log.debug(f"[Polling] Checking {len(self.tracked_chats)} chats (WS: {ws_status})")
            
            # Check each tracked chat
            for chat_id in list(self.tracked_chats.keys()):
                try:
                    status = self._get_chat_status(chat_id)
                    
                    if not status.get("is_operating", True):
                        log.info(f"[Polling] Chat {chat_id} completed, processing...")
                        await self._handle_completion(chat_id)
                    elif status.get("error_type"):
                        log.warning(f"[Polling] Chat {chat_id} has error: {status['error_type']}")
                        
                except Exception as e:
                    log.error(f"[Polling] Error checking {chat_id}: {e}")
    
    # =========================================================================
    # File Watcher
    # =========================================================================
    
    async def _file_watcher_loop(self):
        """
        Watch for new/modified chat tracking files.
        
        Uses polling instead of inotify for simplicity and cross-platform support.
        """
        known_files: dict[str, float] = {}  # filename → mtime
        
        while self.running:
            try:
                # Scan tracked directory
                current_files = {}
                for chat_file in self.state.tracked_dir.glob("*.json"):
                    mtime = chat_file.stat().st_mtime
                    current_files[chat_file.name] = mtime
                    
                    # Check if new or modified
                    if chat_file.name not in known_files:
                        # New file
                        await self._on_new_chat_file(chat_file)
                    elif known_files[chat_file.name] < mtime:
                        # Modified file
                        await self._on_chat_file_modified(chat_file)
                
                known_files = current_files
                
            except Exception as e:
                log.error(f"File watcher error: {e}")
            
            await asyncio.sleep(1)  # Poll every second
    
    async def _on_new_chat_file(self, file_path: Path):
        """Handle new chat tracking file."""
        try:
            chat = TrackedChat.from_file(file_path)
            
            if chat.chat_id in self.tracked_chats:
                # Already tracking - this might be a modification
                return
            
            self.tracked_chats[chat.chat_id] = chat
            log.info(f"Now tracking: {chat.chat_id} ({len(chat.listeners)} listeners)")
            
            await self._maybe_connect_websocket()
            
        except Exception as e:
            log.error(f"Error processing new chat file {file_path}: {e}")
    
    async def _on_chat_file_modified(self, file_path: Path):
        """Handle chat file modification (e.g., new listener added)."""
        try:
            chat = TrackedChat.from_file(file_path)
            
            if chat.chat_id in self.tracked_chats:
                old_count = len(self.tracked_chats[chat.chat_id].listeners)
                new_count = len(chat.listeners)
                self.tracked_chats[chat.chat_id] = chat
                
                if new_count > old_count:
                    log.info(f"Updated listeners for {chat.chat_id}: {old_count} → {new_count}")
            
        except Exception as e:
            log.error(f"Error processing modified chat file {file_path}: {e}")
    
    async def _remove_chat(self, chat_id: str):
        """Remove chat from tracking."""
        self._clear_interim_state(chat_id)
        self.tracked_chats.pop(chat_id, None)
        self.state.remove_tracked(chat_id)
        log.info(f"Removed from tracking: {chat_id}")
        await self._maybe_disconnect_websocket()
    
    # =========================================================================
    # CellCog API
    # =========================================================================
    
    def _get_sdk_version(self) -> str:
        """Get SDK version for headers."""
        try:
            from .. import __version__
            return __version__
        except Exception:
            return "unknown"
    
    def _get_request_headers(self) -> dict:
        """Get headers for CellCog API requests."""
        return {
            "X-API-Key": self.api_key,
            "X-CellCog-Python-SDK-Version": self._get_sdk_version()
        }
    
    def _get_chat_status(self, chat_id: str) -> dict:
        """Get chat status from CellCog API."""
        resp = requests.get(
            f"{self.api_base_url}/cellcog/chat/{chat_id}",
            headers=self._get_request_headers(),
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "is_operating": data.get("operating", False),
            "name": data.get("name", ""),
            "error_type": (
                "security_threat" if data.get("is_security_threat") else
                "out_of_memory" if data.get("is_out_of_memory") else
                None
            )
        }
    
    def _get_chat_history(self, chat_id: str) -> dict:
        """Get chat history from CellCog API."""
        resp = requests.get(
            f"{self.api_base_url}/cellcog/chat/{chat_id}/history",
            headers=self._get_request_headers(),
            timeout=60
        )
        resp.raise_for_status()
        return resp.json()
    
    # =========================================================================
    # Shutdown
    # =========================================================================
    
    async def _shutdown(self):
        """Clean shutdown - cancel tasks but preserve state files."""
        self.running = False
        
        # Cancel interim updates task
        if self.interim_task:
            self.interim_task.cancel()
            try:
                await self.interim_task
            except asyncio.CancelledError:
                pass
        
        # Cancel polling
        if self.poll_task:
            self.poll_task.cancel()
            try:
                await self.poll_task
            except asyncio.CancelledError:
                pass
        
        # Cancel file watcher
        if self.watcher_task:
            self.watcher_task.cancel()
            try:
                await self.watcher_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect WebSocket
        await self._maybe_disconnect_websocket()


def run_daemon():
    """
    Entry point for running daemon as a script.
    
    Usage: python -m cellcog.daemon.main [api_key] [api_base_url]
    
    If no arguments provided, loads from ~/.openclaw/cellcog.json
    """
    # Setup logging
    log_file = Path("~/.cellcog/daemon.log").expanduser()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    # Get API key
    if len(sys.argv) >= 2:
        api_key = sys.argv[1]
        api_base_url = sys.argv[2] if len(sys.argv) >= 3 else "https://cellcog.ai/api"
    else:
        # Load from config
        from ..config import Config
        config = Config()
        if not config.api_key:
            print("Error: No API key provided and none found in config.", file=sys.stderr)
            print("Usage: python -m cellcog.daemon.main <api_key> [api_base_url]", file=sys.stderr)
            sys.exit(1)
        api_key = config.api_key
        api_base_url = config.api_base_url
    
    log.info(f"Starting daemon with API base URL: {api_base_url}")
    log.info(f"API key: {api_key[:10]}...")
    
    # Create daemon
    daemon = CellCogDaemon(api_key, api_base_url)
    
    # Handle shutdown signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def signal_handler():
        log.info("Received shutdown signal")
        asyncio.create_task(daemon._shutdown())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    # Write PID file
    pid_file = Path("~/.cellcog/daemon.pid").expanduser()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))
    log.info(f"Daemon PID: {os.getpid()}")
    
    try:
        loop.run_until_complete(daemon.run())
    finally:
        # Cleanup PID file
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        loop.close()


if __name__ == "__main__":
    run_daemon()
