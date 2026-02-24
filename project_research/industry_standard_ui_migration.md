I've reviewed all your frontend code and the research documentation. Let me give you a clear architectural recommendation that maps your existing components to the industry-standard 3-panel layout while adding the wrap-up capabilities you need.

## The Problem With Your Current Layout

Your current `page.tsx` uses a **2-panel split** (50/50 grid: transcript left, summary + MCP right). This doesn't match the industry standard and — more critically — it has no place for customer context, no wrap-up flow, no disposition codes, and no case field management. The customer's identity is completely absent from the screen.

## Recommended Layout: 3-Panel + Header + ACW Modal

Here's what I recommend, mapped directly to what Genesys + Salesforce delivers and what your code currently supports:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  HEADER BAR                                                              │
│  [ConnectionStatus] [Agent Status: On Call ▼] [ACW Timer: --:--]        │
│  Conversation: {id}                                              [⚙️]   │
├────────────┬─────────────────────────────┬───────────────────────────────┤
│            │                             │                               │
│  LEFT      │   CENTER                    │   RIGHT                       │
│  240px     │   flex                      │   340px                       │
│            │                             │                               │
│  ┌──────┐  │   ┌─────────────────────┐   │   ┌───────────────────────┐   │
│  │CALLER│  │   │                     │   │   │  AI Summary           │   │
│  │INFO  │  │   │  TranscriptViewer   │   │   │  (SummaryViewer)      │   │
│  │Card  │  │   │  (your existing     │   │   │  - Current streaming  │   │
│  │      │  │   │   component)        │   │   │  - Version history    │   │
│  │Name  │  │   │                     │   │   │  - Frequency slider   │   │
│  │Acct# │  │   │  Live transcript    │   │   │                       │   │
│  │Email │  │   │  scrolling with     │   │   ├───────────────────────┤   │
│  │Co.   │  │   │  speaker colors     │   │   │                       │   │
│  └──────┘  │   │                     │   │   │  MCP Suggestions      │   │
│            │   │                     │   │   │  (MCPSuggestionsBox)  │   │
│  ┌──────┐  │   │                     │   │   │  - Product info       │   │
│  │CALL  │  │   │                     │   │   │  - Order lookups      │   │
│  │INFO  │  │   │                     │   │   │  - AI recommendations │   │
│  │      │  │   │                     │   │   │                       │   │
│  │Queue │  │   │                     │   │   ├───────────────────────┤   │
│  │Time  │  │   │                     │   │   │                       │   │
│  │Type  │  │   │                     │   │   │  Compliance Checklist │   │
│  │Xfers │  │   │                     │   │   │  ☑ ID Verified        │   │
│  └──────┘  │   │                     │   │   │  ☑ Order Confirmed    │   │
│            │   │                     │   │   │  ☐ Resolution Given   │   │
│  ┌──────┐  │   └─────────────────────┘   │   │                       │   │
│  │HIST  │  │                             │   └───────────────────────┘   │
│  │      │  │                             │                               │
│  │Prev  │  │                             │                               │
│  │calls │  │                             │                               │
│  │list  │  │                             │                               │
│  └──────┘  │                             │                               │
├────────────┴─────────────────────────────┴───────────────────────────────┤
│  UTILITY BAR (bottom)                                                    │
│  [📞 Call Controls] [🔇 Mute] [⏸ Hold] [↗ Transfer] [⏹ End Call]       │
└──────────────────────────────────────────────────────────────────────────┘
```

**When agent clicks "End Call" → ACW state triggers → overlay/modal appears:**

```
┌──────────────────────────────────────────────────────────────────┐
│  AFTER CALL WORK                              ACW Timer: 01:47  │
│                                                [color-coded]     │
├──────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │ Summary &   │ │ CRM Fields  │ │ Quality     │               │
│  │ Notes    ◄──┘ │             │ │             │               │
│  └─────────────────────────────────────────────┘               │
│                                                                  │
│  TAB 1: Summary & Notes                                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ AI-Generated Summary                                       │ │
│  │ ┌──────────────────────────────────────────────────────┐   │ │
│  │ │ Headline: Customer called about damaged order         │   │ │
│  │ │ Contact Reason: Product damage in shipping            │   │ │
│  │ │ Key Details: Order #4421890, 3x safety gloves         │   │ │
│  │ │ Actions: ✓ Verified order ✓ Initiated replacement     │   │ │
│  │ │ Resolution: Replacement order created, ships tomorrow │   │ │
│  │ │ Sentiment: Frustrated → Satisfied ↗                   │   │ │
│  │ └──────────────────────────────────────────────────────┘   │ │
│  │                                    [👍] [👎] Agent Feedback │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │ Wrap-Up Notes (editable)                                   │ │
│  │ ┌──────────────────────────────────────────────────────┐   │ │
│  │ │ AI pre-drafted notes here, agent can edit...         │   │ │
│  │ └──────────────────────────────────────────────────────┘   │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │ Disposition Code          [AI Suggested ▼]                 │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │ │
│  │ │ Product      │ │ Shipping     │ │ Replacement  │       │ │
│  │ │ Damage  92%  │ │ Issue   78%  │ │ Request  71% │       │ │
│  │ └──────────────┘ └──────────────┘ └──────────────┘       │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │ Follow-Up Actions                                          │ │
│  │ ☐ Ship replacement order — Warehouse — Due: Tomorrow      │ │
│  │ ☐ Send confirmation email — Auto — Due: Today             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│           [ Save & Complete ACW ]                                │
└──────────────────────────────────────────────────────────────────┘
```

## What Goes Where — The Rationale

**LEFT PANEL (new — you don't have this yet)**

This is where the customer identity you said is missing goes. It needs three cards stacked vertically:

1. **Caller Info Card** — Customer name, account number, email, company name. This is the screen pop data. In production Genesys populates this from the IVR/ANI lookup against Salesforce. For your build, you'd pass this as part of the conversation creation or fetch it from a mock customer API. This card should be visible at all times — it's the single most-glanced element on an agent's screen.

2. **Call Metadata Card** — Queue name, channel type, call duration timer, number of transfers, whether this is a callback. This maps to what Genesys puts in the Voice Call record header and what your `ConnectionStatus` component partially covers (but currently only shows connection state, not call state).

3. **Interaction History** — A compact list of prior interactions for this customer (date, channel, brief topic). Agents check this constantly to avoid asking the customer to repeat themselves. In production this comes from Salesforce case history. For your build, mock data is fine — the important thing is that the panel exists in the layout.

**CENTER PANEL (your existing TranscriptViewer — keep it)**

Your `TranscriptViewer.tsx` is solid. The only change: it should take the full center column height. Currently it shares the 50% right panel with summary. In the 3-panel layout it gets its own column and becomes the primary workspace the agent watches during the call. One small UX note: your current reverse-chronological (newest at top) is unusual. Most agent desktops put newest at bottom with auto-scroll. I'd consider making this configurable or switching to newest-at-bottom to match what Salesforce and Genesys show agents.

**RIGHT PANEL (restructured — your SummaryViewer + MCPSuggestionsBox + new checklist)**

This becomes the AI assist column. Stack three sections:

1. **SummaryViewer** (your existing component) — stays mostly as-is. The rolling summaries during the call are your differentiator. Keep the frequency slider, version history, and streaming typewriter effect. This runs during the active call. At call end, the final summary feeds into the ACW panel.

2. **MCPSuggestionsBox** (your existing component) — this is your agentic tool panel. Expand it from the "coming soon" placeholder to show real-time product lookups, order status, and AI recommendations based on transcript context. This is the equivalent of Genesys Agent Copilot's knowledge surfacing feature.

3. **Compliance Checklist** (new component) — A short checklist of items that can be auto-checked by your system based on transcript analysis (identity verified, order confirmed, resolution provided, etc.). This maps directly to Genesys Agent Copilot's checklist of up to 7 items. During the call, items check off automatically as the AI detects them in the transcript.

**HEADER BAR (restructured)**

Your current header just shows the app title and `ConnectionStatus`. Expand it to show: agent status dropdown (Available / On Call / ACW / Break), the ACW countdown timer (hidden during active call, appears when call ends), and the conversation ID. Move the connection status indicator into this bar. This maps to the Salesforce Omni-Channel utility bar + the Genesys ACW timer.

**UTILITY BAR (new — bottom of screen)**

Call control buttons: mute, hold, transfer, end call. These are currently not in your UI at all. Even if they're non-functional for the prototype, having them present shows the complete agent workflow. This maps to the Salesforce Service Cloud Voice call controls and the Genesys softphone tray.

**ACW PANEL (new — appears on "End Call")**

This is the big addition and the core of what you asked about. It's either a modal overlay or a state change that replaces the center panel (I'd recommend an overlay so the transcript stays visible behind it for reference). It has the 3 tabs your research described:

- **Tab 1: Summary & Notes** — Takes the final summary from your `SummaryViewer`, presents it in structured format (not raw text), adds editable wrap-up notes (AI pre-drafted), disposition code picker with AI-suggested codes and confidence scores, follow-up action items, and thumbs up/down feedback.

- **Tab 2: CRM Fields** — Shows the 8-10 case fields AI extracted from the transcript (case subject, type, root cause, product SKU, order number, etc.) with labels indicating whether each came from AI inference or direct transcript extraction. On save, these would sync to Salesforce.

- **Tab 3: Quality** — The compliance checklist (carried over from the right panel with final state), plus interaction metrics (handle time, hold time, transfers, sentiment score).

A single "Save & Complete" button at the bottom that commits everything simultaneously.

## Changes To Your Existing Components

**`page.tsx`** — Change `gridTemplateColumns: '1fr 1fr'` to `gridTemplateColumns: '240px 1fr 340px'`. Add state for `callPhase: 'pre-call' | 'active' | 'acw' | 'complete'` to control which panels and overlays are visible. Add customer data state.

**`grainger-tokens.ts`** — Add tokens for the new ACW panel colors (the timer color coding: green < 60s, yellow 60-90s, red > 90s), tab active/inactive states, and checklist item states.

**`SummaryViewer.tsx`** — No major changes during the active call phase. But you need a prop or mode switch so that when ACW triggers, the final summary can be passed to the ACW panel in structured format rather than raw streaming text.

**`MCPSuggestionsBox.tsx`** — Remove the "Coming Soon" badge and dashed border when it's ready. The component structure is correct — just needs the actual MCP integration.

**`ConnectionStatus.tsx`** — Expand to show call phase state (not just WebSocket connection), or create a separate `CallStatus` component that sits in the header.

## New Components You'll Need

1. **`CallerInfoCard.tsx`** — Customer name, account number, email, company. Pulled from conversation metadata or a customer lookup API.
2. **`CallMetadataCard.tsx`** — Duration timer, queue, channel, transfers.
3. **`InteractionHistory.tsx`** — List of prior contacts for this customer.
4. **`ComplianceChecklist.tsx`** — Checkable items, auto-check capability.
5. **`CallControlBar.tsx`** — Bottom utility bar with call action buttons.
6. **`ACWPanel.tsx`** — The big one. Tabbed overlay with Summary & Notes, CRM Fields, and Quality tabs. Contains sub-components for disposition picker, editable notes, case field preview, follow-up actions.
7. **`ACWTimer.tsx`** — Color-coded countdown timer in the header.

This gives you feature parity with what Genesys Agent Copilot + Salesforce Einstein deliver on the Voice Call record page, while preserving your differentiators (real-time rolling summaries during the call, MCP-powered product/order lookups). The layout matches the "Header with Three Regions" template that Genesys officially recommends for the Salesforce Voice Call record page.