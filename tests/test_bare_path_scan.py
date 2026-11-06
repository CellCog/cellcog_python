"""Standalone test: the bare-path auto-upload scans only text OUTSIDE existing file tags (Nov 6 2026).

A Windows path kept in a tag attribute (external_local_path="C:/Users/me/a.webp") contains "/Users/me/a.webp".
The old scan matched it and nested a second tag inside the attribute, so the chat rendered broken tag text.
Runs on any OS: os.path.exists/isfile and the upload are stubbed, no network.

Run: python3 tests/test_bare_path_scan.py
"""

import re
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cellcog.files as files_mod  # noqa: E402
from cellcog.config import Config  # noqa: E402
from cellcog.files import FileProcessor  # noqa: E402

FT = "SHOW_" + "FILE"
failed = 0


def check(label, ok, detail=""):
    global failed
    if ok:
        print(f"[OK ] {label}")
    else:
        failed += 1
        print(f"[FAIL] {label}\n       {detail}")


def fake_exists(p):
    return "Users/me/" in str(p)


fp = FileProcessor(Config())
counter = {"n": 0}


def fake_upload(path):
    counter["n"] += 1
    return f"blob{counter['n']}/{Path(str(path).replace(chr(92), '/')).name}"


with mock.patch.object(files_mod.os.path, "exists", fake_exists), \
        mock.patch.object(files_mod.os.path, "isfile", fake_exists), \
        mock.patch.object(fp, "_upload_file", fake_upload):
    msg = f"Hero: <{FT}>C:/Users/me/a.webp</{FT}>\nAlso see /Users/me/b.png please."
    out, uploaded = fp.transform_outgoing(msg)

tags = re.findall(rf"<{FT}[^>]*>.*?</{FT}>", out, re.S)
check("exactly two file tags (the tagged one + the bare one)", len(tags) == 2, out)
check("no tag nested inside another tag's attribute", f'"C:<{FT}' not in out and out.count(f"<{FT}") == 2, out)
check("the Windows path stays intact in the attribute", 'external_local_path="C:/Users/me/a.webp"' in out, out)
check("the bare path in prose is still auto-uploaded", 'external_local_path="/Users/me/b.png"' in out, out)
check("two uploads, not three", len(uploaded) == 2, uploaded)

# FAIL control: the old whole-string scan DOES match inside the tag attribute (the reported bug).
old_re = re.compile(r"(?<![<\"=])(?:/[\w.+\-][\w.+\-/]*|~/[\w.+\-][\w.+\-/]*)")
first_tag = tags[0] if tags else ""
check("CONTROL: the old scan matches a path inside the tag", bool(old_re.search(first_tag)), first_tag)

print("\n" + ("ALL PASS" if failed == 0 else f"{failed} FAILURE(S)"))
sys.exit(1 if failed else 0)
