"""
CellCog SDK Message Processor.

Processes chat history for delivery, handling:
- Seen index tracking per session
- File downloads (only for unseen CellCog messages)
- Message formatting
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .message_formatter import (
    format_messages_for_delivery,
    session_key_to_filename,
)

if TYPE_CHECKING:
    from .config import Config
    from .files import FileProcessor


@dataclass
class ProcessedResult:
    """Result of message processing."""
    
    formatted_output: str
    """Formatted messages ready for delivery."""
    
    delivered_count: int
    """Number of messages processed/delivered."""
    
    downloaded_files: list[str]
    """List of local file paths that were downloaded."""
    
    last_seen_index: int
    """Index of the last processed message."""
    
    is_operating: bool
    """Whether the chat is still operating."""


class MessageProcessor:
    """
    Processes chat history for delivery.
    
    Handles:
    - Fetching and transforming messages
    - Seen index tracking per session per chat
    - File downloads (only for unseen CellCog messages)
    - Message formatting for delivery
    """
    
    def __init__(self, config: "Config", file_processor: "FileProcessor"):
        """
        Initialize message processor.
        
        Args:
            config: SDK configuration
            file_processor: File processor for downloads
        """
        self.config = config
        self.files = file_processor
        self.chats_dir = Path("~/.cellcog/chats").expanduser()
    
    def process_for_delivery(
        self,
        chat_id: str,
        session_key: str,
        history: dict,
        is_operating: bool
    ) -> ProcessedResult:
        """
        Process chat history for delivery to a specific session.
        
        Respects seen indices - only processes unseen messages.
        Downloads files only for unseen CellCog messages.
        Updates seen index after processing.
        
        Args:
            chat_id: Chat ID
            session_key: Session key for seen index tracking
            history: Raw history from API {"messages": [...], "blob_name_to_url": {...}}
            is_operating: Whether chat is still operating
        
        Returns:
            ProcessedResult with formatted output and metadata
        """
        # Load seen index for this session
        seen_index = self._load_seen_index(chat_id, session_key)
        
        # Transform messages (downloads files for unseen CellCog messages)
        transformed = self.files.transform_incoming_history(
            messages=history["messages"],
            blob_name_to_url=history.get("blob_name_to_url", {}),
            chat_id=chat_id,
            skip_download_until_index=seen_index
        )
        
        # Format for delivery (only unseen messages)
        start_index = seen_index + 1
        formatted_output, last_index = format_messages_for_delivery(
            messages=transformed,
            chat_id=chat_id,
            is_operating=is_operating,
            start_index=start_index
        )
        
        # Count delivered messages
        delivered_count = max(0, last_index - seen_index) if last_index >= start_index else 0
        
        # Update seen index
        if last_index > seen_index:
            self._save_seen_index(chat_id, session_key, last_index)
        
        # Extract downloaded file paths from unseen CellCog messages
        downloaded_files = self._extract_local_paths(transformed, start_index)
        
        return ProcessedResult(
            formatted_output=formatted_output,
            delivered_count=delivered_count,
            downloaded_files=downloaded_files,
            last_seen_index=last_index if last_index >= 0 else seen_index,
            is_operating=is_operating
        )
    
    def process_full_history(
        self,
        chat_id: str,
        history: dict,
        is_operating: bool,
        download_files: bool = True
    ) -> ProcessedResult:
        """
        Process full chat history (ignores seen indices).
        
        Used by get_history() for manual inspection.
        Does NOT update seen indices.
        
        Args:
            chat_id: Chat ID
            history: Raw history from API
            is_operating: Whether chat is still operating
            download_files: Whether to download files
        
        Returns:
            ProcessedResult with full formatted history
        """
        # If not downloading, skip all downloads
        skip_download = len(history["messages"]) if not download_files else -1
        
        # Transform all messages
        transformed = self.files.transform_incoming_history(
            messages=history["messages"],
            blob_name_to_url=history.get("blob_name_to_url", {}),
            chat_id=chat_id,
            skip_download_until_index=skip_download
        )
        
        # Format ALL messages (start from 0)
        formatted_output, last_index = format_messages_for_delivery(
            messages=transformed,
            chat_id=chat_id,
            is_operating=is_operating,
            start_index=0
        )
        
        # Extract file paths if downloaded
        downloaded_files = self._extract_local_paths(transformed, 0) if download_files else []
        
        return ProcessedResult(
            formatted_output=formatted_output,
            delivered_count=len(transformed),
            downloaded_files=downloaded_files,
            last_seen_index=last_index,
            is_operating=is_operating
        )
    
    def _load_seen_index(self, chat_id: str, session_key: str) -> int:
        """
        Load last seen message index for session.
        
        Args:
            chat_id: Chat ID
            session_key: Session key
            
        Returns:
            Last seen index, or -1 if never seen
        """
        safe_name = session_key_to_filename(session_key)
        index_path = self.chats_dir / chat_id / ".seen_indices" / safe_name
        try:
            if index_path.exists():
                return int(index_path.read_text().strip())
        except (ValueError, IOError):
            pass
        return -1
    
    def _save_seen_index(self, chat_id: str, session_key: str, index: int) -> None:
        """
        Save last seen message index for session.
        
        Args:
            chat_id: Chat ID
            session_key: Session key
            index: Last seen index
        """
        safe_name = session_key_to_filename(session_key)
        index_path = self.chats_dir / chat_id / ".seen_indices" / safe_name
        try:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(str(index))
        except IOError:
            pass
    
    def _extract_local_paths(
        self,
        messages: list[dict],
        start_index: int
    ) -> list[str]:
        """
        Extract local file paths from transformed messages.
        
        Only extracts from CellCog messages starting at start_index.
        
        Args:
            messages: Transformed messages with local paths
            start_index: First index to extract from
            
        Returns:
            List of local file paths
        """
        paths = []
        for i, msg in enumerate(messages):
            if i < start_index:
                continue
            if msg["role"] != "cellcog":
                continue
            
            # Find SHOW_FILE tags with local paths
            for match in re.finditer(r'<SHOW_FILE>([^<]+)</SHOW_FILE>', msg["content"]):
                path = match.group(1).strip()
                if path and path.startswith("/"):
                    paths.append(path)
        
        return paths
