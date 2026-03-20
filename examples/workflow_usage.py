"""
Example: Sequential multi-step workflow using wait_for_completion().

This shows how to chain CellCog tasks into a pipeline where each step
depends on the previous one. The daemon delivers results to your session
at each step; wait_for_completion() blocks until each step is done.

Timeout guidance:
  - Simple jobs (images, quick text):  1800s (30 min)
  - Complex jobs (deep research, video): 3600s (60 min)
"""

from cellcog import CellCogClient

client = CellCogClient()

# ─── Multi-step research → report workflow ────────────────────

# Step 1: Research
print("Step 1: Starting research...")
r1 = client.create_chat(
    prompt="Research the latest advances in quantum computing in 2026",
    notify_session_key="agent:main:main",
    task_label="quantum-research",
    chat_mode="agent team",
)

step1 = client.wait_for_completion(r1["chat_id"], timeout=1800)
if step1["is_operating"]:
    print("Research taking longer than expected.")
    print(step1["status_message"])
    exit(1)

print("Step 1 complete!")

# Step 2: Generate PDF from the research (same chat — CellCog remembers)
print("Step 2: Creating PDF report...")
r2 = client.send_message(
    chat_id=r1["chat_id"],
    message="Create a PDF executive summary of your research findings",
    notify_session_key="agent:main:main",
    task_label="create-pdf",
)

step2 = client.wait_for_completion(r1["chat_id"], timeout=1800)
if not step2["is_operating"]:
    print("Step 2 complete! PDF delivered to your session.")

# Step 3: Create a presentation from the same research
print("Step 3: Creating slide deck...")
r3 = client.send_message(
    chat_id=r1["chat_id"],
    message="Now create a presentation slide deck from the research",
    notify_session_key="agent:main:main",
    task_label="create-slides",
)

step3 = client.wait_for_completion(r1["chat_id"], timeout=1800)
if not step3["is_operating"]:
    print("Step 3 complete! All deliverables ready.")

print("Workflow finished!")
