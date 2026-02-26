Key links organized by what is most applicable to this application — Salesforce + Genesys specifically, and then the broader industry pattern:

---

## Salesforce Service Console — 3-Column Layout (Official Documentation)

The most directly relevant sources confirming Salesforce's out-of-the-box 3-column agent layout:

**1. Salesforce Trailhead — "Learn How to Use the Preconfigured Console"**
https://trailhead.salesforce.com/content/learn/modules/service-cloud-essentials-features/learn-how-to-use-the-preconfigured-console

This is Salesforce's own training module stating that the agent workspace offers a three-column layout out of the box that helps agents spot what they need to quickly respond to customer issues, with case details, contact details, and related cases all displayed on one screen.

**2. Salesforce Trailhead — "Maximize Service Cloud Lightning Features"**
https://trailhead.salesforce.com/content/learn/modules/lex_migration_whatsnew/lex_migration_whatsnew_service

This details the three columns explicitly: the first column shows case details, contact details, and related cases; the second column includes a highlights panel and compact case feed; the third column includes related lists and Knowledge articles. It also describes the utility bar at the bottom with Omni-Channel and CTI softphone access.

**3. Salesforce Trailhead — "Service Cloud for Agents"**
https://trailhead.salesforce.com/content/learn/modules/service-cloud-agent-experience/learn-about-service-cloud-for-agents

This confirms the same layout from the agent's perspective: split view with list view plus workspace tabs, first column with case/contact/related records, second column with highlights panel and case feed, third column with related lists and knowledge articles, and a utility bar at the bottom.

---

## Genesys + Salesforce Integration (Directly Relevant to Your Stack)

**4. Genesys Cloud for Salesforce in Service Cloud — Official Genesys Docs**
https://help.genesys.cloud/articles/genesys-cloud-for-salesforce-in-service-cloud/

This is Genesys's official documentation confirming that Genesys Cloud for Salesforce runs inside Service Cloud and provides agents with WebRTC phone pop/embed, workspace transfers, embedded interactions for scripts/chats/emails/messages, and Console API integration.

**5. About Genesys Cloud for Salesforce — Overview**
https://help.genesys.cloud/articles/about-genesys-cloud-for-salesforce/

This confirms Genesys Cloud for Salesforce works with Service Cloud, Lightning Experience, and Salesforce Omni-Channel. Administrators can set up AI-powered tools like Agent Assist and Agent Copilot within the interaction window to help agents enhance productivity.

**6. CX Cloud from Genesys and Salesforce — Genesys Product Page**
https://www.genesys.com/capabilities/cloud-and-salesforce

This is the joint Genesys/Salesforce product page describing their natively combined AI-powered solution. It explains how integrating Genesys Cloud into the Salesforce interface streamlines the employee experience, and how agents can surface Genesys digital channels including web messaging, SMS, and WhatsApp natively within the Salesforce messaging component.

**7. CX Cloud from Genesys and Salesforce — Salesforce AppExchange**
https://appexchange.salesforce.com/appxListingDetail?listingId=7f59a36f-86c0-4cac-b8af-2c1722ede4d1

The official AppExchange listing describes CX Cloud as a jointly released, native solution that combines a unified AI-powered agent workspace in Salesforce with enterprise contact center and workforce engagement management capabilities from Genesys Cloud.

**8. Genesys Agent Desktop Configuration in Salesforce Console**
https://docs.genesys.com/Documentation/PSAAS/latest/Administrator/DeployADSalesforce

The technical deployment guide for embedding Genesys Agent Desktop within Salesforce Console, including screen pop configuration and workspace transfer setup.

---

## Zendesk Agent Workspace (Confirming Same Pattern)

**9. About the Zendesk Agent Workspace**
https://support.zendesk.com/hc/en-us/articles/4408821259930-About-the-Zendesk-Agent-Workspace

Zendesk's official documentation shows the same multi-panel pattern: agents work across channels within a single ticket interface, with customer context and interaction history on the right side via a context panel, and a conversation thread in the center.

**10. About Custom Layouts with Layout Builder — Zendesk**
https://support.zendesk.com/hc/en-us/articles/5447690090138-About-custom-layouts-with-layout-builder

Zendesk's layout builder docs confirm the standard layout structure: ticket properties on the left side, ticket conversations in the middle, and a context panel on the right — the same 3-panel pattern.

---

The key takeaway for your specific situation: since we're already on Salesforce and plan to use Genesys, Layout A maps almost exactly to what our agents will see in production. The Genesys interaction window (call controls, transcription, agent assist) embeds directly into Salesforce Service Console's 3-column framework via the CX Cloud integration. The UI prototype built mirrors this standard — our agents' real workspace will have the conversation list/queue on the left, active interaction in the center, and customer context + AI panels on the right.




**The panel has 7 functional sections across 3 tabs:**

**Tab 1 — Summary & Notes (primary view)**
- **AI-Generated Summary** — Structured with headline, contact reason, key details, actions taken (with checkmarks), resolution, and a sentiment trend arc. This isn't just a blob of text — agents can scan it in seconds because it mirrors how Genesys Copilot structures its output (reason, resolution, wrap-up code).
- **Editable Wrap-Up Notes** — AI pre-drafts the notes, but the agent can review and edit before saving. This is the pattern Genesys uses — agents are presented with notes to read, edit if necessary, and save, rather than writing from scratch.
- **Disposition Code Picker** — Agent Copilot can suggest up to three predicted wrap-up codes when the agent begins after-call work, each shown with a confidence score. One click to select.
- **Follow-Up Actions** — AI-extracted next steps with assignee and due date, checkable as the agent completes them.
- **Agent Feedback** — Thumbs up/down to train the model, matching Genesys's pattern where agents rate the information using thumbs up/down buttons to verify as relevant or irrelevant.

**Tab 2 — CRM Fields**
- **Salesforce Case Auto-Fill Preview** — Shows 10 fields AI extracted from the transcript (case subject, type, root cause, product SKU, order number, etc.) with source labels showing whether each came from AI inference or direct transcript extraction. This maps to the pattern where the API populates relevant fields in customer profiles, call records, and support tickets. On save, all fields sync to Salesforce.

**Tab 3 — Quality**
- **Compliance Checklist** — Items auto-checked by AI during the call (identity verification, order confirmed, etc.) with progress bar. Matches Genesys Agent Copilot's checklist of up to seven items that can be automatically checked as complete based on text or voice detection.
- **Interaction Metrics** — Handle time, hold time, transfers, FCR, sentiment score, compliance score.

**Persistent elements:** ACW timer in the header (color-coded by elapsed time), call metadata bar, and a one-click "Save & Complete" that simulates syncing everything to Salesforce simultaneously.

The key insight from the research: the biggest ROI isn't the summary itself — it's eliminating the 5+ separate tasks agents do during wrap-up (write notes, pick disposition, update case fields, create follow-ups, complete checklist) and collapsing them into a single review-and-save flow.

---

**Approach 1: Full-Transcript Post-Call Summarization (Industry Default)**

This is what Genesys, Amazon LCA, Five9, and most production systems actually do. After the call ends, a Lambda function reads the persisted transcript from DynamoDB, generates an LLM prompt, and runs an LLM inference with Amazon Bedrock. The generated summary is persisted and can be used by the agent. LCA summarizes call transcripts once the call is over.

The architecture is straightforward: stream audio → transcribe in real-time → persist each transcript segment to a datastore → when the call ends, read the full transcript, send it to the LLM in one shot, return the structured summary. Genesys does the same thing — the system generates immediate post-interaction summaries with features like sentiment analysis and flexible formatting, using custom prompts that control tone, length, and structure.

**Why this is the default:** Quality. When the LLM sees the entire conversation, it can identify what actually mattered — the real resolution, the sentiment arc, the commitments made. It knows the ending, so it can distinguish between a complaint that was resolved versus one that escalated. Latency for a typical 5-minute call transcript is manageable — median end-to-end latency of around 420ms to 580ms in cached flows, and 860ms to 1,240ms in non-cached flows for structured summaries. Even a longer call hitting 2-3 seconds is fine because the agent is already in wrap-up mode.

---

**Approach 2: Incremental / Progressive Summarization (Emerging, More Complex)**

This is exactly the compaction model you described. There's a recent production-deployed research paper (October 2025) that validates this approach specifically for customer support. They introduce a real-time incremental notes generation system that intelligently determines optimal moments to generate concise notes using a summarization LLM and a subsequent relevance classifier. Deployed in production, the system reduces average handling time by 3%, and up to 9% for complex scenarios.

Their architecture triggers the LLM at each new message, using the pattern: previous summary + new transcript chunk → updated summary. The progressive note-taking workflow triggers LLM inference at every new message or phone call, with p50 latency of 600ms and p95 of 2 seconds. They use a fine-tuned Mixtral-8x7B model (not a generic API call) with a DeBERTa classifier to filter trivial updates.

The recursive summarization research confirms the pattern works well for long conversations. The LLM is first prompted to produce a summary given a short dialog context, then asked to continue updating and generate a new summary by combining the previous memory and subsequent dialogues.

**But here's the catch:** This approach has real tradeoffs. The very nature of summarization means that some details, especially infrequent ones, might get lost in the process, and there's a risk of **contextual drift** — over multiple rounds of summarization, the chatbot's understanding of the conversation could gradually shift away from its original meaning. For contact centers specifically, if you miss one "refund" request buried deep in the conversation, that account churns before anyone reviews the ticket.

---

**Approach 3: Hybrid — The Recommended Architecture for Your Case**

Amazon LCA actually supports both, and this is what I'd recommend for an industrial distributor. LCA allows the option to call the summarization function during the call, because at any time the transcript can be fetched and a prompt created, even if the call is in progress. This can be useful for when a call is transferred to another agent or escalated to a supervisor.

The hybrid architecture looks like this:

**During the call:** Stream and persist every transcript segment in real-time (this is your Genesys transcription → datastore pipeline). Don't run rolling compaction — instead, use the live transcript as input for **lightweight, discrete extractions**: entity detection (order numbers, SKUs, product names), intent classification, sentiment per turn, and knowledge article matching. These are cheap, fast operations that don't need full summarization.

**At call end:** Read the full persisted transcript, send it to the LLM in one shot with your structured prompt template (issue, actions, resolution, disposition, next steps, CRM fields). This gives you the highest-quality summary because the model has full context including how the conversation ended.

**On transfer / escalation (mid-call):** This is the one scenario where a mid-call summary matters. If an agent transfers, trigger a summary from the transcript-so-far so the receiving agent gets context without the customer repeating themselves. Genesys already handles this — when using transferred voice interactions, the transferring agent and receiving agent both get a summary of the pre-transferred call.

---

**Why not rolling compaction for our MVP?**

Three practical reasons. First, our typical customer service call is likely 3-8 minutes — that's maybe 2,000-4,000 tokens of transcript, well within any modern LLM's context window without any compaction needed. Rolling summarization solves a problem you don't have yet. Second, every rolling summarization cycle is an LLM inference call, which means cost multiplied by the number of compaction cycles per call — for a 5-minute call you might run 8-10 inferences instead of 1. Third, the quality risk: if the model drops a specific SKU number or an order ID during an intermediate compaction, it's gone forever because we've discarded the original text. With full-transcript summarization, the model always has access to every word spoken.

**When rolling compaction *would* make sense:** If we later expand to multi-session customer journeys (a customer calls back three times about the same issue across days/weeks), compacting older session transcripts into summaries while keeping the current session full is the right pattern. That's the hierarchical architecture that mirrors how human memory actually works, with different systems handling different types of information retention.

**Bottom line for our build:** Persist every transcript segment as it streams in. Generate the structured summary from the full transcript at call end. Save the full transcript alongside the summary so one can always re-generate if prompts improve. This is what Genesys, Amazon LCA, and Observe.AI all do in production, and it gives us the best quality with the simplest architecture.