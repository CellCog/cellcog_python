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
    - Upload local files referenced in SHOW_FILE tags (with early failure on missing files)
    - Add external_local_path attribute to track original paths for outgoing uploads
    - Transform GENERATE_FILE tags to include external_local_path for deterministic output paths
    - Download files from CellCog responses (to external_local_path if specified, else ~/.cellcog/chats/)
    - Transform message content between local paths and blob names
    - Skip downloading files for already-seen messages (optimization)

    Security:
    - Outgoing: Raises FileUploadError if SHOW_FILE references missing local files
    - Incoming: Uses external_local_path for download destination when present (agent-specified),
      otherwise downloads to safe ~/.cellcog/chats/{chat_id}/ directory
    """

    def __init__(self, config: Config):
        self.config = config
        self.default_download_dir = Path("~/.cellcog/chats").expanduser()

    def transform_outgoing(self, message: str) -> tuple[str, list]:
        """
        Transform outgoing message before sending to CellCog.

        Operations:
        1. Find SHOW_FILE tags with local paths → upload and add external_local_path
        2. Find GENERATE_FILE tags → transform to include external_local_path
        3. Auto-detect bare file paths (starting with / or ~/) and upload them
        4. Fail early if any SHOW_FILE references missing local files (prevents broken chats)

        Args:
            message: Original message with local file paths

        Returns:
            (transformed_message, list_of_uploaded_files)
            where each uploaded file is {"local": str, "blob": str}

        Raises:
            FileUploadError: If any SHOW_FILE references local files that don't exist.
                This prevents creating broken chats that waste credits.
        """
        uploaded = []
        missing_files = []

        def replace_show_file(match):
            attrs = match.group(1)
            file_path = match.group(2).strip()

            # Skip empty paths and URLs — not local files
            if not file_path or file_path.startswith(("http://", "https://")):
                return match.group(0)

            # Cross-platform local file detection:
            # Instead of pattern-matching path formats (Unix /, Windows C:\, UNC \\, relative),
            # we simply ask the OS if the file exists. This handles all platforms and path styles
            # including relative paths without a leading slash.
            try:
                if os.path.exists(file_path):
                    try:
                        blob_name = self._upload_file(file_path)
                        uploaded.append({"local": file_path, "blob": blob_name})

                        # Add external_local_path to preserve original path for history restoration
                        return f'<SHOW_FILE external_local_path="{file_path}">{blob_name}</SHOW_FILE>'
                    except FileUploadError:
                        # If upload fails, keep original (will fail on CellCog side)
                        return match.group(0)
            except (OSError, ValueError):
                # os.path.exists() can raise on severely malformed paths
                pass

            # File path looks local but doesn't exist — track for early failure
            missing_files.append(file_path)
            return match.group(0)

        # Process SHOW_FILE tags - upload local files and track original path
        transformed = re.sub(
            r"<SHOW_FILE([^>]*)>(.*?)</SHOW_FILE>",
            replace_show_file,
            message,
            flags=re.DOTALL,
        )

        # Process GENERATE_FILE tags — add external_local_path attribute
        # so CellCog agent knows where the client wants output files stored
        def replace_generate_file(match):
            file_path = match.group(2).strip()
            return f'<GENERATE_FILE external_local_path="{file_path}"></GENERATE_FILE>'

        transformed = re.sub(
            r"<GENERATE_FILE([^>]*)>(.*?)</GENERATE_FILE>",
            replace_generate_file,
            transformed,
            flags=re.DOTALL,
        )

        # Auto-detect bare file paths not wrapped in SHOW_FILE or GENERATE_FILE tags.
        # Many agents send local paths as plain text without tags — this catches those
        # and auto-uploads them so CellCog can access the file contents.
        _SYSTEM_PREFIXES = (
            "/usr/", "/etc/", "/bin/", "/sbin/", "/lib/",
            "/var/", "/tmp/", "/sys/", "/proc/", "/dev/",
            "/opt/", "/boot/",
        )

        # Collect paths already handled by SHOW_FILE/GENERATE_FILE so we skip them
        already_handled = set()
        for m in re.finditer(r"<(?:SHOW_FILE|GENERATE_FILE)[^>]*>([^<]*)</(?:SHOW_FILE|GENERATE_FILE)>", transformed):
            already_handled.add(m.group(1).strip())
        # Also track uploaded paths
        for u in uploaded:
            already_handled.add(u["local"])

        def _auto_upload_bare_path(match):
            raw_path = match.group(0)

            # Expand ~ to absolute path for filesystem check
            check_path = os.path.expanduser(raw_path)

            # Skip if already handled by SHOW_FILE/GENERATE_FILE
            if raw_path in already_handled or check_path in already_handled:
                return raw_path

            # Skip system paths
            if check_path.startswith(_SYSTEM_PREFIXES):
                return raw_path

            # Only auto-upload if it exists as a regular file (not directory)
            try:
                if os.path.isfile(check_path):
                    try:
                        blob_name = self._upload_file(check_path)
                        uploaded.append({"local": check_path, "blob": blob_name})
                        print(
                            f"[cellcog] Auto-detected and uploaded: {raw_path}",
                            file=__import__("sys").stderr,
                        )
                        return f'<SHOW_FILE external_local_path="{check_path}">{blob_name}</SHOW_FILE>'
                    except FileUploadError:
                        return raw_path  # Upload failed — leave as-is
            except (OSError, ValueError):
                pass

            return raw_path

        # Match paths starting with / or ~/ that contain at least one / separator
        # and are not already inside XML-like tags
        transformed = re.sub(
            r"(?<![<\"=])(?:/[\w.+\-][\w.+\-/]*|~/[\w.+\-][\w.+\-/]*)",
            _auto_upload_bare_path,
            transformed,
        )

        # Fail early if any SHOW_FILE-referenced local files are missing
        if missing_files:
            files_list = "\n".join(f"  - {path}" for path in missing_files)
            raise FileUploadError(
                f"Cannot upload {len(missing_files)} file(s) to CellCog — not found:\n"
                f"{files_list}\n\n"
                f"These files may exist on the user's machine but are not accessible "
                f"from the current environment. If running inside Docker, ensure the "
                f"file paths are mounted as volumes. If on WSL, ensure cross-filesystem "
                f"access is available."
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
        3. If external_local_path is present (from GENERATE_FILE), download to that path
        4. Otherwise, download to safe ~/.cellcog/chats/{chat_id}/ location

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

                # Check for external_local_path (from GENERATE_FILE flow)
                # If present, download to the agent-specified path
                external_path_match = re.search(
                    r'external_local_path="([^"]*)"', attrs
                )

                if external_path_match:
                    local_path = external_path_match.group(1)
                else:
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

                # Return with local path (remove blob_name and attributes)
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
        Generate safe download path under ~/.cellcog/chats/{chat_id}/.

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
