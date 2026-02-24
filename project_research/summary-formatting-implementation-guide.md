# Summary Formatting Implementation Guide

**Purpose:** Actionable specification for an LLM implementer to update the summary generation prompts and frontend rendering for both (A) real-time rolling summaries and (B) after-call summaries.

**Compiled:** February 20, 2026

---

## Current State of the Codebase

### Backend: `backend/app/services/summary_generator.py`

**System prompt (line ~217):**
```
You are an AI assistant for customer service agents. Create concise, scannable summaries using bullet points. Be brief and action-oriented.
```

**First summary user prompt (line ~235):**
```
TRANSCRIPT:\n{transcript_text}\n\n
Summarize with 3-4 concise bullet points:\n
• Customer need/issue\n
• Agent response\n
• Current status\n\n
Be brief and scannable.
```

**Rolling update user prompt (line ~224):**
```
PREVIOUS:\n{previous_summary.summary_text}\n\n
NEW TRANSCRIPT:\n{transcript_text}\n\n
Update the summary with bullet points:\n
• What's NEW or CHANGED\n
• Key customer needs/issues\n
• Agent actions taken\n
• Next steps or outcomes\n\n
Keep it under 4-5 bullets. Be concise and action-focused.
```

**Config:** 30-second interval, gpt-3.5-turbo, temperature 0.3, max_tokens 500, token-by-token streaming.

### Frontend: `frontend/src/components/SummaryViewer.tsx`

- Renders `currentSummaryText` as a single `pre-wrap` div (line ~185)
- No section parsing, no per-section DOM elements
- Typewriter cursor animation during streaming
- Full text replacement every update cycle

### Frontend: `frontend/src/components/ACWPanel.tsx`

- Summary tab shows AI summary as a single read-only text block (line ~255)
- No structured sections, no markdown rendering
- Placeholder CRM fields not yet populated by AI

---

## PART A: Real-Time Rolling Summaries (Every ~30 Seconds)

### The Core Problem

Agents are **actively multitasking** (listening, responding, navigating systems) while the summary updates. Every update that forces re-reading is a cognitive interruption. The summary must be **peripherally scannable** — glanceable in 2-3 seconds without losing conversational flow.

The current prompt produces unstructured bullet lists that rewrite entirely each cycle, forcing the agent to re-parse the whole summary to find what changed.

### Research-Backed Formatting Principles

#### 1. Fixed Section Headers Reduce Visual Search Time

Agents develop spatial memory for where information lives. If section headers stay in fixed positions, agents can jump directly to the section they need without scanning.

**Source:** NNGroup research on scannable content ("How Users Read on the Web", Jakob Nielsen, 1997; revalidated 2020) — structured headings improved task completion by 47% vs. unstructured content.
**URL:** https://www.nngroup.com/articles/how-users-read-on-the-web/

**Source:** Google CCAI Agent Assist surfaces "Intent" as a persistent top-level badge that does not move. Genesys Agent Copilot shows "Reason contacted" as a fixed first field.
**URL:** https://help.genesys.cloud/articles/about-genesys-agent-copilot/

#### 2. Bullet Points Beat Prose by 124%

Scannable content with bullet points improved usability by 124% compared to paragraph-style prose in web readability studies. For a multitasking agent, short bullets (under 80 characters) with a strong leading label are essential.

**Source:** NNGroup, "How Users Read on the Web" (1997, revalidated 2020)
**URL:** https://www.nngroup.com/articles/how-users-read-on-the-web/

#### 3. Limit to 5-7 Visible Items (Miller's Law)

Working memory capacity for a secondary task (reading a sidebar while conversing) is severely constrained. The summary panel should never show more than 5-7 total bullet items across all sections.

**Source:** Miller's Law (1956), applied via Sweller's Cognitive Load Theory to interface design.
**URL:** https://www.nngroup.com/articles/short-term-memory-and-web-usability/

#### 4. Additive Updates, Not Full Rewrites

Agents build a mental model of the summary's content and position. Full-text replacement every 30 seconds breaks that model. New content should **append** (especially in the Actions section); existing content should only change when facts genuinely change.

**Source:** arXiv:2510.06677, "Incremental Summarization for Customer Support" (Oct 2025) — agents rated incremental note-taking systems highest when temporal sequence was preserved rather than restructured into a narrative.
**URL:** https://arxiv.org/abs/2510.06677

**Source:** ASAPP contact center case study — agents want "what happened in order" during the call.
**URL:** https://www.asapp.com/blog/a-contact-center-case-study-about-call-summarization-strategies

#### 5. Telegraphic Style, No Filler

Each bullet should read like a log entry or sticky note. No articles ("a", "the"), no filler ("the customer mentioned that"), no hedging ("it appears that").

**Source:** Observe.AI production deployments — agents scan for specific data points (numbers, names, codes) more than narrative text. Label-value formatting reduces eye movement to locate a specific fact.
**URL:** https://www.observe.ai/blog/summarization-ai

#### 6. Quiet Updates vs. Attention Updates

Most 30-second updates should be "quiet" — content changes but nothing demands attention. Only flag an "attention update" when customer intent changes or a critical new entity appears.

**Source:** Cresta Agent Assist uses a two-tier notification model: routine updates happen silently, while coaching moments get a brief highlight. Prevents alert fatigue.

### Recommended Section Structure for Rolling Summary

The following 4-section format is derived from how Google CCAI Agent Assist, Genesys Agent Copilot, Amazon Connect Contact Lens, Cresta, and Observe.AI structure their real-time panels:

```
**CUSTOMER INTENT:** <single line — what the customer wants RIGHT NOW>

**KEY DETAILS:**
• <label>: <value>
• <label>: <value>
• <label>: <value>

**ACTIONS TAKEN:**
• <completed action>
• <completed action>
• <current action — in progress>

**OPEN ITEMS:**
• <unresolved issue>
```

#### Section Rules

| Section | Max Items | Update Behavior | Notes |
|---------|-----------|-----------------|-------|
| CUSTOMER INTENT | 1 line | Replace only when intent genuinely changes | This is the anchor — agents glance here when they lose track |
| KEY DETAILS | 2-4 bullets | Add new entities, update changed values | Label-value pairs, not prose. Orders, SKUs, dates, amounts |
| ACTIONS TAKEN | 3-5 bullets | Append only, never remove or reorder | Chronological. Most recent at bottom. Trim oldest if >5 |
| OPEN ITEMS | 0-2 bullets | Add/remove as items resolve | Ephemeral — disappears when resolved |

### Proposed Updated Prompts

#### System Prompt (replace existing)

```
You are a real-time note-taker for a customer service agent during a live conversation. Your output appears in a small sidebar panel that the agent glances at while multitasking.

RULES:
- Use the EXACT section headers shown below, in this order
- Telegraphic style: no articles (a, the), no filler words, no hedging
- Each bullet under 80 characters
- KEY DETAILS as label: value pairs
- ACTIONS TAKEN in chronological order, append new actions, preserve previous ones
- OPEN ITEMS only for genuinely unresolved issues; omit section if none
- Total output: 5-7 bullets maximum across all sections
```

#### First Summary User Prompt (replace existing)

```
TRANSCRIPT:
{transcript_text}

Generate a scannable summary using this exact format:

**CUSTOMER INTENT:** <one line — what the customer needs>

**KEY DETAILS:**
• <label>: <value>

**ACTIONS TAKEN:**
• <action>

**OPEN ITEMS:**
• <unresolved item> (omit section if none)
```

#### Rolling Update User Prompt (replace existing)

```
PREVIOUS SUMMARY:
{previous_summary}

NEW TRANSCRIPT SINCE LAST UPDATE:
{transcript_text}

Update the summary. RULES:
- Keep the same 4-section format
- CUSTOMER INTENT: only change if intent genuinely shifted
- KEY DETAILS: add new entities, update changed values, keep unchanged ones
- ACTIONS TAKEN: APPEND new actions to the bottom, do NOT remove or reorder previous actions. If over 5, keep only the 3 most recent plus the first one.
- OPEN ITEMS: add new unresolved items, remove items that are now resolved. Omit section if none.

Output the full updated summary:
```

### Frontend Rendering Recommendations

1. **Parse sections by header** — Split LLM output on `**CUSTOMER INTENT:**`, `**KEY DETAILS:**`, etc. and render each as a separate DOM element with a fixed-position header.

2. **Diff-aware rendering** — Compare previous section content to new section content. New bullets fade in (CSS `opacity 0→1` over 1.5s). Changed values get a subtle 3-second background highlight. Removed bullets fade out.

3. **Keep headers static** — Even if a section is empty, keep the header visible (or collapse it with zero height but retain position). Headers never move or reflow.

4. **Truncate ACTIONS TAKEN on overflow** — If >5 actions, show a collapsed "N earlier actions" link above the visible 3-4 most recent.

---

## PART B: After-Call Summaries (Post-Conversation Wrap-Up)

### The Core Difference from Rolling Summaries

After-call summaries serve a **different cognitive context**: the agent is no longer multitasking. They are focused on wrap-up work — reviewing, editing, dispositioning, and saving to CRM. The summary can be longer, more comprehensive, and structured for a focused reading task rather than peripheral scanning.

### Industry-Standard 6-Section Format

Every major contact center platform (Genesys, Five9, Talkdesk, Amazon Connect, Salesforce Einstein) has converged on a remarkably consistent structure:

#### Section 1: Headline (1 line)
- One-sentence summary of the entire interaction
- Maps to CRM "Case Subject" field
- Example: `Customer requested return and replacement for damaged safety gloves (Order #771903)`

**Source:** Genesys calls this "Summary" — first field in Agent Copilot output. Salesforce Einstein auto-fills the "Summary" field on the Voice Call record. Five9 generates a "Summary" headline.
**URL:** https://help.genesys.cloud/articles/work-with-genesys-agent-copilot/

#### Section 2: Contact Reason (1-3 bullets)
- Why the customer contacted
- Distinguish stated reason from underlying issue if different

**Source:** Genesys uses "Reason Contacted" field. Amazon Connect Contact Lens uses "Contact reason" category, auto-detected. Google CCAI uses "Issue" section.
**URL:** https://help.genesys.cloud/articles/about-genesys-agent-copilot/

#### Section 3: Key Details (structured key-value)
- All specific data points extracted from the conversation
- Format as label-value pairs, never embedded in prose
- Orders, SKUs, dates, dollar amounts, account references

**Source:** Observe.AI found agents spend 40% of ACW time re-listening to recordings to find specific data points when summaries embed them in paragraph text.
**URL:** https://www.observe.ai/blog/summarization-ai

#### Section 4: Actions Taken (checklist)
- Everything the agent did, in chronological order
- Checkmark indicators to show completion

**Source:** Genesys Agent Copilot generates actions with checkmarks. Talkdesk shows "Agent Next Steps". Five9 includes actions in the AI Summary output.
**URL:** https://help.genesys.cloud/articles/work-with-genesys-agent-copilot/

#### Section 5: Resolution (1-2 lines)
- How the interaction concluded
- Include status: Resolved / Escalated / Follow-Up Required / Unresolved

**Source:** Genesys uses a "Resolution" field. Salesforce Einstein auto-fills "Resolution" on Voice Call record. Amazon Connect Contact Lens uses resolution category.
**URL:** https://help.genesys.cloud/articles/work-with-advanced-custom-summaries/

#### Section 6: Follow-Up Items (0-3 bullets, optional)
- Actions that need to happen AFTER the call
- Include assignee and due date if determinable

**Source:** Talkdesk shows "Next Steps" with assignee fields. Genesys includes follow-up actions in the wrap-up workflow.
**URL:** https://support.talkdesk.com/hc/en-us/articles/16761287647259-Copilot-Automatic-Summarization-Agent-Next-Steps-and-Disposition

#### Supplementary: Sentiment Arc
- Customer emotional trajectory: e.g., `Frustrated → Neutral → Satisfied`
- Used by Genesys, Observe.AI, and Amazon Connect Contact Lens

**Source:** Genesys Agent Copilot deep dive blog
**URL:** https://www.genesys.com/blog/post/genesys-cloud-agent-copilot-deep-dive

### Formatting Best Practices for After-Call Summaries

| Practice | Detail | Source |
|----------|--------|--------|
| Consistent section names | Same headers across all calls — agents build muscle memory | Genesys custom summary docs |
| Pre-filled, editable | AI writes first draft; agent reviews and edits | Genesys blog: "agents review, edit, and save" |
| Length: 150-300 words | <100 words misses detail; >300 words agents stop reading | Five9 research |
| Headline: <100 chars | For CRM subject line auto-fill | Salesforce Einstein pattern |
| Bullets: <80 chars each | Scannable and fits CRM field widths | NNGroup scannable content |
| Third person, past tense | Factual tone; no hedging | Genesys custom summary config |
| Specific quantities | "3 items" not "several items"; include all reference numbers | Observe.AI production pattern |

**Sources:**
- https://help.genesys.cloud/articles/work-with-advanced-custom-summaries/
- https://www.genesys.com/blog/post/genesys-cloud-agent-copilot-deep-dive
- https://www.five9.com/blog/agentassistsummaries

### Proposed After-Call Summary Prompt

**Note:** This is a separate LLM call that may not yet be built. It should be triggered when the call ends (or when the agent enters ACW phase), using the **full transcript** rather than the rolling summary approach.

#### System Prompt

```
You are an AI summarizer for a contact center. Generate a structured after-call summary from the full conversation transcript. The summary will be displayed to the agent for review and saved to the CRM.

RULES:
- Use the EXACT section headers below, in this order
- Third person, past tense, factual tone
- No hedging (avoid "it seems", "appeared to")
- Include specific quantities, dates, and reference numbers — never generalize
- Headline under 100 characters
- Total summary: 150-300 words
- Each bullet under 80 characters
```

#### User Prompt

```
FULL TRANSCRIPT:
{full_transcript}

Generate the after-call summary using this exact format:

**HEADLINE:** <one-sentence summary, under 100 characters>

**CONTACT REASON:**
• <stated reason>
• <underlying issue, if different from stated reason>

**KEY DETAILS:**
• <label>: <value>
• <label>: <value>
• <label>: <value>

**ACTIONS TAKEN:**
• ✓ <completed action>
• ✓ <completed action>

**RESOLUTION:** <Resolved | Escalated | Follow-Up Required | Unresolved>
<1-2 sentence description of outcome>

**FOLLOW-UP ITEMS:** (omit if none)
• <action> — <assignee> — <date if known>

**SENTIMENT:** <start emotion> → <end emotion>
```

### Frontend Rendering Recommendations for ACW Panel

1. **Parse sections by header** — Same approach as rolling summaries, but with the 6-section after-call format.

2. **Make each section editable** — Agent can click into any section to edit the AI draft. Genesys pattern: "agents review, edit, and save."

3. **Map sections to CRM fields** — HEADLINE → Salesforce Case Subject, CONTACT REASON → Case Description, RESOLUTION → Case Status/Resolution field, etc.

4. **Show sentiment as a visual indicator** — Small gradient bar or emoji pair (e.g., 😤 → 😊) rather than just text. Genesys and Observe.AI both use visual sentiment arcs.

5. **Pre-populate disposition codes** — Use the CONTACT REASON and RESOLUTION sections to suggest 1-3 wrap-up codes with confidence scores.

---

## PART C: Architecture Notes

### Two Separate LLM Calls

The rolling summary and after-call summary should be **separate LLM calls** with different prompts, different triggers, and different output formats:

| Aspect | Rolling Summary | After-Call Summary |
|--------|----------------|-------------------|
| Trigger | Every 30 seconds during live call | Once, when call ends / agent enters ACW |
| Input | Previous summary + new transcript chunk | Full transcript |
| Output length | 5-7 bullets, ~50-100 words | 6 sections, 150-300 words |
| Cognitive context | Agent multitasking, peripheral scanning | Agent focused on wrap-up |
| Update behavior | Additive diff, minimal rewrite | Single comprehensive generation |
| Token budget | 500 max tokens | 800-1000 max tokens |
| Model | gpt-3.5-turbo (speed priority) | gpt-4o or equivalent (quality priority) |

### Parsing Strategy

Both prompts use `**SECTION_HEADER:**` formatting. A shared frontend utility can parse this:

```
1. Split output on lines matching /^\*\*[A-Z ]+:\*\*/
2. Extract header name and content for each section
3. Render each section as a separate component with a fixed-position header
4. For rolling summaries: diff against previous parsed sections
5. For after-call summaries: render as editable fields
```

---

## Reference Index

| # | Source | URL | Relevant To |
|---|--------|-----|-------------|
| 1 | NNGroup — How Users Read on the Web | https://www.nngroup.com/articles/how-users-read-on-the-web/ | Bullet points, scannability, 124% improvement |
| 2 | NNGroup — Short-Term Memory and Usability | https://www.nngroup.com/articles/short-term-memory-and-web-usability/ | Miller's Law, 5-7 item limit |
| 3 | Genesys — About Agent Copilot | https://help.genesys.cloud/articles/about-genesys-agent-copilot/ | Section structure, intent/reason fields |
| 4 | Genesys — Work with Agent Copilot | https://help.genesys.cloud/articles/work-with-genesys-agent-copilot/ | Transfer summaries, review-edit-save pattern |
| 5 | Genesys — Custom Summaries | https://help.genesys.cloud/articles/work-with-advanced-custom-summaries/ | Issue-Actions-Resolution structure, configurable format |
| 6 | Genesys — Agent Copilot Deep Dive Blog | https://www.genesys.com/blog/post/genesys-cloud-agent-copilot-deep-dive | AI notes cleaner than human, sentiment arc |
| 7 | Genesys — Eir Case Study | https://www.genesys.com/customer-stories/eir | 1 min saved/call, 3-4 second generation |
| 8 | Five9 — AI Summaries Product Page | https://www.five9.com/products/capabilities/ai-summaries | 40% time savings |
| 9 | Five9 — Agent Assist Summaries Blog | https://www.five9.com/blog/agentassistsummaries | 150-300 word sweet spot, summary value |
| 10 | Five9 — Forrester 120s Saved | https://www.five9.com/blog/beyond-call-how-ai-task-automation-boosts-agent-productivity | 120 seconds saved per contact |
| 11 | Amazon Connect — Gen AI Summarization | https://aws.amazon.com/blogs/machine-learning/use-generative-ai-to-increase-agent-productivity-through-automated-call-summarization/ | Mid-call transfer summaries, architecture |
| 12 | Observe.AI — Summarization AI | https://www.observe.ai/blog/summarization-ai | 6 min avg ACW, entity extraction, 40% re-listen problem |
| 13 | ASAPP — Call Summarization Case Study | https://www.asapp.com/blog/a-contact-center-case-study-about-call-summarization-strategies | Incremental > rewrite, agent preference |
| 14 | Talkdesk — Copilot Summarization | https://support.talkdesk.com/hc/en-us/articles/16761287647259-Copilot-Automatic-Summarization-Agent-Next-Steps-and-Disposition | Summary + disposition + next steps panel |
| 15 | arXiv — Incremental Summarization | https://arxiv.org/abs/2510.06677 | 3-9% handling time reduction, agents prefer temporal order |
| 16 | arXiv — Recursive Summarization for Dialogue | https://arxiv.org/abs/2308.15022 | Rolling compaction approach validation |
| 17 | McKinsey — Contact Center Crossroads | https://www.mckinsey.com/capabilities/operations/our-insights/the-contact-center-crossroads-finding-the-right-mix-of-humans-and-ai | Reduced ACW as top AI benefit |
| 18 | McKinsey — Economic Potential of Gen AI | https://www.mckinsey.com/capabilities/tech-and-ai/our-insights/the-economic-potential-of-generative-ai-the-next-productivity-frontier | 14% resolution increase, 9% handling time reduction |
