"""
CellCog SDK File Processing.

Handles transparent translation between OpenClaw local paths and CellCog blob storage.
"""

import mimetypes
import os
import re
from pathlib import Path
from typing import Optional

import requests

from .config import Config
from .exceptions import FileDownloadError, FileUploadError


class FileProcessor:
    """
    Handles file upload/download and path translation for CellCog SDK.

    Key responsibilities:
    - Upload local files referenced in SHOW_FILE tags
    - Add external_local_path attribute to track original paths
    - Transform GENERATE_FILE tags to include external_local_path
    - Download files from CellCog responses to specified locations
    - Transform message content between local paths and blob names
    - Auto-download files without external_local_path to ~/.cellcog/chats/{chat_id}/
    - Skip downloading files for already-seen messages (optimization)
    """

    def __init__(self, config: Config):
        self.config = config
        self.default_download_dir = Path("~/.cellcog/chats").expanduser()

    def transform_outgoing(self, message: str) -> tuple[str, list]:
        """
        Transform outgoing message before sending to CellCog.

        Operations:
        1. Find SHOW_FILE tags with local paths → upload and add external_local_path
        2. Find GENERATE_FILE tags → transform to include external_local_path with empty content

        Args:
            message: Original message with local file paths

        Returns:
            (transformed_message, list_of_uploaded_files)
            where each uploaded file is {"local": str, "blob": str}
        """
        uploaded = []

        def replace_show_file(match):
            attrs = match.group(1)
            file_path = match.group(2).strip()

            # Only process if it's a local path that exists
            if file_path.startswith("/") and os.path.exists(file_path):
                try:
                    blob_name = self._upload_file(file_path)
                    uploaded.append({"local": file_path, "blob": blob_name})

                    # Add external_local_path to preserve original path for history restoration
                    return f'<SHOW_FILE external_local_path="{file_path}">{blob_name}</SHOW_FILE>'
                except FileUploadError:
                    # If upload fails, keep original (will fail on CellCog side)
                    return match.group(0)

            # Not a local file - return unchanged
            return match.group(0)

        def replace_generate_file(match):
            attrs = match.group(1)
            file_path = match.group(2).strip()

            # Transform GENERATE_FILE to have external_local_path with empty content
            # This signals to CellCog agent where the file should end up on client's machine
            return f'<GENERATE_FILE external_local_path="{file_path}"></GENERATE_FILE>'

        # Process SHOW_FILE tags - upload local files and track original path
        transformed = re.sub(
            r"<SHOW_FILE([^>]*)>(.*?)</SHOW_FILE>",
            replace_show_file,
            message,
            flags=re.DOTALL,
        )

        # Process GENERATE_FILE tags - add external_local_path attribute
        transformed = re.sub(
            r"<GENERATE_FILE([^>]*)>(.*?)</GENERATE_FILE>",
            replace_generate_file,
            transformed,
            flags=re.DOTALL,
        )

        return transformed, uploaded

    def transform_incoming_history(
        self,
        messages: list,
        blob_name_to_url: dict,
        chat_id: str,
        skip_download_until_index: int = -1,
    ) -> list:
        """
        Transform incoming chat history from CellCog.

        Operations:
        1. For ALL messages: Replace blob_names with local paths
        2. For CellCog messages with index > skip_download_until_index: Download files
        3. Auto-generate download paths for files without external_local_path

        Args:
            messages: List of message dicts from CellCog API
            blob_name_to_url: Mapping of blob_name to URL data
            chat_id: Chat ID (for default download location)
            skip_download_until_index: Don't download files for messages at or below this index.
                                       Files for these messages were already downloaded in previous calls.
                                       Default -1 means download all files.

        Returns:
            List of transformed messages with local paths in all SHOW_FILE tags
            Format: [{"role": "cellcog"|"openclaw", "content": str, "created_at": str}]
        """
        transformed_messages = []

        for msg_index, msg in enumerate(messages):
            content = msg.get("content", "")
            message_from = msg.get("messageFrom", "")
            is_cellcog_message = message_from == "CellCog"

            # Only download files for messages we haven't seen yet
            should_download = msg_index > skip_download_until_index

            def replace_show_file(match):
                attrs = match.group(1)
                blob_name = match.group(2).strip()

                # Extract external_local_path attribute if present
                external_local_path_match = re.search(r'external_local_path="([^"]*)"', attrs)

                if external_local_path_match:
                    # User specified path via GENERATE_FILE (or SDK uploaded file)
                    local_path = external_local_path_match.group(1)
                else:
                    # Auto-generate download path
                    local_path = self._generate_auto_download_path(blob_name, chat_id)

                # Only download for CellCog messages we haven't seen yet
                if is_cellcog_message and should_download and blob_name in blob_name_to_url:
                    url_data = blob_name_to_url[blob_name]
                    try:
                        self._download_file(url_data["url"], local_path)
                    except FileDownloadError:
                        # If download fails, still return the path
                        # (file just won't exist)
                        pass

                # Return with resolved local path (remove blob_name)
                return f"<SHOW_FILE>{local_path}</SHOW_FILE>"

            transformed_content = re.sub(
                r"<SHOW_FILE([^>]*)>(.*?)</SHOW_FILE>",
                replace_show_file,
                content,
                flags=re.DOTALL,
            )

            transformed_messages.append(
                {
                    "role": "cellcog" if is_cellcog_message else "openclaw",
                    "content": transformed_content,
                    "created_at": msg.get("createdAt"),
                }
            )

        return transformed_messages

    def _generate_auto_download_path(self, blob_name: str, chat_id: str) -> str:
        """
        Generate download path for files without external_local_path.

        Handles two blob_name formats:
        - {chat_id}//home/app/path/to/file.ext  (double slash = from CellCog's /home/app/)
        - {chat_id}/path/to/file.ext             (single slash = relative path)

        Args:
            blob_name: Full blob name from CellCog
            chat_id: Chat ID for organizing downloads

        Returns:
            Local path like ~/.cellcog/chats/{chat_id}/{path}
        """
        if "/" not in blob_name:
            # Malformed - use blob_name as filename
            return str(self.default_download_dir / chat_id / blob_name)

        # Remove chat_id prefix (everything up to first /)
        path_part = blob_name.split("/", 1)[1]

        # Handle double slash (//home/app/ → remove /home/app prefix)
        if path_part.startswith("/home/app/"):
            path_part = path_part[10:]  # Remove '/home/app/'
        elif path_part.startswith("/"):
            path_part = path_part[1:]  # Remove leading /

        # Construct local path
        local_path = self.default_download_dir / chat_id / path_part

        return str(local_path)

    def _upload_file(self, local_path: str) -> str:
        """
        Upload local file to CellCog.

        Args:
            local_path: Path to local file

        Returns:
            blob_name from CellCog

        Raises:
            FileUploadError: If upload fails
        """
        path = Path(local_path)

        if not path.exists():
            raise FileUploadError(f"File not found: {local_path}")

        mime_type = self._get_mime_type(path)
        file_size = path.stat().st_size

        # Step 1: Request upload URL
        try:
            resp = requests.post(
                f"{self.config.api_base_url}/files/request-upload",
                headers=self.config.get_request_headers(),
                json={
                    "filename": path.name,
                    "file_size": file_size,
                    "mime_type": mime_type,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise FileUploadError(f"Failed to get upload URL: {e}")

        # Step 2: Upload to signed URL
        try:
            with open(local_path, "rb") as f:
                put_resp = requests.put(
                    data["upload_url"],
                    data=f,
                    headers={"Content-Type": mime_type},
                    timeout=300,  # 5 min timeout for large files
                )
                put_resp.raise_for_status()
        except requests.RequestException as e:
            raise FileUploadError(f"Failed to upload file: {e}")

        # Step 3: Confirm upload
        try:
            confirm_resp = requests.post(
                f"{self.config.api_base_url}/files/confirm-upload/{data['file_id']}",
                headers=self.config.get_request_headers(),
                timeout=30,
            )
            confirm_resp.raise_for_status()
        except requests.RequestException as e:
            raise FileUploadError(f"Failed to confirm upload: {e}")

        return data["blob_name"]

    def _download_file(self, url: str, local_path: str) -> None:
        """
        Download file from URL to local path.

        Args:
            url: Signed URL to download from
            local_path: Local path to save file

        Raises:
            FileDownloadError: If download fails
        """
        try:
            # Create parent directories
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            # Download with streaming for large files
            resp = requests.get(url, stream=True, timeout=300)
            resp.raise_for_status()

            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

        except requests.RequestException as e:
            raise FileDownloadError(f"Failed to download file: {e}")
        except IOError as e:
            raise FileDownloadError(f"Failed to save file: {e}")

    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type for a file."""
        mime_type, _ = mimetypes.guess_type(str(path))
        return mime_type or "application/octet-stream"
