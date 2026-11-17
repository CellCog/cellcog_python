"""Tests for the storage fallback (CEL-3867): when storage.googleapis.com is unreachable, uploads and downloads go
through cellcog.ai, and a file that still fails is reported loudly. No network: requests calls are replaced.

Run: python3 tests/test_storage_fallback.py   (or pytest)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["CELLCOG_DISABLE_ERROR_REPORTS"] = "1"

import requests  # noqa: E402

from cellcog import files as F  # noqa: E402
from cellcog.exceptions import FileDownloadError, FileUploadError  # noqa: E402

API = "https://cellcog.ai/api"
STORAGE = "https://storage.googleapis.com/cellcog_files/blob?X-Goog-Signature=abc"
CALLS = []
PASS = FAIL = 0


def check(name, cond, note=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {note}")


class _Cfg:
    api_key = "test"
    api_base_url = API

    def get_request_headers(self):
        return {"X-API-Key": "test", "X-CellCog-Python-SDK-Version": "2.8.1"}


class _Resp:
    def __init__(self, status=200, payload=None, body=b""):
        self.status_code, self._payload, self._body = status, payload or {}, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=8192):
        yield self._body


def proxy_block(*a, **k):
    raise requests.exceptions.ProxyError("Unable to connect to proxy: Tunnel connection failed: 403 Forbidden")


def install(put_storage, get_storage=None, put_fallback=None, get_fallback=None):
    """Route each requests call by URL: storage vs cellcog.ai."""
    CALLS.clear()

    def post(url, **k):
        CALLS.append(("POST", url))
        if url.endswith("/files/request-upload"):
            return _Resp(payload={"file_id": "f1", "upload_url": STORAGE, "blob_name": "human_files/u/ref.png"})
        return _Resp(payload={"success": True})

    def put(url, **k):
        CALLS.append(("PUT", url))
        if url.startswith("https://storage.googleapis.com"):
            return put_storage(url, **k)
        return (put_fallback or (lambda *a, **kw: _Resp()))(url, **k)

    def get(url, **k):
        CALLS.append(("GET", url, k.get("params")))
        if url.startswith("https://storage.googleapis.com"):
            return (get_storage or proxy_block)(url, **k)
        return (get_fallback or (lambda *a, **kw: _Resp(body=b"via-cellcog")))(url, **k)

    F.requests.post, F.requests.put, F.requests.get = post, put, get


def tmpfile(size=100, name="ref.png"):
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.truncate(size)
    return p


def main():
    print("— upload —")
    install(lambda *a, **k: _Resp())
    fp = F.FileProcessor(_Cfg())
    blob = fp._upload_file(tmpfile())
    check("direct storage PUT works: no cellcog.ai byte upload (PASS control)",
          blob == "human_files/u/ref.png" and not any("upload-bytes" in c[1] for c in CALLS), str(CALLS))

    install(proxy_block)
    fp = F.FileProcessor(_Cfg())
    blob = fp._upload_file(tmpfile())
    check("a proxy-refused storage PUT falls back to /files/upload-bytes, then confirms",
          blob == "human_files/u/ref.png" and ("PUT", f"{API}/files/upload-bytes/f1") in CALLS
          and ("POST", f"{API}/files/confirm-upload/f1") in CALLS, str(CALLS))
    check("the run remembers the block", fp._storage_blocked is True)
    CALLS.clear()
    fp._upload_file(tmpfile())
    check("the next upload skips the direct storage attempt",
          not any(c[1].startswith("https://storage") for c in CALLS) and any("upload-bytes" in c[1] for c in CALLS), str(CALLS))

    install(lambda *a, **k: _Resp(status=403, payload={}))
    fp = F.FileProcessor(_Cfg())
    blob = fp._upload_file(tmpfile())
    check("a storage PUT answered 403 falls back to /files/upload-bytes, then confirms",
          blob == "human_files/u/ref.png" and ("PUT", f"{API}/files/upload-bytes/f1") in CALLS
          and ("POST", f"{API}/files/confirm-upload/f1") in CALLS, str(CALLS))
    check("a 403 answer is not remembered: the next upload tries storage first", fp._storage_blocked is False)

    install(lambda *a, **k: _Resp(status=404, payload={}))
    fp = F.FileProcessor(_Cfg())
    try:
        fp._upload_file(tmpfile()); err = ""
    except FileUploadError as e:
        err = str(e)
    check("[FAIL control] an HTTP 404 FROM storage is a real answer: no fallback, clear error",
          "HTTP 404" in err and not any("upload-bytes" in c[1] for c in CALLS) and "X-Goog-Signature" not in err, err)

    install(lambda *a, **k: _Resp(status=403, payload={}), put_fallback=lambda *a, **k: _Resp(status=500, payload={"detail": "boom"}))
    fp = F.FileProcessor(_Cfg())
    try:
        fp._upload_file(tmpfile()); err = ""
    except FileUploadError as e:
        err = str(e)
    check("[FAIL control] a 403 from storage AND a failing cellcog.ai route is an error, with no signed link in it",
          err != "" and "X-Goog-Signature" not in err, err)

    install(proxy_block)
    fp = F.FileProcessor(_Cfg())
    try:
        fp._upload_file(tmpfile(size=F.PROXY_UPLOAD_MAX_BYTES + 1, name="big.mp4")); err = ""
    except FileUploadError as e:
        err = str(e)
    check("[FAIL control] a blocked file over 25 MB says why, and sends nothing through cellcog.ai",
          "100 MB" in err and "big.mp4" in err and not any("upload-bytes" in c[1] for c in CALLS), err)

    print("— loud failure on send —")
    install(proxy_block, put_fallback=lambda *a, **k: _Resp(status=500, payload={"detail": "boom"}))
    fp = F.FileProcessor(_Cfg())
    path = tmpfile()
    try:
        fp.transform_outgoing(f"Use this <SHOW_FILE>{path}</SHOW_FILE> as reference"); err = ""
    except FileUploadError as e:
        err = str(e)
    check("[FAIL control] a file that cannot be uploaded either way stops the send, naming the file",
          "failed to upload" in err and path in err and "Nothing was sent" in err, err)

    install(proxy_block)
    fp = F.FileProcessor(_Cfg())
    out, up = fp.transform_outgoing(f"Use this <SHOW_FILE>{path}</SHOW_FILE> as reference")
    check("the same message with a working fallback sends the stored reference (PASS control)",
          "human_files/u/ref.png" in out and len(up) == 1, out)

    print("— download —")
    chat_id = "6ae7d4b4a578585316b14e62"
    ref = f"{chat_id}//home/app/img/legpress_A.png"
    dest = os.path.join(tempfile.mkdtemp(), "out", "legpress_A.png")
    install(proxy_block)
    fp = F.FileProcessor(_Cfg())
    fp._download_file(STORAGE, dest, chat_id=chat_id, ref=ref)
    fb = [c for c in CALLS if c[0] == "GET" and c[1] == f"{API}/cellcog/chat/{chat_id}/file"]
    check("a proxy-refused storage GET falls back to /cellcog/chat/{id}/file with the ref",
          open(dest, "rb").read() == b"via-cellcog" and fb and fb[0][2] == {"ref": ref}, str(CALLS))
    check("no .part file is left behind", not os.path.exists(dest + ".part"))

    install(lambda *a, **k: _Resp(), get_storage=lambda *a, **k: _Resp(status=403))
    fp = F.FileProcessor(_Cfg())
    dest3 = os.path.join(tempfile.mkdtemp(), "b.png")
    fp._download_file(STORAGE, dest3, chat_id=chat_id, ref=ref)
    check("a storage GET answered 403 falls back to /cellcog/chat/{id}/file, and is not remembered",
          open(dest3, "rb").read() == b"via-cellcog" and fp._storage_blocked is False, str(CALLS))

    install(lambda *a, **k: _Resp(), get_storage=lambda *a, **k: _Resp(status=404))
    fp = F.FileProcessor(_Cfg())
    try:
        fp._download_file(STORAGE, os.path.join(tempfile.mkdtemp(), "c.png"), chat_id=chat_id, ref=ref); err = ""
    except FileDownloadError as e:
        err = str(e)
    check("[FAIL control] a storage GET answered 404 is a real answer: no fallback",
          "HTTP 404" in err and not any(c[0] == "GET" and "cellcog.ai" in c[1] for c in CALLS), err + " " + str(CALLS))

    install(lambda *a, **k: _Resp(), get_storage=lambda *a, **k: _Resp(status=403))
    fp = F.FileProcessor(_Cfg())
    try:
        fp._download_file(STORAGE, os.path.join(tempfile.mkdtemp(), "d.png")); err = ""
    except FileDownloadError as e:
        err = str(e)
    check("[FAIL control] a 403 with no chat to fall back to stays an error", "HTTP 403" in err and "X-Goog-Signature" not in err, err)

    install(lambda *a, **k: _Resp(), get_storage=lambda *a, **k: _Resp(body=b"direct"))
    fp = F.FileProcessor(_Cfg())
    dest2 = os.path.join(tempfile.mkdtemp(), "a.png")
    fp._download_file(STORAGE, dest2, chat_id=chat_id, ref=ref)
    check("a working storage GET never touches cellcog.ai (PASS control)",
          open(dest2, "rb").read() == b"direct" and not any("/file" in c[1] for c in CALLS if c[0] == "GET" and "cellcog.ai" in c[1]))

    install(proxy_block, get_fallback=lambda *a, **k: _Resp(status=404, payload={"detail": "File not found"}))
    fp = F.FileProcessor(_Cfg())
    msgs = [{"messageFrom": "CellCog", "content": f"Here:\n<SHOW_FILE>{ref}</SHOW_FILE>", "createdAt": "x"}]
    out = fp.transform_incoming_history(msgs, {ref: {"url": STORAGE}}, chat_id)
    check("[FAIL control] a file that downloads neither way gets a visible note, not a silent missing file",
          "[cellcog: this file was not downloaded:" in out[0]["content"] and "HTTP 404" in out[0]["content"]
          and "X-Goog-Signature" not in out[0]["content"], out[0]["content"])

    print(f"\n{PASS} passed, {FAIL} failed")
    return FAIL


def test_storage_fallback():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
