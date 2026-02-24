# Customer Service Agent Workflow & Best-in-Class UI Research

## Understanding the Project Context

The project description you shared mentions a system that will eventually "support multiple concurrent conversations, persist conversation data, and assist agents with additional real-time insights," with the current scope focused on "core streaming and summarization workflow." This maps directly to a well-established product category: **AI-powered Agent Assist / Real-Time Agent Desktop** — a tool that sits alongside (or embedded within) a customer service agent's workspace, providing live transcription, summarization, and AI-driven insights during calls or chats.

Here's what you need to know to build a best-of-class version.

---

## Part 1: The Typical Customer Service Agent Workflow

### The Call Lifecycle (Voice)

A typical inbound voice call follows these phases:

1. **Pre-Call (Screen Pop):** Before the agent even speaks, the system surfaces the customer's identity, account info, interaction history, and reason for calling (from IVR data or intent detection). This is called a "screen pop" — the CRM record automatically appearing on screen.

2. **Active Call — Discovery:** The agent greets the customer, identifies their issue, and searches for relevant information. This is the most cognitively demanding phase — the agent is simultaneously listening, typing notes, navigating systems, and thinking about solutions.

3. **Active Call — Resolution:** The agent works through the issue — looking up knowledge base articles, executing system actions (refunds, updates, escalations), and communicating the resolution.

4. **Wrap-Up / After-Call Work (ACW):** After the customer hangs up, the agent writes up a summary/disposition, selects category codes, updates the CRM, and marks the ticket. This phase typically takes 30-90 seconds and is where AI summarization delivers the most obvious ROI.

5. **Ready / Available:** The agent sets their status back to available and enters the queue for the next interaction.

### The Pain Points

Research and industry experts consistently identify these agent frustrations:

- **The "Swivel Chair" Problem:** Agents toggle between 10-20+ applications — CRMs, knowledge bases, billing systems, ticketing tools, spreadsheets, and even sticky notes. Zendesk reports this as the single biggest productivity killer.
- **Manual Note-Taking During Calls:** Agents try to listen and type simultaneously, leading to incomplete notes and divided attention.
- **Repetitive After-Call Work:** Writing up the same types of summaries over and over, selecting disposition codes, updating multiple systems.
- **Context Loss on Transfers:** When a call gets escalated or transferred, the next agent often starts from scratch because context didn't travel with the customer.
- **Information Overload:** Too much data on screen with no intelligence about what's relevant *right now*.

---

## Part 2: How Agents Handle Multiple Conversations

### Important Distinction: Voice vs. Text Channels

The project's mention of "multiple concurrent conversations" likely refers to one of two models:

**Model A — Blended Agent (Most Common):**
Agents handle different *types* of interactions across channels — e.g., one voice call at a time, but can also handle 2-4 concurrent chats or emails during gaps. Contact center platforms like NICE CXone, 8x8, and Talkdesk allow admins to configure "blending rules," such as: "While on a phone call, the agent can also receive up to 2 chats" or "While handling chats, the agent can receive emails but not calls." The key insight is that **voice calls are exclusive** (one at a time), while text-based channels can be concurrent.

**Model B — Chat Concurrency:**
For chat-only or chat-heavy agents, the standard is 2-3 concurrent chat sessions, with some experienced agents handling up to 6. The natural "lag time" between customer messages creates windows for the agent to context-switch. Industry best practice (from COPC and others) recommends starting at 3 concurrent chats and adjusting based on complexity and skill level.

**Model C — Supervisor/Observer View (Likely What Your Project Means):**
A supervisor or QA analyst monitors *multiple active calls simultaneously* — not participating, but observing transcripts, sentiment, and alerts across many conversations at once. This is what Observe.AI's "Real-Time Supervisor Assist" provides: a "mission control" dashboard showing all active calls with the ability to drill into any one.

### For Your Project

Given the project focuses on "streaming and summarization," the "multiple concurrent conversations" likely means displaying a **list of active/recent conversations** that an agent or supervisor can monitor, with the ability to drill into any one to see the live transcript and AI insights. Think of it like a dashboard with conversation cards that you can expand.

---

## Part 3: The Agent Desktop UI — What Best-in-Class Looks Like

### The "Single Pane of Glass" Principle

Every major player (Zendesk, Salesforce, NICE, Talkdesk, Genesys) has converged on the same core principle: **unified workspace**. Instead of 20 tabs, one screen with intelligently surfaced, contextual information. The key is *not* dumping all data on screen — it's surfacing only what's relevant to the current task.

### Canonical Layout (What Industry Leaders Use)

The best agent desktops follow a consistent 3-panel layout:

```
┌─────────────────────────────────────────────────────────────────┐
│  Top Bar: Agent status, queue info, notifications, settings     │
├──────────────┬──────────────────────┬──────────────────────────-┤
│              │                      │                           │
│  LEFT PANEL  │   CENTER PANEL       │   RIGHT PANEL             │
│  Nav / Queue │   Active Convo       │   Context / AI Assist     │
│              │                      │                           │
│  - Active    │   - Live transcript  │   - Customer profile      │
│    convos    │   - Chat thread      │   - Interaction history   │
│  - Waiting   │   - Call controls    │   - Knowledge articles    │
│  - Recent    │   - Reply composer   │   - AI suggestions        │
│              │                      │   - Sentiment indicator   │
│              │                      │   - Summary (live)        │
│              │                      │   - Checklist / script    │
│              │                      │                           │
├──────────────┴──────────────────────┴───────────────────────────┤
│  Bottom Bar (optional): Quick actions, templates, escalation    │
└─────────────────────────────────────────────────────────────────┘
```

### Panel-by-Panel Breakdown

#### Left Panel — Conversation List / Queue
- List of active conversations (cards with customer name, topic, duration, sentiment emoji)
- Visual indicators: unread messages, waiting time, priority level, channel icon (phone/chat/email)
- Click to switch between conversations
- Filter/sort by status, channel, priority
- **Best practice (Zendesk):** Conversations ordered by urgency with color-coded status badges

#### Center Panel — The Active Conversation
- **For Voice Calls:** Live scrolling transcript with speaker labels (Agent / Customer), timestamps, and highlighted keywords/entities. Partial transcripts appear in real-time and finalize. Call controls (mute, hold, transfer, record) are overlaid or docked at top.
- **For Chat:** Standard chat thread with the reply composer at bottom
- **Key UX detail:** Newest content at bottom, auto-scroll with "pinned to bottom" behavior, but allow scroll-up to review without disrupting the stream
- **Best practice (Amazon LCA):** Color-code speakers (blue for agent, gray for customer), show sentiment per turn with a small indicator

#### Right Panel — Context & AI Assist
This is where the AI-powered magic lives, and it's the most critical panel for your project:

- **Customer Context Card:** Name, account ID, plan/tier, contact info, recent orders/tickets — pulled from CRM
- **Interaction History Timeline:** Previous calls, chats, emails with dates and quick summaries
- **AI-Powered Sections:**
  - **Live Summary:** A continuously updating summary of the current conversation (the "streaming summarization" your project describes)
  - **Suggested Knowledge Articles:** Clickable tiles surfaced based on detected intent — title + preview snippet (Google CCAI pattern)
  - **Next-Best-Action Suggestions:** Recommended responses, upsell opportunities, or process steps
  - **Compliance Checklist:** Dynamic checklist that checks off items as the agent covers required topics (e.g., "Verified identity ✓", "Offered warranty ✓")
  - **Sentiment Gauge:** Real-time customer sentiment (positive/neutral/negative) with trend
  - **Agent Q&A:** A search/chat box where the agent can ask the AI copilot a question mid-call
- **Best practice (Creovai, Observe.AI):** These sections are collapsible/expandable accordion-style so agents see what they need without scroll overwhelm

### Specific UI Patterns from Leaders

| Company | Key UI Innovation |
|---------|-------------------|
| **Zendesk Agent Workspace** | Unified status menu across channels; context panel toggles between customer info, apps, and knowledge; conversation order oldest-to-newest for natural reading |
| **NICE CXone Agent** | 30+ channel types in one view; AI "Enlighten" provides real-time behavioral guidance; handles voice + digital simultaneously |
| **Talkdesk Agent Workspace** | Industry-specific pre-built layouts; AI automates manual tasks and provides step-by-step guidance; single-screen access to all tools |
| **Salesforce Service Cloud** | Einstein AI surfaces case predictions, article recommendations, and auto-populates fields; "Service Console" is the canonical multi-panel layout |
| **Google CCAI Agent Assist** | Knowledge articles as clickable tiles with title + preview; sentiment analysis panel; generative AI session summarization at wrap-up; agents can manually search the knowledge base |
| **Amazon LCA** | Call list page with at-a-glance cards (duration, sentiment trend, categories); call detail page with turn-by-turn transcript + inline agent assist messages; agent assist bot widget for on-demand queries |
| **Observe.AI** | Real-time supervisor "mission control" across all active calls; agents can "raise hand" for help; AI auto-captures notes with dollar amounts and dates |
| **Cresta Agent Assist** | Learns from top performers; reduces typing by 50% with AI-suggested responses; works across voice, chat, and email |
| **Comcast "Einstein"** | Consolidated 20+ desktop apps into one; same knowledge base powers agent tools, website, and self-service apps; 87% of agents say it helps them do their job |

---

## Part 4: Considerations for this project's UI

Given the project scope (streaming transcription + summarization, expanding to multi-conversation and real-time insights):

### MVP (Current Scope: Core Streaming & Summarization)

1. **Live Transcript View (Center Panel)**
   - Real-time scrolling transcript with speaker diarization (Agent vs. Customer)
   - Color-coded speakers
   - Timestamps on each turn
   - Auto-scroll behavior with "scroll lock" when user scrolls up
   - Visual indicator for "live" / "streaming" state (pulsing dot or waveform)

2. **Running Summary (Right Panel or Collapsible Sidebar)**
   - AI-generated summary that updates as the conversation progresses
   - Clearly labeled sections: "Issue," "Key Points," "Resolution" (or similar)
   - Visual cue when summary updates (subtle highlight/animation)

3. **Call Controls / Status Bar (Top)**
   - Duration timer
   - Connection status indicator
   - Mute/unmute, pause/resume controls

### Phase 2 (Multiple Conversations)

4. **Conversation List (Left Panel)**
   - Cards for each active conversation: customer name/ID, duration, channel icon, sentiment badge
   - Click to switch; active conversation highlighted
   - "New conversation" and status indicators (live, on-hold, wrap-up, completed)
   - Visual density optimized — enough info to triage at a glance, not so much it's overwhelming

5. **Persistent Conversation Data**
   - Completed conversations remain accessible with their transcript + summary
   - Searchable history
   - Sortable by date, customer, topic, sentiment

### Phase 3 (Real-Time Insights / Agent Assist)

6. **Knowledge Assist Panel**
   - Auto-surfaced articles based on detected conversation topics
   - Clickable tiles (title + snippet)
   - Manual search capability

7. **Sentiment & Tone Indicators**
   - Per-turn sentiment badges or a rolling sentiment trend line
   - Alerts when sentiment drops sharply

8. **AI Copilot / Q&A**
   - Inline chat where agent can ask the AI a question about the current conversation
   - Quick-action buttons: "Summarize so far," "Suggest response," "Find related article"

9. **Supervisor View**
   - Grid/list of all active conversations with key metrics
   - Ability to "listen in" to any conversation's transcript in real-time
   - Alerts for negative sentiment or compliance issues

### Design Principles Followed

1. **Progressive Disclosure:** Don't show everything at once. Use collapsible panels, tabs, and drill-down patterns. Surface the minimum needed for the current task.

2. **Reduce Cognitive Load:** The agent is already listening to a customer. The UI should support their attention, not compete for it. Use subtle animations, not flashy alerts. Information should be glanceable.

3. **Speed Over Beauty:** Every click and every second of load time matters. Agents handle hundreds of interactions daily. Optimize for keyboard shortcuts, minimal clicks, and instant response.

4. **Contextual Intelligence:** Don't just display data — surface *relevant* data. The right knowledge article at the right moment is worth more than a complete knowledge base.

5. **Seamless Channel Switching:** If/when you support multiple channels, the conversation thread should be unified. A customer who starts on chat and calls back should have one continuous record.

6. **Accessibility:** Many contact center agents work 8+ hour shifts. Use readable font sizes (14px+ for body text), sufficient contrast, and dark mode option. The Lalinda Dias UX research noted that some agent populations skew older and less comfortable with complex mouse navigation — design for keyboard-first interaction where possible.

---

## Key Metrics That Drive UI Decisions

When designing for contact centers, every UI choice maps back to a measurable outcome:

| Metric | What It Measures | UI Impact |
|--------|-----------------|-----------|
| **AHT (Average Handle Time)** | Total time from answer to wrap-up | Reducing clicks, auto-populating fields, AI summaries all reduce AHT |
| **ACW (After-Call Work)** | Time spent on post-call tasks | AI summarization is the #1 lever here — can reduce ACW by 50%+ |
| **FCR (First Contact Resolution)** | % resolved on first contact | Knowledge assist and context surfacing help agents resolve without transfers |
| **CSAT (Customer Satisfaction)** | Post-interaction customer rating | Less time on hold, more personalized service, faster resolution |
| **Agent Satisfaction** | Internal agent engagement | Unified workspace, less app-switching, AI support for tedious tasks |

---

## Summary

Your project sits squarely in the "AI Agent Assist" category — one of the hottest areas in contact center technology. The core workflow you're building (audio streaming → real-time transcription → AI summarization) is the foundation that every major player builds on. The UI patterns are well-established: a 3-panel layout with conversation list, active transcript, and contextual AI sidebar. The companies that execute best (Observe.AI, Cresta, NICE, Zendesk) differentiate on **intelligence** (surfacing the right info at the right moment) and **speed** (zero-latency transcription, instant suggestions).

Build the streaming + summarization core solidly, design the conversation list to scale to concurrent sessions, and leave clear extension points for knowledge assist and sentiment analysis — and you'll have a best-of-class foundation.
