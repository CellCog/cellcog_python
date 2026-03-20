"""
Example: Using wait_for_completion() for synchronous workflows.

CellCog's fire-and-forget pattern is great for conversational agents,
but sometimes you need to block until a task completes — for cron jobs,
Lobster pipelines, scripts, or any sequential workflow.

wait_for_completion() composes with create_chat() and send_message()
to enable this. The daemon still handles result delivery to your session;
wait_for_completion() simply blocks your thread until that's done.
"""

from cellcog import CellCogClient

client = CellCogClient()

# ─── Simple blocking usage ────────────────────────────────────

result = client.create_chat(
    prompt="What are the top 3 AI trends in 2026?",
    notify_session_key="agent:main:main",
    task_label="ai-trends",
)

print(f"Chat created: {result['chat_id']}")
print("Waiting for CellCog to finish...")

# Block until done (default timeout: 30 minutes)
completion = client.wait_for_completion(result["chat_id"])

if not completion["is_operating"]:
    print("✅ Done! Results delivered to your session.")
else:
    print(f"⏳ {completion['status_message']}")


# ─── Custom timeout ───────────────────────────────────────────

# For complex jobs (deep research, video production), use 60 min
result = client.create_chat(
    prompt="Create a comprehensive market analysis of the EV industry",
    notify_session_key="agent:main:main",
    task_label="ev-research",
    chat_mode="agent team",
)

completion = client.wait_for_completion(result["chat_id"], timeout=3600)

if not completion["is_operating"]:
    print("✅ Research complete!")
else:
    # Timed out — daemon will deliver results later
    print("Still working. Results will arrive at your session.")


# ─── Re-wait after timeout ────────────────────────────────────

# If the first wait times out, you can wait again
completion = client.wait_for_completion("some_chat_id", timeout=300)
if completion["is_operating"]:
    # Wait another 30 minutes
    completion = client.wait_for_completion("some_chat_id", timeout=1800)
