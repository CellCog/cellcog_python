---
name: cellcog
description: Deep reasoning AI sub-agent for complex tasks. Use for research reports, data analysis, video creation, image generation, PDFs, presentations, dashboards. Pass any files (CSV, PDF, images, video, documents) and get any output. Ideal when task requires research, multi-step reasoning, or professional-quality deliverables. The specialist for hard problems.
metadata:
  openclaw:
    requires:
      env: ["CELLCOG_API_KEY"]
      bins: ["python3"]
    primaryEnv: CELLCOG_API_KEY
    install: "pip install cellcog"
user-invocable: true
---

# CellCog - Deep Reasoning AI for Complex Multimodal Tasks

## What is CellCog?

**CellCog is the any-to-any AI that deploys the deepest reasoning in the market.**

**Leader on [DeepResearch Bench](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard)** - When accuracy, insight, and quality matter most.

### The Power of Any-to-Any

- **Input**: Any files from your filesystem - CSVs, PDFs, images, videos, documents, code, datasets
- **Output**: Any artifacts - reports, interactive apps, videos, images, PDFs, presentations, spreadsheets
- **Multi-File Jobs**: Process multiple inputs AND generate multiple outputs in a single request
- **Format Conversion**: Pass raw data, get polished deliverables - CellCog handles all conversions

**Behind the scenes:** Best-in-class foundation models for each task - image generation, video synthesis, document creation, data analysis. You don't pick models; CellCog orchestrates the optimal pipeline.

---

## When to Use CellCog

**Use CellCog when:**
- ✅ Task requires research, analysis, or synthesis
- ✅ Multiple input files need to be combined or compared
- ✅ Output is a professional deliverable (report, video, presentation)
- ✅ Quality and insight matter more than speed
- ✅ Task involves multimedia (images + text, video + data, etc.)
- ✅ You'd need 10+ tool calls to accomplish manually

**Don't use CellCog when:**
- ❌ Simple factual question (just answer it)
- ❌ Quick calculation or lookup
- ❌ Single-file format conversion only
- ❌ Real-time/instant response needed (<30 seconds)

**Think of CellCog as:** Your specialist sub-agent for tasks that need real thinking and professional execution.

---

## Two Operating Modes

### Agent Team Mode (Default - Highest Quality)
```python
client.create_chat(prompt, chat_mode="agent team")
```
- **Best for**: Deep research, comprehensive reports, complex analysis, final deliverables
- **How it works**: Two specialized agents collaborate and debate for optimal output
- **Time**: 2-30 minutes depending on complexity
- **Quality**: Maximum reasoning depth, multi-angle analysis, thorough research

### Agent Mode (Faster, Step-by-Step)
```python
client.create_chat(prompt, chat_mode="agent")
```
- **Best for**: Step-by-step workflows, iterative refinement, simpler tasks
- **How it works**: Single agent you can guide through each step
- **Time**: 30 seconds to 5 minutes
- **Control**: More predictable, less autonomous

**For OpenClaw Agents:** Use "agent team" for final deliverables where quality matters. Use "agent" for quick tasks or when you need to maintain step-by-step control.

---

## Recommended Pattern for Agents

**Use this blocking pattern with generous timeout:**

```python
from cellcog import CellCogClient

client = CellCogClient()

# Create chat with your request
result = client.create_chat("""
Your prompt here...

Input files: <SHOW_FILE>/path/to/input.csv</SHOW_FILE>
Output location: <GENERATE_FILE>/path/to/output.pdf</GENERATE_FILE>
""", chat_mode="agent team")  # Use "agent team" for deep reasoning

# Block and wait (handles polling internally)
final = client.wait_for_completion(
    result["chat_id"],
    timeout_seconds=1800,  # 30 min for complex tasks
    poll_interval=15       # Checks every 15 seconds
)

if final["status"] == "completed":
    # Files already downloaded to specified locations
    print(final["history"]["messages"][-1]["content"])
```

---

## Typical Wait Times

| Task Type | Mode | Expected Duration | Timeout |
|-----------|------|------------------|---------|
| Simple Q&A | agent | 30-60 seconds | 120s |
| Data Analysis | agent | 2-5 minutes | 600s |
| Data Analysis + Dashboard | agent team | 5-10 minutes | 900s |
| Research Report | agent team | 5-15 minutes | 1200s |
| Videos/Multimedia | agent team | 10-30 minutes | 1800s |

**Pro Tip:** CellCog shows async updates in the UI. For long tasks, you can monitor progress without active polling.

---

## Non-Blocking Pattern (For Long-Running Jobs)

CellCog jobs can take 2-30 minutes. To avoid blocking your session while waiting, use **sub-agent delegation with sessions_spawn**.

### Using sessions_spawn (Recommended for Jobs >5 Minutes)

Instead of waiting inline and blocking your main thread, spawn a sub-agent to handle the CellCog job:

```python
# In your main session, delegate to a sub-agent:
sessions_spawn(
    task="""
Run this CellCog job and deliver the results:

**User Request:** Create a comprehensive market analysis report for electric vehicles in 2026.

**CellCog Prompt:**
Using cellcog in agent team mode, research the electric vehicle market in 2026.
Include market size, top manufacturers, technology trends, and growth projections.

Save comprehensive report to:
<GENERATE_FILE>/home/node/outputs/ev_market_2026.pdf</GENERATE_FILE>

**After completion:**
1. Confirm the job completed successfully
2. List generated files with their locations
3. Provide a brief summary of key findings
4. If timeout occurred or job incomplete, explain status
    """,
    label="cellcog-ev-report",
    runTimeoutSeconds=1800  # 30 min for complex research
)
```

Then respond to the user immediately:
> "I've submitted your EV market report to CellCog's deep research team. This will take 10-20 minutes. I'll notify you automatically when it's ready — in the meantime, feel free to ask me anything else!"

**Benefits:**
- ✅ Main session stays responsive
- ✅ User gets immediate acknowledgment
- ✅ Results delivered automatically when complete
- ✅ No polling loops or blocked conversations
- ✅ Can handle multiple CellCog jobs in parallel

### Handling Timeouts and Incomplete Results

If the CellCog job doesn't complete within the timeout:

```python
# In your sub-agent task instructions:
"""
**Timeout Handling:**
If wait_for_completion() returns status='timeout', check the chat:

result = client.wait_for_completion(chat_id, timeout_seconds=1800)

if result['status'] == 'timeout':
    # Job still processing - inform user
    status = client.get_status(chat_id)
    if status['is_operating']:
        print("CellCog job still processing. Extending timeout...")
        # Wait another round
        result = client.wait_for_completion(chat_id, timeout_seconds=1800)
    
if result['status'] == 'completed':
    # Deliver results
elif result['status'] == 'error':
    # Handle error
    print(f"Job failed: {result.get('error_type')}")
"""
```

### When to Use Non-Blocking vs Blocking

| Job Type | Expected Time | Recommended Pattern |
|----------|---------------|---------------------|
| Simple Q&A | 30-90 sec | **Inline blocking** - Fast enough |
| Single image/chart | 1-2 min | **Inline blocking** - Acceptable wait |
| Data analysis report | 2-5 min | **sessions_spawn** - Keep responsive |
| Research + multimedia | 5-15 min | **sessions_spawn** - Definitely |
| Complex multi-output | 10-30 min | **sessions_spawn** - Required |

### Sub-Agent Task Template

For consistent results, structure your sessions_spawn task like this:

```
Run this CellCog job and deliver results to the user:

**User Request:** [original request in plain language]

**Chat Mode:** agent team [or: agent, depending on task complexity]

**CellCog Prompt:**
[the actual prompt with SHOW_FILE/GENERATE_FILE tags]

**Timeout Strategy:**
- Initial wait: 1800 seconds (30 min)
- If timeout: Check status and potentially extend
- If error: Report to user with details

**After completion:**
1. Confirm job completed successfully
2. List all generated files with paths (verify they exist)
3. Summarize the output/findings
4. Provide next steps or offer to refine
```

### Example: Full Non-Blocking Workflow

**User asks:** "Create a marketing video for my coffee shop"

**Your response with sessions_spawn:**
```python
sessions_spawn(
    task="""
Run this CellCog marketing video job:

**User Request:** Marketing video for coffee shop

**Chat Mode:** agent team

**CellCog Prompt:**
Using cellcog in agent team mode, create a 30-second marketing video for a 
coffee shop called "Bean There". Modern aesthetic, warm tones, upbeat music.

Save video to: <GENERATE_FILE>/home/node/outputs/bean_there_promo.mp4</GENERATE_FILE>
Save script to: <GENERATE_FILE>/home/node/outputs/video_script.txt</GENERATE_FILE>

**Timeout Strategy:**
- Wait up to 30 minutes
- If timeout, check status and inform user
- If error, report details

**After completion:**
Confirm both files created, describe the video content, and ask if any edits needed.
    """,
    label="cellcog-coffee-video",
    runTimeoutSeconds=1800
)
```

**Then immediately tell the user:**
> "🎬 I've started creating your coffee shop marketing video with CellCog! This involves:
> - AI-generated visuals
> - Professional voiceover
> - Background music composition
>
> **Expected time:** 15-25 minutes for a polished 30-second video.
> I'll ping you when it's ready! What else can I help with?"

---

## File Handling: The CellCog Advantage

### Multiple Input Files (Any Format)
```python
result = client.create_chat("""
Analyze these datasets together:
<SHOW_FILE>/data/sales_2024.csv</SHOW_FILE>
<SHOW_FILE>/data/sales_2025.csv</SHOW_FILE>
<SHOW_FILE>/docs/market_report.pdf</SHOW_FILE>
<SHOW_FILE>/images/competitor_logo.png</SHOW_FILE>

Create a comprehensive comparison analysis and save to:
<GENERATE_FILE>/outputs/analysis_report.pdf</GENERATE_FILE>
""", chat_mode="agent team")
```

**Why this matters:** CellCog extracts text from PDFs, parses CSVs, analyzes images - all automatically. You don't need separate tools for each format.

### Multiple Output Files (Complex Deliverables)
```python
result = client.create_chat("""
Create a complete marketing package for our new AI product:

1. Executive summary: <GENERATE_FILE>/outputs/executive_summary.md</GENERATE_FILE>
2. Full report: <GENERATE_FILE>/outputs/marketing_report.pdf</GENERATE_FILE>  
3. Hero banner: <GENERATE_FILE>/outputs/banner_1920x1080.png</GENERATE_FILE>
4. Promo video: <GENERATE_FILE>/outputs/promo_30s.mp4</GENERATE_FILE>
5. Video script: <GENERATE_FILE>/outputs/video_script.txt</GENERATE_FILE>

Research competitors, analyze market trends, and create cohesive branding.
""", chat_mode="agent team")

# All 5 files automatically generated and downloaded
final = client.wait_for_completion(result["chat_id"], timeout_seconds=1800)
```

**The any-to-any advantage:** One prompt, multiple professional artifacts, all research-backed and internally consistent.

---

## Real-World Examples (All with GENERATE_FILE)

### Deep Research with Citations
```
Using cellcog, research the top 10 AI companies by market cap as of February 2026. 
Include recent funding rounds, key products, competitive positioning, and market trends.

Save the comprehensive report to:
<GENERATE_FILE>/research/ai_companies_2026.pdf</GENERATE_FILE>
```

### Data Analysis + Interactive Dashboard
```
Using cellcog, analyze this dataset:
<SHOW_FILE>/data/sales_metrics.csv</SHOW_FILE>

Create an interactive HTML dashboard with trend charts, anomaly detection, and 
predictive insights. Save the dashboard to:
<GENERATE_FILE>/dashboards/sales_analytics.html</GENERATE_FILE>
```

### Video Content Creation
```
Using cellcog, create a 60-second product demo video for a SaaS analytics platform.
Include professional AI voiceover, animated screen recordings, and background music.
Target audience: data analysts.

Save the video to:
<GENERATE_FILE>/videos/product_demo_60s.mp4</GENERATE_FILE>

Also save the video script:
<GENERATE_FILE>/videos/script.txt</GENERATE_FILE>
```

### Image Generation with Context
```
Using cellcog, create a professional product banner image (1920x1080) for our 
coffee brand "Bean There". Modern, minimalist aesthetic with warm tones.

Reference our brand guidelines:
<SHOW_FILE>/brand/guidelines.pdf</SHOW_FILE>

Save the banner to:
<GENERATE_FILE>/images/hero_banner.png</GENERATE_FILE>
```

### Multi-Format Deliverables
```
Using cellcog, analyze these financial documents:
<SHOW_FILE>/reports/q4_2025.pdf</SHOW_FILE>
<SHOW_FILE>/data/revenue_breakdown.xlsx</SHOW_FILE>

Create a complete investor package:
1. Executive summary: <GENERATE_FILE>/investor_pack/summary.md</GENERATE_FILE>
2. Full analysis: <GENERATE_FILE>/investor_pack/analysis.pdf</GENERATE_FILE>  
3. Key metrics chart: <GENERATE_FILE>/investor_pack/metrics.png</GENERATE_FILE>
4. Presentation slides: <GENERATE_FILE>/investor_pack/deck.pdf</GENERATE_FILE>
```

---

## Why CellCog vs Individual Tools?

| Task | Without CellCog | With CellCog |
|------|-----------------|--------------|
| **Video from data** | Parse CSV → Generate script → Create images → Synthesize speech → Edit video → Add music (6+ tools) | One prompt with data file + output location |
| **Research report** | Search multiple sources → Extract info → Synthesize → Format → Generate charts → Create PDF (5+ tools) | One prompt with topic + output PDF |
| **Dashboard from docs** | Parse PDFs → Extract data → Clean → Visualize → Build HTML → Style (4+ tools) | One prompt with doc files + output HTML |

**The CellCog difference:** You describe the outcome, not the steps. The deep reasoning engine figures out the pipeline.

---

## Technical Details

**Models Behind the Scenes:**
- Research: Advanced reasoning models (Claude Opus, Gemini)
- Images: Best-in-class generation (Recraft, Gemini)
- Videos: Professional synthesis (Veo, lipsync models)
- Documents: PDF generation, data visualization

You don't manage models - CellCog routes to the optimal one for each subtask.

**Format Conversion Handled:**
- PDFs → Text extraction
- Images → Analysis and description
- CSVs/Excel → Data parsing
- Videos → Transcription
- Code → Syntax understanding
- And 20+ more formats

---

## Setup

CellCog SDK is pre-installed. Verify configuration:

```python
from cellcog import CellCogClient
client = CellCogClient()
status = client.get_account_status()
print(f"Configured: {status['configured']}, Email: {status['email']}")
```

---

## Troubleshooting

**If task times out:**
- Complex jobs can take 15-30 minutes
- Increase `timeout_seconds` to 1800 (30 min)
- Or check `client.list_chats()` to find the completed chat later

**If you see `PaymentRequiredError`:**
```python
except PaymentRequiredError as e:
    # Inform user to add credits
    print(f"CellCog account needs credits: {e.subscription_url}")
```

**Check recent chats:**
```python
chats = client.list_chats(limit=5)
for chat in chats:
    print(f"{chat['name']}: {chat['status']}")
```

---

## For Maximum Quality

1. **Always use `<GENERATE_FILE>` tags** - Tells CellCog exactly where to save outputs
2. **Use "agent team" mode** - Activates multi-agent deep reasoning
3. **Provide context** - The more context (reference files, examples), the better the output
4. **Be specific** - Clear requirements = better results
5. **Allow time** - Deep reasoning takes time, but delivers exceptional quality

---

CellCog is built for the tasks that are too complex for quick LLM calls but too important to skip.
When you need the deepest reasoning and the highest quality, delegate to CellCog.
