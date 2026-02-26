import { useState, useEffect, useRef, useCallback } from "react";

/* ═══════════════════════════════════════════════════════════════════
   Agent Desktop — After-Call Work (ACW) Summary Panel
   Full-featured post-interaction wrap-up with AI-generated insights,
   editable fields, CRM auto-fill, disposition codes, and agent QA.
   
   Based on Genesys Agent Copilot, Five9 AI Summaries, Talkdesk Copilot,
   and Salesforce Service Cloud ACW patterns.
   
   Palette: Primary Red #C8102E · Charcoal #333 · White/Gray body
   ═══════════════════════════════════════════════════════════════════ */

// ── Design Tokens ────────────────────────────────────────────────
const C = {
  red: "#C8102E", redD: "#A00C23", redL: "#FBEAED", redLt: "#FDF2F4",
  hdr: "#333333", hdrAlt: "#292929", dk: "#2C2C2C",
  tx: "#1A1A1A", tx2: "#555555", tx3: "#888888", tx4: "#AAAAAA",
  wh: "#FFFFFF", off: "#FAFAFA", bg: "#F5F5F5", bgWarm: "#F9F8F6",
  bd: "#D9D9D9", bdL: "#EBEBEB", bdFocus: "#999999",
  grn: "#0D7C3F", grnBg: "#E6F4EC", grnLt: "#F0FAF4",
  amb: "#A65D00", ambBg: "#FFF4DC", ambLt: "#FFF9ED",
  blu: "#1B6EC2", bluBg: "#E8F1FB", bluLt: "#F2F7FC",
  ft: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  mo: "'SF Mono', Consolas, Menlo, monospace",
  r: 6, rLg: 10, sh: "0 1px 3px rgba(0,0,0,.08)", shMd: "0 2px 8px rgba(0,0,0,.1)",
  shLg: "0 4px 16px rgba(0,0,0,.12)",
};

// ── Mock Data (Simulating AI Output from Genesys Copilot) ────────
const CALL_META = {
  id: "INT-2026-4829",
  customer: "Marcus Johnson",
  company: "Johnson Industrial Supply",
  account: "ACCT-88421",
  tier: "Gold",
  channel: "Voice",
  duration: "4:32",
  queue: "Industrial MRO — Shipping",
  agent: "Sarah Mitchell",
  startTime: "2:14 PM",
  endTime: "2:18 PM",
  date: "Feb 17, 2026",
};

const AI_SUMMARY = {
  headline: "Shipping delay resolved — Order #4829-A expedited at no charge",
  contactReason: "Customer reported order #4829-A had not shipped after 5 days despite selecting 2-day shipping at checkout.",
  keyDetails: [
    "Order #4829-A placed Jan 28 — 50x Item #2KL41 (Nitrile Gloves, L)",
    "Root cause: fulfillment center backlog at DFW distribution center",
    "Customer expressed frustration about missed deadline for warehouse restock",
  ],
  actionsTaken: [
    { text: "Verified order and identified fulfillment delay", done: true },
    { text: "Applied complimentary expedited shipping upgrade", done: true },
    { text: "New tracking number generated — emailed within 1 hour", done: true },
    { text: "Confirmed expected delivery: Thursday, Feb 20", done: true },
  ],
  resolution: "Expedited reshipping confirmed. Customer satisfied with resolution. No credit issued — shipping upgrade absorbed cost.",
  nextSteps: [
    { text: "Verify tracking email sent within 1 hour", assignee: "System", due: "Today" },
    { text: "Follow-up if delivery not confirmed by Feb 21", assignee: "Agent", due: "Feb 21" },
  ],
  sentiment: { overall: "negative → positive", start: "negative", end: "positive", score: 78 },
};

const WRAP_NOTES_DRAFT = `Order #4829-A (50x Nitrile Gloves #2KL41) reshipped via expedited from DFW center. Fulfillment backlog caused 5-day delay on 2-day shipping selection. Tracking update to be emailed within 1 hour. Expected delivery Thu Feb 20. No credit issued — customer accepted complimentary shipping upgrade. Customer satisfied.`;

const DISPOSITION_SUGGESTIONS = [
  { code: "SHIP-DELAY-RESOLVED", label: "Shipping Delay — Resolved", confidence: 96 },
  { code: "SHIP-EXPEDITE", label: "Shipping — Expedited Override", confidence: 82 },
  { code: "ORDER-ISSUE-RESOLVED", label: "Order Issue — Resolved", confidence: 71 },
];

const CRM_FIELDS = [
  { field: "Case Subject", value: "Shipping Delay — Order #4829-A", source: "AI", editable: true },
  { field: "Case Type", value: "Shipping Issue", source: "AI", editable: true },
  { field: "Case Status", value: "Resolved", source: "AI", editable: true },
  { field: "Priority", value: "High", source: "AI", editable: true },
  { field: "Root Cause", value: "Fulfillment Center Backlog", source: "AI", editable: true },
  { field: "Resolution Action", value: "Expedited Shipping Override", source: "AI", editable: true },
  { field: "Product SKU", value: "#2KL41 — Nitrile Gloves (L)", source: "Transcript", editable: false },
  { field: "Order Number", value: "#4829-A", source: "Transcript", editable: false },
  { field: "Follow-Up Required", value: "Yes — Feb 21", source: "AI", editable: true },
  { field: "Customer Satisfaction", value: "Satisfied", source: "AI", editable: true },
];

const CHECKLIST = [
  { id: 1, label: "Verified customer identity", done: true, auto: true },
  { id: 2, label: "Confirmed order number", done: true, auto: true },
  { id: 3, label: "Identified root cause", done: true, auto: true },
  { id: 4, label: "Explained resolution clearly", done: true, auto: true },
  { id: 5, label: "Offered compensation if applicable", done: true, auto: false },
  { id: 6, label: "Confirmed next steps & timeline", done: true, auto: true },
  { id: 7, label: "Asked if anything else needed", done: false, auto: false },
];

// ── Utility Components ───────────────────────────────────────────
const Pill = ({ children, bg, fg, sx }) => (
  <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: bg, color: fg, letterSpacing: ".04em", whiteSpace: "nowrap", ...sx }}>{children}</span>
);

const Lbl = ({ children, sx }) => (
  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".07em", textTransform: "uppercase", color: C.tx3, marginBottom: 6, ...sx }}>{children}</div>
);

const SectionCard = ({ children, sx }) => (
  <div style={{ background: C.wh, border: `1px solid ${C.bdL}`, borderRadius: C.r, padding: 14, ...sx }}>{children}</div>
);

const ConfBar = ({ pct }) => (
  <div style={{ width: 48, height: 4, borderRadius: 2, background: C.bdL, overflow: "hidden", flexShrink: 0 }}>
    <div style={{ width: `${pct}%`, height: "100%", borderRadius: 2, background: pct > 85 ? C.grn : pct > 70 ? C.amb : C.tx3 }} />
  </div>
);

const SentimentDot = ({ value, sz = 10 }) => {
  const color = { positive: C.grn, negative: C.red, neutral: C.amb }[value] || C.tx3;
  return <span style={{ display: "inline-block", width: sz, height: sz, borderRadius: "50%", background: color, flexShrink: 0 }} />;
};

const SentimentArc = ({ start, end, score }) => {
  const startC = { positive: C.grn, negative: C.red, neutral: C.amb }[start];
  const endC = { positive: C.grn, negative: C.red, neutral: C.amb }[end];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: `linear-gradient(90deg, ${start === "negative" ? C.redL : C.ambBg} 0%, ${C.grnBg} 100%)`, borderRadius: C.r }}>
      <SentimentDot value={start} />
      <div style={{ flex: 1, height: 3, borderRadius: 2, background: `linear-gradient(90deg, ${startC}, ${endC})` }} />
      <SentimentDot value={end} />
      <div style={{ fontSize: 11, fontWeight: 600, color: C.tx }}>
        CSAT Prediction: <span style={{ color: endC }}>{score}/100</span>
      </div>
    </div>
  );
};

// ── ACW Header Bar ───────────────────────────────────────────────
const ACWHeader = ({ elapsed, onSave, saving, saved }) => (
  <div style={{ background: C.hdr, color: C.wh, padding: "12px 20px", display: "flex", alignItems: "center", gap: 12, borderRadius: `${C.rLg}px ${C.rLg}px 0 0` }}>
    <div style={{ width: 32, height: 32, borderRadius: "50%", background: C.red, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0 }}>📋</div>
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: ".01em" }}>After-Call Work</div>
      <div style={{ fontSize: 11, color: C.tx4, marginTop: 1 }}>
        {CALL_META.customer} · {CALL_META.company} · {CALL_META.duration} call
      </div>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ textAlign: "right", marginRight: 8 }}>
        <div style={{ fontSize: 10, color: C.tx4, letterSpacing: ".05em" }}>ACW TIMER</div>
        <div style={{ fontSize: 16, fontWeight: 700, fontFamily: C.mo, color: elapsed > 60 ? C.red : elapsed > 30 ? C.amb : C.grn }}>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</div>
      </div>
      <button
        onClick={onSave}
        disabled={saving || saved}
        style={{
          padding: "8px 18px", borderRadius: C.r, border: "none", fontFamily: C.ft,
          fontWeight: 700, fontSize: 12, cursor: saving || saved ? "default" : "pointer",
          background: saved ? C.grn : C.red, color: C.wh, letterSpacing: ".02em",
          opacity: saving ? 0.7 : 1, transition: "all .2s ease",
        }}
      >
        {saved ? "✓ Saved to Salesforce" : saving ? "Saving…" : "Save & Complete"}
      </button>
    </div>
  </div>
);

// ── AI Summary Section ───────────────────────────────────────────
const SummarySection = ({ expanded, onToggle }) => (
  <SectionCard>
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: expanded ? 14 : 0, cursor: "pointer" }} onClick={onToggle}>
      <div style={{ fontSize: 14 }}>🤖</div>
      <div style={{ flex: 1 }}>
        <Lbl sx={{ marginBottom: 0 }}>AI-Generated Summary</Lbl>
      </div>
      <Pill bg={C.grnBg} fg={C.grn}>AUTO-GENERATED</Pill>
      <span style={{ fontSize: 11, color: C.tx3, cursor: "pointer", userSelect: "none" }}>{expanded ? "▲" : "▼"}</span>
    </div>
    {expanded && (
      <div style={{ fontSize: 12, lineHeight: 1.7, color: C.tx }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: C.dk, marginBottom: 10, padding: "8px 12px", background: C.bg, borderRadius: C.r, borderLeft: `3px solid ${C.red}` }}>
          {AI_SUMMARY.headline}
        </div>

        <div style={{ fontWeight: 600, color: C.tx, marginBottom: 4 }}>Contact Reason</div>
        <div style={{ color: C.tx2, marginBottom: 12 }}>{AI_SUMMARY.contactReason}</div>

        <div style={{ fontWeight: 600, color: C.tx, marginBottom: 4 }}>Key Details</div>
        <div style={{ marginBottom: 12, padding: "8px 12px", background: C.off, borderRadius: C.r }}>
          {AI_SUMMARY.keyDetails.map((d, i) => (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: i < AI_SUMMARY.keyDetails.length - 1 ? 4 : 0, color: C.tx2 }}>
              <span style={{ color: C.tx3, flexShrink: 0 }}>•</span>{d}
            </div>
          ))}
        </div>

        <div style={{ fontWeight: 600, color: C.tx, marginBottom: 4 }}>Actions Taken</div>
        <div style={{ marginBottom: 12 }}>
          {AI_SUMMARY.actionsTaken.map((a, i) => (
            <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 4, color: C.tx2 }}>
              <span style={{ color: a.done ? C.grn : C.tx3, flexShrink: 0, fontSize: 13, lineHeight: "20px" }}>{a.done ? "✓" : "○"}</span>
              <span>{a.text}</span>
            </div>
          ))}
        </div>

        <div style={{ fontWeight: 600, color: C.tx, marginBottom: 4 }}>Resolution</div>
        <div style={{ color: C.tx2, marginBottom: 12, padding: "8px 12px", background: C.grnLt, borderRadius: C.r, borderLeft: `3px solid ${C.grn}` }}>
          {AI_SUMMARY.resolution}
        </div>

        <div style={{ fontWeight: 600, color: C.tx, marginBottom: 6 }}>Sentiment Trend</div>
        <SentimentArc start={AI_SUMMARY.sentiment.start} end={AI_SUMMARY.sentiment.end} score={AI_SUMMARY.sentiment.score} />
      </div>
    )}
  </SectionCard>
);

// ── Editable Wrap-Up Notes ───────────────────────────────────────
const WrapNotes = ({ notes, setNotes, locked }) => {
  const ref = useRef(null);
  return (
    <SectionCard>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{ fontSize: 14 }}>📝</div>
        <Lbl sx={{ marginBottom: 0, flex: 1 }}>Wrap-Up Notes</Lbl>
        <Pill bg={C.bluBg} fg={C.blu}>EDITABLE</Pill>
      </div>
      <div style={{ position: "relative" }}>
        <textarea
          ref={ref}
          value={notes}
          onChange={e => setNotes(e.target.value)}
          disabled={locked}
          style={{
            width: "100%", minHeight: 88, padding: 12, border: `1px solid ${C.bdL}`,
            borderRadius: C.r, fontFamily: C.ft, fontSize: 12, lineHeight: 1.65,
            color: C.tx, background: locked ? C.bg : C.wh, resize: "vertical",
            outline: "none", boxSizing: "border-box", transition: "border-color .15s",
          }}
          onFocus={e => (e.target.style.borderColor = C.bdFocus)}
          onBlur={e => (e.target.style.borderColor = C.bdL)}
        />
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 10, color: C.tx3 }}>
          <span>AI-drafted • Review and edit before saving</span>
          <span>{notes.length} chars</span>
        </div>
      </div>
    </SectionCard>
  );
};

// ── Disposition / Wrap-Up Code Picker ────────────────────────────
const DispositionPicker = ({ selected, onSelect }) => (
  <SectionCard>
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <div style={{ fontSize: 14 }}>🏷️</div>
      <Lbl sx={{ marginBottom: 0, flex: 1 }}>Disposition Code</Lbl>
      <Pill bg={C.ambBg} fg={C.amb}>AI-SUGGESTED</Pill>
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {DISPOSITION_SUGGESTIONS.map((d, i) => {
        const active = selected === d.code;
        return (
          <div
            key={d.code}
            onClick={() => onSelect(d.code)}
            style={{
              display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
              borderRadius: C.r, cursor: "pointer", transition: "all .15s",
              background: active ? C.redL : C.off,
              border: `1.5px solid ${active ? C.red : "transparent"}`,
            }}
          >
            <div style={{
              width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
              border: `2px solid ${active ? C.red : C.bd}`,
              background: active ? C.red : "transparent",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all .15s",
            }}>
              {active && <span style={{ color: C.wh, fontSize: 10 }}>✓</span>}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: active ? 700 : 500, color: C.tx }}>{d.label}</div>
              <div style={{ fontSize: 10, color: C.tx3 }}>{d.code}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <ConfBar pct={d.confidence} />
              <span style={{ fontSize: 10, fontWeight: 600, color: d.confidence > 85 ? C.grn : C.tx3, minWidth: 28 }}>{d.confidence}%</span>
            </div>
          </div>
        );
      })}
    </div>
  </SectionCard>
);

// ── Next Steps / Follow-Up Actions ───────────────────────────────
const NextSteps = () => {
  const [checks, setChecks] = useState(AI_SUMMARY.nextSteps.map(() => false));
  return (
    <SectionCard>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{ fontSize: 14 }}>📌</div>
        <Lbl sx={{ marginBottom: 0, flex: 1 }}>Follow-Up Actions</Lbl>
      </div>
      {AI_SUMMARY.nextSteps.map((s, i) => (
        <div
          key={i}
          onClick={() => setChecks(p => p.map((v, j) => j === i ? !v : v))}
          style={{
            display: "flex", gap: 10, alignItems: "flex-start", padding: "8px 10px",
            borderRadius: C.r, cursor: "pointer", marginBottom: 4,
            background: checks[i] ? C.grnLt : "transparent", transition: "background .15s",
          }}
        >
          <div style={{
            width: 16, height: 16, borderRadius: 3, flexShrink: 0, marginTop: 1,
            border: `1.5px solid ${checks[i] ? C.grn : C.bd}`,
            background: checks[i] ? C.grn : C.wh,
            display: "flex", alignItems: "center", justifyContent: "center",
            transition: "all .15s",
          }}>
            {checks[i] && <span style={{ color: C.wh, fontSize: 9, fontWeight: 700 }}>✓</span>}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: checks[i] ? C.tx3 : C.tx, textDecoration: checks[i] ? "line-through" : "none" }}>{s.text}</div>
            <div style={{ fontSize: 10, color: C.tx3, marginTop: 2 }}>
              <span style={{ fontWeight: 600 }}>{s.assignee}</span> · Due: {s.due}
            </div>
          </div>
        </div>
      ))}
    </SectionCard>
  );
};

// ── CRM Auto-Fill Preview ────────────────────────────────────────
const CRMPreview = ({ expanded, onToggle, fields, onFieldEdit }) => (
  <SectionCard>
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: expanded ? 10 : 0, cursor: "pointer" }} onClick={onToggle}>
      <div style={{ fontSize: 14 }}>☁️</div>
      <Lbl sx={{ marginBottom: 0, flex: 1 }}>Salesforce Case Fields</Lbl>
      <Pill bg={C.bluBg} fg={C.blu}>{fields.length} FIELDS</Pill>
      <span style={{ fontSize: 11, color: C.tx3, userSelect: "none" }}>{expanded ? "▲" : "▼"}</span>
    </div>
    {expanded && (
      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {fields.map((f, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
            background: i % 2 === 0 ? C.off : C.wh, borderRadius: 3,
          }}>
            <div style={{ width: 130, fontSize: 11, fontWeight: 600, color: C.tx3, flexShrink: 0 }}>{f.field}</div>
            <div style={{ flex: 1, fontSize: 12, color: C.tx, fontWeight: 500 }}>{f.value}</div>
            <Pill bg={f.source === "AI" ? C.grnBg : C.bluBg} fg={f.source === "AI" ? C.grn : C.blu} sx={{ fontSize: 8 }}>
              {f.source}
            </Pill>
            {f.editable && (
              <span style={{ fontSize: 10, color: C.tx4, cursor: "pointer" }} title="Edit field">✎</span>
            )}
          </div>
        ))}
        <div style={{ marginTop: 8, fontSize: 10, color: C.tx3, display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: C.grn }}>●</span> AI-extracted fields will auto-populate Salesforce Case on save
        </div>
      </div>
    )}
  </SectionCard>
);

// ── Compliance Checklist ─────────────────────────────────────────
const ComplianceChecklist = ({ items, onToggle }) => {
  const done = items.filter(i => i.done).length;
  const total = items.length;
  const pct = Math.round((done / total) * 100);
  return (
    <SectionCard>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{ fontSize: 14 }}>✅</div>
        <Lbl sx={{ marginBottom: 0, flex: 1 }}>Call Quality Checklist</Lbl>
        <span style={{ fontSize: 11, fontWeight: 700, color: pct === 100 ? C.grn : C.amb }}>{done}/{total}</span>
      </div>
      <div style={{ height: 3, background: C.bdL, borderRadius: 2, marginBottom: 10, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: pct === 100 ? C.grn : C.amb, borderRadius: 2, transition: "width .3s ease" }} />
      </div>
      {items.map(item => (
        <div
          key={item.id}
          onClick={() => onToggle(item.id)}
          style={{
            display: "flex", alignItems: "center", gap: 8, padding: "5px 8px",
            borderRadius: 3, cursor: "pointer", marginBottom: 2,
            fontSize: 12, color: item.done ? C.tx3 : C.tx,
          }}
        >
          <span style={{ color: item.done ? C.grn : C.bd, fontSize: 14, flexShrink: 0 }}>
            {item.done ? "☑" : "☐"}
          </span>
          <span style={{ textDecoration: item.done ? "line-through" : "none", flex: 1 }}>{item.label}</span>
          {item.auto && item.done && (
            <span style={{ fontSize: 9, color: C.tx4, fontStyle: "italic" }}>auto-detected</span>
          )}
        </div>
      ))}
    </SectionCard>
  );
};

// ── Agent Feedback / Rating ──────────────────────────────────────
const AgentFeedback = ({ rating, setRating }) => (
  <SectionCard sx={{ background: C.bgWarm }}>
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
      <div style={{ fontSize: 14 }}>💬</div>
      <Lbl sx={{ marginBottom: 0, flex: 1 }}>Rate AI Summary Quality</Lbl>
    </div>
    <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
      {[
        { val: "up", icon: "👍", label: "Accurate" },
        { val: "down", icon: "👎", label: "Needs Work" },
      ].map(opt => (
        <button
          key={opt.val}
          onClick={() => setRating(rating === opt.val ? null : opt.val)}
          style={{
            flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
            gap: 6, padding: "8px 12px", borderRadius: C.r, fontSize: 12, fontWeight: 600,
            fontFamily: C.ft, cursor: "pointer", transition: "all .15s",
            background: rating === opt.val ? (opt.val === "up" ? C.grnBg : C.redL) : C.wh,
            border: `1.5px solid ${rating === opt.val ? (opt.val === "up" ? C.grn : C.red) : C.bdL}`,
            color: rating === opt.val ? (opt.val === "up" ? C.grn : C.red) : C.tx2,
          }}
        >
          <span style={{ fontSize: 16 }}>{opt.icon}</span>
          {opt.label}
        </button>
      ))}
    </div>
    <div style={{ fontSize: 10, color: C.tx3, textAlign: "center" }}>
      Your feedback trains Genesys Copilot to generate better summaries
    </div>
  </SectionCard>
);

// ── Call Metadata Bar ────────────────────────────────────────────
const MetaBar = () => (
  <div style={{
    display: "flex", flexWrap: "wrap", gap: 6, padding: "10px 14px",
    background: C.off, borderRadius: C.r, fontSize: 11, color: C.tx2,
  }}>
    {[
      ["Interaction", CALL_META.id],
      ["Date", CALL_META.date],
      ["Time", `${CALL_META.startTime} – ${CALL_META.endTime}`],
      ["Duration", CALL_META.duration],
      ["Channel", CALL_META.channel],
      ["Queue", CALL_META.queue],
      ["Account", `${CALL_META.account} (${CALL_META.tier})`],
    ].map(([k, v]) => (
      <span key={k} style={{ display: "flex", gap: 4 }}>
        <span style={{ fontWeight: 600, color: C.tx3 }}>{k}:</span>
        <span style={{ color: C.tx }}>{v}</span>
        <span style={{ color: C.bdL, margin: "0 2px" }}>|</span>
      </span>
    ))}
  </div>
);

// ── ACW Time Saved Banner ────────────────────────────────────────
const TimeSavedBanner = ({ saved }) => (
  saved ? (
    <div style={{
      padding: "12px 16px", background: C.grnLt, borderRadius: C.r,
      display: "flex", alignItems: "center", gap: 10, border: `1px solid ${C.grn}22`,
    }}>
      <div style={{ fontSize: 20 }}>⚡</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: C.grn }}>Call Complete — Wrap-up saved to Salesforce</div>
        <div style={{ fontSize: 11, color: C.tx2, marginTop: 2 }}>AI summary, disposition, case fields, and follow-up actions synced. Estimated ACW time saved: ~45 seconds.</div>
      </div>
    </div>
  ) : null
);

// ═══════════════════════════════════════════════════════════════════
// MAIN COMPONENT — Full ACW Panel
// ═══════════════════════════════════════════════════════════════════
export default function ACWSummaryPanel() {
  const [elapsed, setElapsed] = useState(0);
  const [notes, setNotes] = useState(WRAP_NOTES_DRAFT);
  const [disposition, setDisposition] = useState(DISPOSITION_SUGGESTIONS[0].code);
  const [summaryOpen, setSummaryOpen] = useState(true);
  const [crmOpen, setCrmOpen] = useState(false);
  const [checklist, setChecklist] = useState(CHECKLIST);
  const [rating, setRating] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [activeTab, setActiveTab] = useState("summary");

  // ACW timer
  useEffect(() => {
    if (saved) return;
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, [saved]);

  const handleSave = useCallback(() => {
    setSaving(true);
    setTimeout(() => { setSaving(false); setSaved(true); }, 1200);
  }, []);

  const toggleCheck = useCallback((id) => {
    setChecklist(prev => prev.map(i => i.id === id ? { ...i, done: !i.done } : i));
  }, []);

  const tabs = [
    { id: "summary", label: "Summary & Notes", icon: "📋" },
    { id: "crm", label: "CRM Fields", icon: "☁️" },
    { id: "quality", label: "Quality", icon: "✅" },
  ];

  return (
    <div style={{
      fontFamily: C.ft, maxWidth: 680, margin: "0 auto",
      background: C.bg, borderRadius: C.rLg, overflow: "hidden",
      boxShadow: C.shLg, color: C.tx,
    }}>
      {/* Header */}
      <ACWHeader elapsed={elapsed} onSave={handleSave} saving={saving} saved={saved} />

      {/* Meta bar */}
      <div style={{ padding: "12px 16px 0" }}>
        <MetaBar />
      </div>

      {/* Tab navigation */}
      <div style={{ display: "flex", gap: 2, padding: "12px 16px 0" }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              flex: 1, padding: "8px 12px", borderRadius: `${C.r}px ${C.r}px 0 0`,
              border: "none", fontFamily: C.ft, fontSize: 12, fontWeight: 600,
              cursor: "pointer", transition: "all .15s",
              background: activeTab === tab.id ? C.wh : "transparent",
              color: activeTab === tab.id ? C.red : C.tx3,
              borderBottom: activeTab === tab.id ? `2px solid ${C.red}` : `2px solid transparent`,
            }}
          >
            <span style={{ marginRight: 4 }}>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12, minHeight: 400 }}>
        {/* Saved banner */}
        <TimeSavedBanner saved={saved} />

        {activeTab === "summary" && (
          <>
            <SummarySection expanded={summaryOpen} onToggle={() => setSummaryOpen(o => !o)} />
            <WrapNotes notes={notes} setNotes={setNotes} locked={saved} />
            <DispositionPicker selected={disposition} onSelect={setDisposition} />
            <NextSteps />
            <AgentFeedback rating={rating} setRating={setRating} />
          </>
        )}

        {activeTab === "crm" && (
          <>
            <CRMPreview expanded={true} onToggle={() => {}} fields={CRM_FIELDS} />
            <SectionCard>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <div style={{ fontSize: 14 }}>🔗</div>
                <Lbl sx={{ marginBottom: 0, flex: 1 }}>Integration Status</Lbl>
              </div>
              <div style={{ fontSize: 12, color: C.tx2, lineHeight: 1.7 }}>
                {saved ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ color: C.grn }}>✓</span> Case fields synced to Salesforce</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ color: C.grn }}>✓</span> Disposition code applied</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ color: C.grn }}>✓</span> Call transcript attached to case</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ color: C.grn }}>✓</span> Follow-up task created in Salesforce</div>
                  </div>
                ) : (
                  <div>
                    On save, the following will be synced to Salesforce Service Cloud:
                    case fields (auto-filled from transcript), disposition code, wrap-up notes,
                    call transcript attachment, and any follow-up tasks.
                  </div>
                )}
              </div>
            </SectionCard>
          </>
        )}

        {activeTab === "quality" && (
          <>
            <ComplianceChecklist items={checklist} onToggle={toggleCheck} />
            <SectionCard>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <div style={{ fontSize: 14 }}>📊</div>
                <Lbl sx={{ marginBottom: 0, flex: 1 }}>Interaction Metrics</Lbl>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {[
                  ["Handle Time", "4:32", C.grn],
                  ["Hold Time", "0:00", C.grn],
                  ["Transfers", "0", C.grn],
                  ["Sentiment Score", "78/100", C.grn],
                  ["First Contact Resolution", "Yes", C.grn],
                  ["Compliance Score", `${checklist.filter(c => c.done).length}/${checklist.length}`, checklist.every(c => c.done) ? C.grn : C.amb],
                ].map(([label, value, color]) => (
                  <div key={label} style={{ padding: "8px 10px", background: C.off, borderRadius: C.r }}>
                    <div style={{ fontSize: 10, color: C.tx3, fontWeight: 600, marginBottom: 2 }}>{label}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color }}>{value}</div>
                  </div>
                ))}
              </div>
            </SectionCard>
            <AgentFeedback rating={rating} setRating={setRating} />
          </>
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: "10px 16px", background: C.off, borderTop: `1px solid ${C.bdL}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        fontSize: 10, color: C.tx3,
      }}>
        <span>Powered by Genesys Agent Copilot + Salesforce Service Cloud</span>
        <span>Agent: {CALL_META.agent}</span>
      </div>
    </div>
  );
}
