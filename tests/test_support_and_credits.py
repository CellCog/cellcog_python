"""Standalone tests for stop_chat, the removed create_ticket and the 402 (out of credits) text.

Mocked HTTP only (requests.request in cellcog.chat is replaced; sockets refuse to connect).

Run: python3 tests/test_support_and_credits.py
"""

import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _no_net(*a, **k):
    raise RuntimeError("test: network blocked")


socket.socket.connect = _no_net
_tmp = tempfile.mkdtemp(prefix="cellcog_test_")
os.environ["CELLCOG_STATE_DIR"] = _tmp
os.environ["CELLCOG_API_KEY"] = "sk_test_not_a_real_key"

from cellcog import CellCogClient, PaymentRequiredError
from cellcog import chat as chat_mod
from cellcog.client import STOP_TEXT

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


class FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


calls = []


def fake_http(routes):
    calls.clear()

    def request(method, url, headers=None, json=None, timeout=None, **kw):
        calls.append((method, url, json))
        for (m, suffix), resp in routes.items():
            if m == method and url.endswith(suffix):
                return resp
        raise AssertionError(f"unexpected request {method} {url}")

    chat_mod.requests.request = request


client = CellCogClient(agent_provider="script", agent_version="1", config_path=os.path.join(_tmp, "cfg.json"))

# --- create_ticket is gone (no SDK user called it; support reports are filed by CellCog's agents) ---
check("no create_ticket", hasattr(client, "create_ticket"), False)
done = client._build_completion_message(chat_id=CHAT, formatted_output="", delivered_count=0, downloaded_files=[],
                                        chat_credits=None, wallet_balance=None)
check("result formatter teaches the support report", "Ask CellCog to file a support report" in done, True)

# --- stop_chat sends the MCP / web stop line, only into a running chat ---
check("STOP_TEXT", STOP_TEXT, "Please stop operation and wait for further instructions.")
fake_http({("GET", f"/chat/{CHAT}"): FakeResp(200, {"operating": True, "name": "x"}),
           ("POST", f"/chat/{CHAT}/messages"): FakeResp(200, {})})
res = client.stop_chat(CHAT)
check("running: one POST with STOP_TEXT", [c[2] for c in calls if c[0] == "POST"], [{"message": STOP_TEXT}])
check("running: stopped", res["stopped"], True)
fake_http({("GET", f"/chat/{CHAT}"): FakeResp(200, {"operating": False, "name": "x"})})
res = client.stop_chat(CHAT)
check("idle: nothing sent", [c for c in calls if c[0] == "POST"], [])
check("idle: not stopped", res["stopped"], False)

# --- 402: the server's answer when it carries one (marked by `case`), else the fallback ---
OLD = {"message": "old sentence", "payment_options": {"billing_url": "https://cellcog.ai/profile?tab=billing",
       "top_ups": [{"amount_dollars": 10, "credits": 900, "url": "https://buy.stripe.com/test_ten"}]}}
NEW = dict(OLD, case="C2", message="Out of credits; the recommended way is below.", checkout_url="https://a.example/plan",
           options=[{"label": "Subscribe to a plan", "recommended": True, "url": "https://a.example/plan"},
                    {"label": "Top up once", "recommended": False, "url": "https://buy.stripe.com/test_ten"}])


def err_for(detail):
    fake_http({("POST", "/cellcog/chat/new"): FakeResp(402, {"detail": detail})})
    try:
        client._chat._request("POST", "/cellcog/chat/new", {})
    except PaymentRequiredError as e:
        return e


e = err_for(NEW)
check("enriched: server message + bullets", str(e).split("\n\nAccount:")[0],
      "Out of credits; the recommended way is below.\n"
      "  • Subscribe to a plan: https://a.example/plan\n"
      "  • Top up once: https://buy.stripe.com/test_ten")
check("enriched: attributes", (e.case, e.checkout_url, len(e.options), e.top_ups[0]["credits"]), ("C2", "https://a.example/plan", 2, 900))
e = err_for(OLD)
check("fallback: old text", str(e).startswith("Payment required."), True)
check("fallback: no proration claim", "prorated" in str(e) or "cr/$1" in str(e), False)
check("fallback: old message not used without case", (e.message, "old sentence" in str(e)), (None, False))

print(f"\n{'FAILED' if failed else 'ALL PASSED'} ({failed} failed)")
sys.exit(1 if failed else 0)
