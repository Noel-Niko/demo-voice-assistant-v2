# AI Call Summarization & Transfer Summary — Business Value Evidence

**Compiled: February 18, 2026**
**Purpose: Management justification for AI-powered after-call work (ACW) summarization and agent-to-agent transfer summaries**

All URLs below have been verified as live and accessible.

---

## 1. Genesys (Your Planned Audio Transcription Provider)

### Genesys Agent Copilot — Product Documentation

**URL:** https://help.genesys.cloud/articles/about-genesys-agent-copilot/
**What it confirms:** Genesys Agent Copilot provides after-call work automation, AI-generated conversation summaries, suggested wrap-up codes, and resolution tracking. Core summarization features include contact reason identification, resolution status, and sentiment analysis.

**URL:** https://help.genesys.cloud/articles/work-with-genesys-agent-copilot/
**What it confirms:** Genesys Agent Copilot generates a summary for each interaction. On call transfers, both the transferring agent and the receiving agent get a summary of the pre-transferred call. The receiving agent also gets a summary of their own interaction after concluding the call — directly validating the two primary use cases (ACW summary + transfer context).

**URL:** https://help.genesys.cloud/usecases/genesys-agent-copilot/
**What it confirms:** The official Genesys use case document. When agents move to after-call work, Genesys Cloud AI creates an interaction summary and predicts wrap-up codes. Agents review, edit, and save AI-generated notes to the system of record instead of writing from scratch.

### Genesys Agent Copilot — Deep Dive (Blog)

**URL:** https://www.genesys.com/blog/post/genesys-cloud-agent-copilot-deep-dive
**What it confirms:** Agents spend the entirety of every interaction speaking to the customer, knowing that the copilot is keeping track of what has happened. When the interaction ends, agents are presented with notes to read, edit if necessary, and save. Auto-summarization also ensures improved data quality for analytics — AI-generated notes are cleaner and more consistent than human-written notes. Veteran agents use suggested wrap-up codes to shorten after-call workload; novice agents require less training.

### Genesys Agent Copilot — Demo Page (Quantified Results)

**URL:** https://www.genesys.com/resources/genesys-agent-copilot-demo
**What it confirms:** Agent Copilot users have seen a **5-minute decrease in average handle time**, a **1.5-minute decrease in average hold time**, and a **2-minute decrease in after-call work time**. This is Genesys's own published benchmark data.

### Genesys Customer Story: Eir (Measured ROI)

**URL:** https://www.genesys.com/customer-stories/eir
**What it confirms:** Eir (Ireland's leading telecom) deployed Agent Copilot. Key results: **agents saving up to 1 minute per voice call** with auto-summarization and wrap-up code capabilities. Customer effort scores improved by **63%** and sales conversions increased by **10%**. AI-powered summarization generates notes within 3–4 seconds. Once reviewed by agents, notes automatically save to the CRM system.

### Genesys — Custom Summary Configuration

**URL:** https://help.genesys.cloud/articles/work-with-advanced-custom-summaries/
**What it confirms:** Genesys supports customizable summary formats (Issue-Actions-Resolution structure, paragraph or sections, controlled tone and length). This documents how summaries can be tailored to specific business needs and CRM field requirements — relevant for Salesforce integration planning.

### Genesys — ACW Component in Salesforce

**URL:** https://help.genesys.cloud/articles/configure-the-after-call-work-component/
**What it confirms:** Genesys Cloud's after-call work component can be embedded directly in the Salesforce Voice Call record page. Agents can view recommended wrap-up codes and AI-suggested interaction summaries through Agent Copilot — directly within Salesforce, not in a separate window. This is the native integration path for your Salesforce + Genesys stack.

---

## 2. Five9 (Independent Platform Validation)

### Five9 AI Summaries — Product Page

**URL:** https://www.five9.com/products/capabilities/ai-summaries
**What it confirms:** Five9 AI Summaries saves **up to 40% of an agent's time** by removing the need to write call notes and summaries. Summaries are generated in seconds using LLM technology. Customizable output formats for different business needs. Managers can use summaries to analyze agent interaction quality.

### Five9 Agent Assist 2.0 Launch — Press Release

**URL:** https://www.five9.com/news/news-releases/five9-introduces-agent-assist-20-ai-summary-powered-openai
**What it confirms:** Five9's official press release announcing AI Summary powered by OpenAI. States that call summarization is "the holy grail for Agent Assist" because it attacks "one of the biggest sources of cost for call handling." Summaries are essential for providing context so the next agent handling a call can understand the customer's interaction journey. No model training or manual categorization required.

### Five9 — TruConnect Case Study (Measured ROI)

**URL:** https://www.five9.com/news/news-releases/truconnectpr
**What it confirms:** TruConnect deployed Five9 Agent Assist with AI-powered call summarization. Results within 3 months: **30-second reduction in average handle time** per call. **7.5% cost savings** in year one. Expected **20% cost savings** in year two with CRM integration. The COO stated: "even efficient call centers can be improved by using the automated summaries."

### Five9 — TruConnect Case Study Download Page

**URL:** https://www.five9.com/resources/case-study/truconnect
**What it confirms:** Downloadable case study confirming all TruConnect metrics. Agent engagement and productivity increased. AHT reduced by 30 seconds. 7.5% savings in year one.

### Five9 — AI Summary Blog (Detailed Value Proposition)

**URL:** https://www.five9.com/blog/agentassistsummaries
**What it confirms:** Detailed breakdown of AI Summary value: reduces post-contact activity time (summaries generated in seconds vs. minutes of manual writing), enables quality monitoring and training, boosts customer satisfaction through better context on follow-up calls, and helps with compliance by capturing and storing call discussion.

### Five9 — Forrester TEI Study Results

**URL:** https://www.five9.com/news/news-releases/five9-ai-elevated-cx-platform-delivered-145m-business-value-and-212-roi-through
**What it confirms:** Forrester Total Economic Impact study found Five9 delivered **$14.5M in business value** and **212% ROI**. The study specifically credits AI Agents, Agent Assist, **post-call summarization**, and workflow automation as key value drivers. Based on a composite 500-agent organization.

### Five9 — Forrester Study: 120 Seconds Saved Per Contact

**URL:** https://www.five9.com/blog/beyond-call-how-ai-task-automation-boosts-agent-productivity
**What it confirms:** A Forrester study commissioned by Five9 found that for every contact reaching a live agent, brands save **120 seconds** by automating key activities including automatic summaries. Agents get AI-generated summaries and action items pushed into the CRM, saving time and improving follow-ups.

---

## 3. Amazon Web Services (Architecture Reference)

### AWS — Generative AI Call Summarization Blog

**URL:** https://aws.amazon.com/blogs/machine-learning/use-generative-ai-to-increase-agent-productivity-through-automated-call-summarization/
**What it confirms:** Detailed architecture for AI call summarization using Amazon Bedrock (with Claude as the LLM). The system streams audio, transcribes in real-time, persists transcript segments, then generates the summary after the call ends. Critically, it also supports mid-call summarization for transfers: "LCA allows the option to call the summarization function during the call... this can be useful for when a call is transferred to another agent or escalated to a supervisor. Rather than putting the customer on hold and explaining the call, the new agent can quickly read an auto-generated summary." Supports Genesys Cloud Audiohook integration.

### AWS — Live Call Analytics with Salesforce Integration

**URL:** https://aws.amazon.com/blogs/machine-learning/boost-agent-productivity-with-salesforce-integration-for-live-call-analytics/
**What it confirms:** Architecture for pushing AI-generated call summaries directly into Salesforce case records. Includes start-of-call Lambda hook (for customer lookup) and post-call summary Lambda hook (for CRM update). Directly relevant to your Salesforce + Genesys stack.

### AWS — LCA GitHub Repository (Open Source Reference)

**URL:** https://github.com/aws-samples/amazon-transcribe-live-call-analytics
**What it confirms:** Complete open-source reference architecture. End-of-call transcript summary using Amazon Bedrock (with Claude). Real-time transcription with PII redaction. Genesys Cloud Audiohook integration supported natively. Configurable summary prompts stored in DynamoDB.

---

## 4. McKinsey & Company (Industry Research)

### McKinsey — "The Contact Center Crossroads" (March 2025)

**URL:** https://www.mckinsey.com/capabilities/operations/our-insights/the-contact-center-crossroads-finding-the-right-mix-of-humans-and-ai
**What it confirms:** McKinsey's 2025 analysis of AI in contact centers. Agents are seeing positive effects of gen AI especially from **reduced After Call Work (ACW)**. AI tools summarize issues and proposed interventions, increasing agent productivity and reducing call times. Also covers the broader trend: digital interactions growing 6% annually since 2010, human-to-human interactions still growing 2% annually.

### McKinsey — "The Economic Potential of Generative AI"

**URL:** https://www.mckinsey.com/capabilities/tech-and-ai/our-insights/the-economic-potential-of-generative-ai-the-next-productivity-frontier
**What it confirms:** McKinsey's foundational gen AI research. At one company with 5,000 customer service agents, generative AI increased issue resolution by **14% per hour** and reduced handling time by **9%**. Also reduced agent attrition and escalation requests by **25%**. Crucially, productivity improvements were greatest among less-experienced agents. McKinsey estimates generative AI could increase customer care productivity at a value of **30–45% of current function costs**.

### McKinsey — "From Promising to Productive" (August 2024)

**URL:** https://www.mckinsey.com/capabilities/operations/our-insights/from-promising-to-productive-real-results-from-gen-ai-in-services
**What it confirms:** McKinsey's analysis of companies moving from AI pilots to scale. Only 3% of organizations had scaled gen AI in operations as of early 2024 — but those that did attributed more than 10% of EBIT to gen AI. Includes a case study of a European telecom deploying a gen-AI copilot for customer service agents with faster knowledge retrieval. Discusses the importance of prioritizing use cases for long-term value.

---

## 5. Academic / Production Research

### Incremental Summarization for Customer Support (October 2025)

**URL:** https://arxiv.org/abs/2510.06677
**What it confirms:** Peer-reviewed production study comparing incremental (real-time) summarization vs. bulk post-call summarization. Deployed in a real contact center. Incremental approach achieved **3% reduction in case handling time** (up to **9% for complex cases**) with agent satisfaction scores over **80%**. Writing summary notes consumes roughly **10% of case handling duration**. Validates both that summarization delivers measurable value and that the architecture choice matters.

### Recursive Summarization for Long-Term Dialogue Memory

**URL:** https://arxiv.org/abs/2308.15022
**What it confirms:** Academic research on the "rolling compaction" summarization approach — where an LLM recursively updates a summary as conversation progresses. Demonstrates the method works for maintaining context across long conversations and multiple sessions. Published in peer-reviewed venue with experiments on multiple LLMs.

---

## 6. Additional Vendor Validation

### Observe.AI — Summarization AI Product

**URL:** https://www.observe.ai/blog/summarization-ai
**What it confirms:** Observe.AI reports the **average wrap-up time is 6 minutes per interaction**. Their contact-center-specific LLM (trained on 2B interactions) powers customizable summarization. Customer quote from Accolade (healthcare): "We are able to create high-quality after call summaries using generative AI that are consistent and actionable." Summaries pushed directly into CRM via integrations, "fully eliminating ACW."

### ASAPP — Call Summarization Case Study

**URL:** https://www.asapp.com/blog/a-contact-center-case-study-about-call-summarization-strategies
**What it confirms:** Contact center case study validating that taking notes during the call does not improve agent efficiency and may harm customer experience. Automating conversation summaries reduces or completely eliminates dispositioning time. Their approach: make automated summaries visible in the agent desktop for review and edit, then (as confidence grows) remove manual review entirely.

### Talkdesk — Copilot Summarization Documentation

**URL:** https://support.talkdesk.com/hc/en-us/articles/16761287647259-Copilot-Automatic-Summarization-Agent-Next-Steps-and-Disposition
**What it confirms:** Talkdesk Copilot provides automatic summary, next steps, and disposition recommendation when agent enters wrap-up stage. Generated via a "Generate with AI" button. Summary, recommended disposition, and next steps all presented in a single panel. Confirms the industry-standard ACW panel pattern.

---

## Summary of Quantified Business Impact

| Source | Metric | Result |
|--------|--------|--------|
| Genesys (Demo Page) | After-call work reduction | 2 minutes per interaction |
| Genesys (Demo Page) | Average handle time reduction | 5 minutes per interaction |
| Genesys (Eir Case Study) | Time saved per voice call | Up to 1 minute |
| Genesys (Eir Case Study) | Customer effort score improvement | 63% |
| Five9 (Product Page) | Agent time savings | Up to 40% |
| Five9 (TruConnect Case Study) | AHT reduction | 30 seconds per call |
| Five9 (TruConnect Case Study) | Year 1 cost savings | 7.5% |
| Five9 (TruConnect Case Study) | Year 2 projected cost savings | 20% |
| Five9 (Forrester TEI) | Total business value | $14.5M / 212% ROI |
| Five9 (Forrester Study) | Time saved per live agent contact | 120 seconds |
| McKinsey | Issue resolution increase | 14% per hour |
| McKinsey | Handling time reduction | 9% |
| McKinsey | Agent attrition/escalation reduction | 25% |
| McKinsey | Customer care productivity gain | 30–45% of function costs |
| Observe.AI | Average wrap-up time (baseline) | 6 minutes per interaction |
| Academic (arXiv) | Handling time reduction (incremental) | 3–9% |

---

## Key Takeaways for Management

Every major contact center platform vendor (Genesys, Five9, Talkdesk, NICE, Observe.AI) and every major cloud provider (AWS, Google, Microsoft) has invested in AI call summarization as a primary feature. McKinsey identifies customer service as the single largest opportunity area for generative AI productivity gains. The two highest-value use cases — consistently validated across all sources — are:

1. **After-call work summarization** — Eliminating manual note-taking and disposition coding, saving 30 seconds to 6 minutes per interaction depending on baseline maturity.

2. **Transfer/escalation context summaries** — Generating a summary of the conversation so far when a call is transferred, so the receiving agent has full context without the customer repeating themselves.

Both use cases are natively supported by Genesys Agent Copilot and can be embedded directly into Salesforce Service Cloud via the existing CX Cloud integration.
