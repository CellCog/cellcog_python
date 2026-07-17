"""Standalone tests for SDK gs:// SHOW_FILE handling.

Run: python3 tests/test_gs_url_handling.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cellcog.config import Config
from cellcog.files import FileProcessor

CHAT = "687a8aa4fcf12067f5a5b9e0"
failed = 0


def check(label, got, want):
    global failed
    ok = got == want
    if not ok:
        failed += 1
        print(f"[FAIL] {label}\n       got : {got}\n       want: {want}")
    else:
        print(f"[OK ] {label}")


fp = FileProcessor(Config())

# --- download-path derivation strips gs://bucket/ then chat_id ---
# Real CellCog blobs from /home/app are {chat_id}//home/app/... (double slash:
# {chat_id}/ + the absolute /home/app/... path). The /home/app/ prefix is stripped.
p = fp._generate_auto_download_path(f"gs://cellcog_files/{CHAT}//home/app/out.png", CHAT)
check("gs:// download path strips scheme+bucket+chat+/home/app",
      p, str(fp.default_download_dir / CHAT / "out.png"))

# A non-/home/app relative path keeps its sub-path after the chat_id.
p = fp._generate_auto_download_path(f"gs://cellcog_files/{CHAT}/sub/dir/file.pdf", CHAT)
check("gs:// download path nested",
      p, str(fp.default_download_dir / CHAT / "sub/dir/file.pdf"))

# --- legacy bare blob still works (back-compat), double-slash /home/app form ---
p = fp._generate_auto_download_path(f"{CHAT}//home/app/out.png", CHAT)
check("legacy bare blob still derives correctly",
      p, str(fp.default_download_dir / CHAT / "out.png"))

# --- outgoing: gs:// is left untouched (not treated as missing local file) ---
msg = f"Here <SHOW_FILE>gs://cellcog_files/{CHAT}/a.png</SHOW_FILE> done"
transformed, uploaded = fp.transform_outgoing(msg)
check("outgoing gs:// unchanged", transformed, msg)
check("outgoing gs:// nothing uploaded", uploaded, [])

print("\n" + ("ALL PASS" if failed == 0 else f"{failed} FAILURE(S)"))
sys.exit(1 if failed else 0)
