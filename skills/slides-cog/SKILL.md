---
name: slides-cog
description: Presentation generation powered by CellCog. Create PPTX presentations, pitch decks, keynotes, slide designs, image slideshows, professional presentations. AI-powered presentation builder.
---

# Slides Cog - Presentations Powered by CellCog

Create professional presentations with AI - from pitch decks to keynotes to image slideshows.

---

## Prerequisites

This skill requires the CellCog mothership skill for SDK setup and API calls.

```bash
clawhub install cellcog
```

**Read the cellcog skill first** for SDK setup and the `sessions_spawn` pattern. This skill shows you what's possible.

**Quick pattern:**
```python
client.create_chat_and_stream(
    prompt="[your presentation request]",
    session_id=session_id,
    main_agent=False,
    chat_mode="agent team"  # Always for presentations
)
```

---

## What Presentations You Can Create

### Pitch Decks

Investor and stakeholder presentations:

- **Startup Pitch**: "Create a 12-slide pitch deck for a fintech startup disrupting small business lending"
- **Investor Update**: "Build a quarterly investor update presentation covering metrics, milestones, and roadmap"
- **Funding Ask**: "Create a Series A pitch deck for an AI healthcare company seeking $5M"

### Business Presentations

Corporate and professional presentations:

- **Quarterly Business Review**: "Create a QBR presentation covering sales performance, challenges, and next quarter plans"
- **Strategy Presentation**: "Build a strategic planning presentation for entering the European market"
- **Board Deck**: "Create a board meeting presentation with financials, KPIs, and key decisions needed"
- **Project Proposal**: "Build a project proposal presentation for implementing a new CRM system"

### Sales Presentations

Customer-facing decks:

- **Product Demo Deck**: "Create a product demo presentation for our project management software"
- **Capabilities Deck**: "Build a company capabilities presentation for enterprise sales"
- **Case Study Presentation**: "Create a case study presentation showing how Client X achieved 3x ROI"
- **Pricing Presentation**: "Build a pricing and packaging presentation for our three tiers"

### Educational Presentations

Teaching and training content:

- **Course Slides**: "Create lecture slides for an introduction to machine learning"
- **Training Deck**: "Build employee onboarding slides covering company culture and policies"
- **Workshop Presentation**: "Create workshop slides for a design thinking session"
- **Tutorial Slides**: "Build a step-by-step tutorial presentation for using Excel pivot tables"

### Event Presentations

Conferences and special events:

- **Keynote**: "Create a keynote presentation on the future of artificial intelligence"
- **Conference Talk**: "Build a 20-minute conference presentation on scaling engineering teams"
- **All-Hands**: "Create an all-hands meeting presentation covering company updates and wins"
- **Product Launch**: "Build a product launch presentation for unveiling our new feature"

### Image Slideshows

Visual storytelling with images:

- **Portfolio Slideshow**: "Create a photography portfolio slideshow with minimal text"
- **Travel Presentation**: "Build a vacation recap slideshow with photos and captions"
- **Event Highlights**: "Create an event highlight slideshow from conference photos"
- **Visual Story**: "Build a brand story slideshow using images and minimal text"

---

## Presentation Features

CellCog presentations can include:

| Element | Description |
|---------|-------------|
| **Title Slides** | Bold, impactful opening slides |
| **Content Slides** | Text, bullets, and layouts |
| **Charts & Graphs** | Bar, line, pie, and more |
| **Images** | AI-generated or placeholder for your images |
| **Data Tables** | Clean, formatted tables |
| **Timelines** | Visual timelines and roadmaps |
| **Comparison Slides** | Side-by-side comparisons |
| **Quote Slides** | Testimonials and callouts |

---

## Output Formats

| Format | Best For |
|--------|----------|
| **PPTX** | Editable in PowerPoint, Google Slides, Keynote |
| **PDF** | Sharing, printing, unchangeable |
| **Interactive HTML** | Web-based presentations |

---

## When to Use Agent Team Mode

For presentations, **always use `chat_mode="agent team"`** (the default).

Creating presentations involves:
- Content structuring
- Narrative flow
- Visual design
- Image generation (if needed)
- Layout optimization

This multi-step process benefits from the full agent team.

---

## Example Presentation Prompts

**Startup pitch deck:**
> "Create a 12-slide Series A pitch deck for 'DataSync' - a B2B SaaS company that helps enterprises sync data across cloud applications.
> 
> Include slides for: Problem, Solution, Product Demo, Market Size, Business Model, Traction, Team, Competition, Go-to-Market, Financials, Ask, Contact.
> 
> Key metrics: $50K MRR, 30 customers, 15% MoM growth, seeking $5M for expansion.
> 
> Modern, professional design. Blue and white color scheme."

**Quarterly business review:**
> "Create a QBR presentation for Q4 2025:
> 
> 1. Executive Summary
> 2. Revenue Performance (hit 95% of target)
> 3. Customer Metrics (NPS improved to 72)
> 4. Key Wins (3 enterprise deals closed)
> 5. Challenges (churn increased in SMB segment)
> 6. Q1 2026 Priorities
> 7. Resource Asks
> 
> Include relevant charts. Corporate professional style."

**Educational slides:**
> "Create a 15-slide presentation for teaching 'Introduction to Python Programming':
> 
> 1. What is Python?
> 2. Why Learn Python?
> 3. Setting Up Your Environment
> 4. Variables and Data Types
> 5. Basic Operations
> 6. Strings
> 7. Lists
> 8. Conditionals (if/else)
> 9. Loops
> 10. Functions
> 11. Simple Project: Calculator
> 12. Resources for Learning More
> 
> Beginner-friendly, include code examples, clean modern design."

**Image slideshow:**
> "Create a visual slideshow presentation showcasing 10 images of modern architecture around the world. Each slide should have: one stunning building image, the building name, location, and architect. Minimal text, maximum visual impact. Generate the images."

---

## Tips for Better Presentations

1. **Specify slide count**: "10-12 slides" helps scope appropriately. Pitch decks are typically 10-15 slides. Training can be 20-30.

2. **List the slides you want**: Even a rough outline helps. "Include: Problem, Solution, Market, Team, Ask."

3. **Provide key content**: Actual metrics, quotes, and facts make better slides than placeholders.

4. **Design direction**: "Minimal and modern", "Corporate professional", "Bold and colorful", specific colors.

5. **Mention the audience**: "For investors", "For technical team", "For executives" changes tone and detail level.

6. **Specify format**: "PPTX for editing" or "PDF for sharing."
