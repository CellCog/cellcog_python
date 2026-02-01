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
    - Download files from CellCog responses to specified locations
    - Transform message content between local paths and blob names
    """

    def __init__(self, config: Config):
        self.config = config
        self.default_download_dir = Path("~/.openclaw/cellcog_files").expanduser()

    def transform_outgoing(self, message: str) -> tuple[str, list]:
        """
        Transform outgoing message before sending to CellCog.

        Operations:
        1. Find SHOW_FILE tags with local paths
        2. Upload each local file to CellCog
        3. Replace local path with blob_name, add external_local_path attribute
        4. Keep GENERATE_FILE tags unchanged (passed to CellCog agent)

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

        # Process SHOW_FILE tags - upload local files and track original path
        transformed = re.sub(
            r"<SHOW_FILE([^>]*)>(.*?)</SHOW_FILE>",
            replace_show_file,
            message,
            flags=re.DOTALL,
        )

        # GENERATE_FILE passes through unchanged
        # CellCog agent will read it and use the path for external_local_path in response

        return transformed, uploaded

    def transform_incoming_history(self, messages: list, blob_name_to_url: dict, chat_id: str) -> list:
        """
        Transform incoming chat history from CellCog.

        Operations:
        1. For ALL messages: Replace blob_names with external_local_path (local paths)
        2. For CellCog messages ONLY: Download files before replacing

        Args:
            messages: List of message dicts from CellCog API
            blob_name_to_url: Mapping of blob_name to URL data
            chat_id: Chat ID (for default download location)

        Returns:
            List of transformed messages with local paths in all SHOW_FILE tags
        """
        transformed_messages = []

        for msg in messages:
            content = msg.get("content", "")
            message_from = msg.get("messageFrom", "")
            is_user_message = message_from != "CellCog"

            def replace_show_file(match):
                attrs = match.group(1)
                blob_name = match.group(2).strip()

                # Extract external_local_path attribute
                external_local_path_match = re.search(r'external_local_path="([^"]*)"', attrs)

                if external_local_path_match:
                    external_local_path = external_local_path_match.group(1)
                elif blob_name in blob_name_to_url:
                    # No external_local_path - use default download location
                    url_data = blob_name_to_url[blob_name]
                    filename = url_data.get("filename") or blob_name.split("/")[-1]
                    external_local_path = str(self.default_download_dir / chat_id / filename)
                else:
                    # No URL data available - keep as-is
                    return match.group(0)

                # For CellCog messages: download the file first
                if not is_user_message and blob_name in blob_name_to_url:
                    url_data = blob_name_to_url[blob_name]
                    try:
                        self._download_file(url_data["url"], external_local_path)
                    except FileDownloadError:
                        # If download fails, still return the path
                        # (file just won't exist)
                        pass

                # For ALL messages: restore the original local path
                return f"<SHOW_FILE>{external_local_path}</SHOW_FILE>"

            transformed_content = re.sub(
                r"<SHOW_FILE([^>]*)>(.*?)</SHOW_FILE>",
                replace_show_file,
                content,
                flags=re.DOTALL,
            )

            transformed_messages.append(
                {
                    "from": "user" if is_user_message else "cellcog",
                    "content": transformed_content,
                    "created_at": msg.get("createdAt"),
                }
            )

        return transformed_messages

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
                headers={"Authorization": f"Bearer {self.config.api_key}"},
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
                headers={"Authorization": f"Bearer {self.config.api_key}"},
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
