"""
CellCog Daemon State Management.

Data classes for tracking chats and listeners.
File-based persistence for resilience across restarts.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class Listener:
    """
    A session listening for updates on a chat.
    
    Attributes:
        session_key: OpenClaw session key (e.g., "agent:main:main")
        gateway_url: OpenClaw Gateway URL for notifications
        gateway_auth_source: How to get auth token (e.g., "env:OPENCLAW_GATEWAY_TOKEN")
        task_label: Human-readable label for notifications
        added_at: When this listener was added
    """
    session_key: str
    gateway_url: str
    gateway_auth_source: str
    task_label: str
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Listener":
        """Create from dictionary."""
        return cls(
            session_key=data["session_key"],
            gateway_url=data["gateway_url"],
            gateway_auth_source=data["gateway_auth_source"],
            task_label=data["task_label"],
            added_at=data.get("added_at", datetime.now(timezone.utc).isoformat())
        )


@dataclass
class TrackedChat:
    """
    A chat being tracked by the daemon.
    
    Stored as JSON file at ~/.cellcog/tracked_chats/{chat_id}.json
    
    Attributes:
        chat_id: CellCog chat ID
        listeners: List of sessions listening for updates
        created_at: When tracking started
        last_verified_at: Last time we verified chat status
    """
    chat_id: str
    listeners: list[Listener]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "chat_id": self.chat_id,
            "listeners": [l.to_dict() for l in self.listeners],
            "created_at": self.created_at,
            "last_verified_at": self.last_verified_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TrackedChat":
        """Create from dictionary."""
        return cls(
            chat_id=data["chat_id"],
            listeners=[Listener.from_dict(l) for l in data.get("listeners", [])],
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            last_verified_at=data.get("last_verified_at", datetime.now(timezone.utc).isoformat())
        )
    
    @classmethod
    def from_file(cls, file_path: Path) -> "TrackedChat":
        """Load from JSON file."""
        data = json.loads(file_path.read_text())
        return cls.from_dict(data)
    
    def save_to_file(self, tracked_dir: Path) -> None:
        """Save to JSON file."""
        file_path = tracked_dir / f"{self.chat_id}.json"
        file_path.write_text(json.dumps(self.to_dict(), indent=2))
    
    def add_listener(self, listener: Listener) -> bool:
        """
        Add a listener if not already present.
        
        Returns:
            True if listener was added, False if already present
        """
        existing_keys = {l.session_key for l in self.listeners}
        if listener.session_key not in existing_keys:
            self.listeners.append(listener)
            return True
        return False
    
    def update_verified_at(self) -> None:
        """Update last_verified_at to now."""
        self.last_verified_at = datetime.now(timezone.utc).isoformat()


class StateManager:
    """
    Manages persistent state for the daemon.
    
    State is stored in files for resilience:
    - ~/.cellcog/tracked_chats/{chat_id}.json - One file per tracked chat
    - ~/.cellcog/chats/{chat_id}/.seen_indices/{session_key} - Seen message indices
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize state manager.
        
        Args:
            base_dir: Base directory for state files. Defaults to ~/.cellcog
        """
        self.base_dir = base_dir or Path("~/.cellcog").expanduser()
        self.tracked_dir = self.base_dir / "tracked_chats"
        self.chats_dir = self.base_dir / "chats"
        
        # Ensure directories exist
        self.tracked_dir.mkdir(parents=True, exist_ok=True)
        self.chats_dir.mkdir(parents=True, exist_ok=True)
    
    def load_all_tracked(self) -> dict[str, TrackedChat]:
        """
        Load all tracked chats from disk.
        
        Returns:
            Dictionary of chat_id → TrackedChat
        """
        tracked = {}
        for chat_file in self.tracked_dir.glob("*.json"):
            try:
                chat = TrackedChat.from_file(chat_file)
                tracked[chat.chat_id] = chat
            except Exception as e:
                # Log error but continue loading others
                print(f"Error loading {chat_file}: {e}")
        return tracked
    
    def save_tracked(self, chat: TrackedChat) -> None:
        """Save a tracked chat to disk."""
        chat.save_to_file(self.tracked_dir)
    
    def remove_tracked(self, chat_id: str) -> None:
        """Remove a tracked chat file."""
        file_path = self.tracked_dir / f"{chat_id}.json"
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass
    
    def get_tracked_file_path(self, chat_id: str) -> Path:
        """Get path to tracking file for a chat."""
        return self.tracked_dir / f"{chat_id}.json"
