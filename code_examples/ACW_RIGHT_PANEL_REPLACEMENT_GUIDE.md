# ACW Right-Panel Replacement — Implementation Guide

> **Updated 2026-02-20:** Revised Step 6 (page.tsx) to reflect the word-by-word streaming refactor
> (`useTranscriptStream` hook, `onWordInterim`/`onWordFinal` callbacks). The original guide used the
> pre-streaming batch pattern (`handleTranscriptBatch`, `onTranscriptBatch`, `useState<TranscriptLine[]>`),
> which would revert the streaming work if followed literally. Also updated prerequisites, file summary,
> and demo data constants to match `Option2_data_file_v2.txt`.

## Overview

This guide implements a **call-phase-driven layout transition** from a 2-panel active-call view to a 3-panel layout where the right column swaps between active-call content and an After-Call Work (ACW) panel. No overlays, no drawers, no z-index headaches — just a clean conditional render driven by call phase state.

### State Transitions

```
ACTIVE CALL:
┌──────────────────┬─────────────────────────┬──────────────────────┐
│  LEFT (240px)    │  CENTER (flex-1)        │  RIGHT (340px)       │
│                  │                         │                      │
│  CallerInfoCard  │  TranscriptViewer       │  MCPSuggestionsBox   │
│  CallMetaCard    │  (unchanged)            │  SummaryViewer       │
│  InteractionHist │                         │  (rolling summary)   │
└──────────────────┴─────────────────────────┴──────────────────────┘

ACW PHASE:
┌──────────────────┬─────────────────────────┬──────────────────────┐
│  LEFT (240px)    │  CENTER (flex-1)        │  RIGHT (380-400px)   │
│  COMPACT         │                         │                      │
│  CallerInfoCard  │  TranscriptViewer       │  ACW Panel (3 tabs)  │
│  (only)          │  (unchanged)            │  - Summary & Notes   │
│                  │                         │  - CRM Fields        │
│                  │                         │  - Quality           │
└──────────────────┴─────────────────────────┴──────────────────────┘
```

---

## Critical Notes for the Implementing LLM

1. **Follow steps 1-7 in exact order.** Step 1 (types) must be done first because all subsequent components import from it. Steps 2-5 (new components) can be done in any order but must all exist before Step 6 (page.tsx rewrite) because page.tsx imports them all. Step 7 (build verification) is last.

2. **`'use client'` directive is NOT needed on new component files.** The existing codebase pattern is that only `page.tsx` has `'use client'` at the top. Child components that use React hooks (e.g., `SummaryViewer.tsx` uses `useState`/`useEffect`, `MCPSuggestionsBox.tsx` uses `useState`) do NOT have `'use client'` — they inherit client-side rendering from the parent. Follow this same pattern for all new components. Do NOT add `'use client'` to `CallerInfoCard.tsx`, `CallMetaCard.tsx`, `InteractionHistory.tsx`, or `ACWPanel.tsx`.

3. **All placeholder data is hardcoded at the module level in `page.tsx`** as `DEMO_CALLER`, `DEMO_CALL_META`, and `DEMO_HISTORY` constants. These are passed as props to child components. In production, they would be fetched from APIs. Each placeholder is marked with a `// PLACEHOLDER:` comment explaining what replaces it.

4. **The `maxWidth` on the panel container increases from `1400px` to `1600px`** to accommodate the 3-column layout. The header and footer `maxWidth` also update to match.

5. **All styles use inline style objects** (not CSS modules or Tailwind). This matches the existing codebase convention. Use the design tokens from `@/styles/grainger-tokens.ts` for all values.

---

## Prerequisites

Before starting, read and understand these existing files:

| File | Purpose |
|------|---------|
| `frontend/src/app/page.tsx` | Main layout — currently 2-panel `1fr 1fr` grid |
| `frontend/src/components/TranscriptViewer.tsx` | Center panel transcript |
| `frontend/src/components/SummaryViewer.tsx` | Right panel rolling summary |
| `frontend/src/components/MCPSuggestionsBox.tsx` | Right panel MCP placeholder |
| `frontend/src/components/ConnectionStatus.tsx` | Header connection status |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket with auto-reconnect |
| `frontend/src/hooks/useTranscriptStream.ts` | Word-by-word transcript stream hook |
| `frontend/src/types/conversation.ts` | API response types |
| `frontend/src/types/websocket.ts` | WebSocket event types |
| `frontend/src/styles/grainger-tokens.ts` | Design system tokens |
| `code_examples/acw-summary-panel.jsx` | Reference ACW panel (mock data, full UI) |

---

## Step 1: Add Call Phase Type Definition

**File:** `frontend/src/types/conversation.ts`

Add the `CallPhase` type and supporting interfaces at the end of the existing file. Do NOT modify existing types. The file currently ends with the `ApiError` interface. Note that the `TranscriptLine` interface already includes `line_id` and `is_final` fields from the word-streaming refactor. Append everything below after the `ApiError` interface.

```typescript
// --- Add below the existing `ApiError` interface ---

export type CallPhase = 'active' | 'acw';

export interface CallerInfo {
  customerName: string;
  company: string;
  accountNumber: string;
  tier: string;
}

export interface CallMeta {
  interactionId: string;
  channel: string;
  queue: string;
  startTime: string;
  duration: string;
  agent: string;
}

export interface InteractionHistoryItem {
  date: string;
  subject: string;
  channel: string;
  resolution: string;
}

export interface DispositionSuggestion {
  code: string;
  label: string;
  confidence: number;
}

export interface ComplianceCheckItem {
  id: number;
  label: string;
  done: boolean;
  auto: boolean;
}

export interface CRMField {
  field: string;
  value: string;
  source: 'AI' | 'Transcript';
  editable: boolean;
}

export interface ACWState {
  wrapUpNotes: string;
  selectedDisposition: string | null;
  checklist: ComplianceCheckItem[];
  agentRating: 'up' | 'down' | null;
  isSaving: boolean;
  isSaved: boolean;
  acwElapsedSeconds: number;
}
```

---

## Step 2: Create the CallerInfoCard Component

**File:** `frontend/src/components/CallerInfoCard.tsx` (NEW)

This component renders caller identification in the left panel. It appears in both call phases.

```typescript
/**
 * Caller Info Card — Left Panel
 *
 * Shows customer name, company, account, and tier.
 * Visible in both active-call and ACW phases.
 */

import { CallerInfo } from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/grainger-tokens';

interface CallerInfoCardProps {
  caller: CallerInfo;
}

export default function CallerInfoCard({ caller }: CallerInfoCardProps) {
  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.avatar}>
          {caller.customerName.charAt(0).toUpperCase()}
        </div>
        <div style={styles.nameBlock}>
          <div style={styles.customerName}>{caller.customerName}</div>
          <div style={styles.company}>{caller.company}</div>
        </div>
      </div>
      <div style={styles.details}>
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Account</span>
          <span style={styles.detailValue}>{caller.accountNumber}</span>
        </div>
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Tier</span>
          <span style={styles.tierBadge}>{caller.tier}</span>
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    boxShadow: shadows.base,
    padding: spacing.md,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  avatar: {
    width: '36px',
    height: '36px',
    borderRadius: borderRadius.full,
    backgroundColor: colors.primary,
    color: colors.surface,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.bold,
    flexShrink: 0,
  },
  nameBlock: {
    display: 'flex',
    flexDirection: 'column' as const,
    minWidth: 0,
  },
  customerName: {
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.bold,
    color: colors.text,
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  company: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  details: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.xs,
    borderTop: `1px solid ${colors.borderLight}`,
    paddingTop: spacing.sm,
  },
  detailRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  detailLabel: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    fontWeight: typography.fontWeight.medium,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  detailValue: {
    fontSize: typography.fontSize.sm,
    color: colors.text,
    fontFamily: typography.fontFamily.mono,
  },
  tierBadge: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.semibold,
    color: '#A65D00',
    backgroundColor: '#FFF4DC',
    padding: '2px 8px',
    borderRadius: borderRadius.sm,
  },
};
```

---

## Step 3: Create the CallMetaCard Component

**File:** `frontend/src/components/CallMetaCard.tsx` (NEW)

Displays call metadata. Only visible during the active call phase; hidden during ACW.

```typescript
/**
 * Call Meta Card — Left Panel (active call only)
 *
 * Shows interaction ID, channel, queue, start time, duration, agent name.
 * Hidden during ACW phase to compact the left panel.
 */

import { CallMeta } from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/grainger-tokens';

interface CallMetaCardProps {
  meta: CallMeta;
}

export default function CallMetaCard({ meta }: CallMetaCardProps) {
  const rows: [string, string][] = [
    ['Interaction', meta.interactionId],
    ['Channel', meta.channel],
    ['Queue', meta.queue],
    ['Start', meta.startTime],
    ['Duration', meta.duration],
    ['Agent', meta.agent],
  ];

  return (
    <div style={styles.container}>
      <h3 style={styles.title}>Call Details</h3>
      <div style={styles.rows}>
        {rows.map(([label, value]) => (
          <div key={label} style={styles.row}>
            <span style={styles.label}>{label}</span>
            <span style={styles.value}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    boxShadow: shadows.base,
    padding: spacing.md,
  },
  title: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.semibold,
    color: colors.text,
    margin: `0 0 ${spacing.sm} 0`,
  },
  rows: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '4px',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '3px 0',
  },
  label: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    fontWeight: typography.fontWeight.medium,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  value: {
    fontSize: typography.fontSize.sm,
    color: colors.text,
    fontWeight: typography.fontWeight.medium,
    textAlign: 'right' as const,
    maxWidth: '140px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
};
```

---

## Step 4: Create the InteractionHistory Component

**File:** `frontend/src/components/InteractionHistory.tsx` (NEW)

Shows past interactions for the customer. Only visible during active call phase.

```typescript
/**
 * Interaction History — Left Panel (active call only)
 *
 * Shows recent past interactions for the current customer.
 * Hidden during ACW to compact the left panel.
 */

import { useState } from 'react';
import { InteractionHistoryItem } from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/grainger-tokens';

interface InteractionHistoryProps {
  history: InteractionHistoryItem[];
}

export default function InteractionHistory({ history }: InteractionHistoryProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div style={styles.container}>
      <div
        style={styles.header}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <h3 style={styles.title}>
          History ({history.length})
        </h3>
        <span style={styles.expandIcon}>{isExpanded ? '▼' : '▶'}</span>
      </div>

      {isExpanded && (
        <div style={styles.list}>
          {history.length === 0 ? (
            <div style={styles.empty}>No previous interactions</div>
          ) : (
            history.map((item, idx) => (
              <div key={idx} style={styles.item}>
                <div style={styles.itemHeader}>
                  <span style={styles.itemDate}>{item.date}</span>
                  <span style={styles.itemChannel}>{item.channel}</span>
                </div>
                <div style={styles.itemSubject}>{item.subject}</div>
                <div style={styles.itemResolution}>{item.resolution}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    boxShadow: shadows.base,
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    cursor: 'pointer',
    userSelect: 'none' as const,
  },
  title: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.semibold,
    color: colors.text,
    margin: 0,
  },
  expandIcon: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
  },
  list: {
    padding: `0 ${spacing.md} ${spacing.md}`,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.sm,
  },
  empty: {
    fontSize: typography.fontSize.sm,
    color: colors.textLight,
    textAlign: 'center' as const,
    padding: spacing.md,
  },
  item: {
    padding: spacing.sm,
    backgroundColor: colors.background,
    borderRadius: borderRadius.sm,
    borderLeft: `3px solid ${colors.borderLight}`,
  },
  itemHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '4px',
  },
  itemDate: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    fontFamily: typography.fontFamily.mono,
  },
  itemChannel: {
    fontSize: '10px',
    fontWeight: typography.fontWeight.semibold,
    color: colors.info,
    backgroundColor: `${colors.info}15`,
    padding: '1px 6px',
    borderRadius: borderRadius.sm,
    textTransform: 'uppercase' as const,
  },
  itemSubject: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.medium,
    color: colors.text,
    marginBottom: '2px',
  },
  itemResolution: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
  },
};
```

---

## Step 5: Create the ACWPanel Component

**File:** `frontend/src/components/ACWPanel.tsx` (NEW)

This is the main ACW component that replaces the right panel content when the call phase transitions to `'acw'`. It has 3 tabs: Summary & Notes, CRM Fields, Quality.

Use `code_examples/acw-summary-panel.jsx` as your visual/behavioral reference. The key differences from the reference:

1. **Use the existing design tokens** from `@/styles/grainger-tokens.ts` instead of inline `C` constants
2. **Accept real data via props** instead of hardcoded mock data
3. **Use TypeScript** with the types from Step 1
4. **Consume the final summary and checklist state** from the active-call phase as inputs

```typescript
/**
 * ACW Panel — Right Panel (acw phase only)
 *
 * After-Call Work panel with 3 tabs:
 *   1. Summary & Notes — AI summary review, editable wrap-up notes, disposition picker
 *   2. CRM Fields — Auto-filled Salesforce fields preview
 *   3. Quality — Compliance checklist + interaction metrics
 *
 * Props receive the final summary text, checklist state, and caller/call metadata
 * from the active-call phase. This data is CONSUMED as input, not regenerated.
 *
 * REFERENCE: code_examples/acw-summary-panel.jsx for visual patterns.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Summary,
  CallerInfo,
  CallMeta,
  DispositionSuggestion,
  ComplianceCheckItem,
  CRMField,
  ACWState,
} from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/grainger-tokens';

interface ACWPanelProps {
  /** The final completed summary from the active-call SummaryViewer */
  finalSummary: string;
  /** All historical summary versions (for reference) */
  summaryVersions: Summary[];
  /** Caller identity — displayed in the ACW header */
  caller: CallerInfo;
  /** Call metadata — displayed in the meta bar */
  callMeta: CallMeta;
  /** Conversation ID for API calls */
  conversationId: string;
  /** Callback when agent completes ACW (Save & Complete) */
  onComplete: (state: ACWState) => void;
}

export default function ACWPanel({
  finalSummary,
  summaryVersions,
  caller,
  callMeta,
  conversationId,
  onComplete,
}: ACWPanelProps) {
  const [activeTab, setActiveTab] = useState<'summary' | 'crm' | 'quality'>('summary');
  const [acwElapsed, setAcwElapsed] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  // --- Wrap-up notes (pre-filled from AI summary) ---
  const [wrapUpNotes, setWrapUpNotes] = useState(finalSummary);

  // --- Disposition code ---
  // PLACEHOLDER: In production, these come from a backend endpoint or
  // are generated by the LLM based on the conversation summary.
  const [dispositionSuggestions] = useState<DispositionSuggestion[]>([
    { code: 'PLACEHOLDER-RESOLVED', label: 'Issue Resolved', confidence: 0 },
    { code: 'PLACEHOLDER-ESCALATED', label: 'Escalated', confidence: 0 },
    { code: 'PLACEHOLDER-FOLLOWUP', label: 'Follow-Up Required', confidence: 0 },
  ]);
  const [selectedDisposition, setSelectedDisposition] = useState<string | null>(null);

  // --- Compliance checklist ---
  // PLACEHOLDER: In production, items are auto-checked by the AI based
  // on transcript analysis during the active call.
  const [checklist, setChecklist] = useState<ComplianceCheckItem[]>([
    { id: 1, label: 'Verified customer identity', done: false, auto: false },
    { id: 2, label: 'Confirmed order number', done: false, auto: false },
    { id: 3, label: 'Identified root cause', done: false, auto: false },
    { id: 4, label: 'Explained resolution clearly', done: false, auto: false },
    { id: 5, label: 'Offered compensation if applicable', done: false, auto: false },
    { id: 6, label: 'Confirmed next steps & timeline', done: false, auto: false },
    { id: 7, label: 'Asked if anything else needed', done: false, auto: false },
  ]);

  // --- CRM fields ---
  // PLACEHOLDER: In production, these are AI-extracted from the transcript
  // and populated by the summary_generator or a dedicated CRM-mapping service.
  const [crmFields] = useState<CRMField[]>([
    { field: 'Case Subject', value: '[AI-generated — not yet implemented]', source: 'AI', editable: true },
    { field: 'Case Type', value: '[AI-generated — not yet implemented]', source: 'AI', editable: true },
    { field: 'Case Status', value: '[AI-generated — not yet implemented]', source: 'AI', editable: true },
    { field: 'Priority', value: '[AI-generated — not yet implemented]', source: 'AI', editable: true },
    { field: 'Root Cause', value: '[AI-generated — not yet implemented]', source: 'AI', editable: true },
    { field: 'Resolution Action', value: '[AI-generated — not yet implemented]', source: 'AI', editable: true },
  ]);

  // --- Agent feedback ---
  const [agentRating, setAgentRating] = useState<'up' | 'down' | null>(null);

  // ACW timer — counts up every second until saved
  useEffect(() => {
    if (isSaved) return;
    const interval = setInterval(() => setAcwElapsed((e) => e + 1), 1000);
    return () => clearInterval(interval);
  }, [isSaved]);

  const handleSave = useCallback(() => {
    setIsSaving(true);
    // PLACEHOLDER: In production, this calls:
    //   PUT /api/conversations/{conversationId}/complete
    //   POST /api/conversations/{conversationId}/disposition
    //   PUT /api/conversations/{conversationId}/wrap-up-notes
    // See "Capabilities Not Yet Built" section at end of this guide.
    setTimeout(() => {
      setIsSaving(false);
      setIsSaved(true);
      onComplete({
        wrapUpNotes,
        selectedDisposition,
        checklist,
        agentRating,
        isSaving: false,
        isSaved: true,
        acwElapsedSeconds: acwElapsed,
      });
    }, 1200);
  }, [wrapUpNotes, selectedDisposition, checklist, agentRating, acwElapsed, onComplete, conversationId]);

  const toggleCheckItem = useCallback((id: number) => {
    setChecklist((prev) =>
      prev.map((item) => (item.id === id ? { ...item, done: !item.done } : item))
    );
  }, []);

  const tabs = [
    { id: 'summary' as const, label: 'Summary & Notes' },
    { id: 'crm' as const, label: 'CRM Fields' },
    { id: 'quality' as const, label: 'Quality' },
  ];

  const checklistDone = checklist.filter((c) => c.done).length;
  const checklistTotal = checklist.length;
  const timerColor =
    acwElapsed > 90 ? colors.error : acwElapsed > 60 ? colors.warning : colors.success;

  return (
    <div style={styles.container}>
      {/* ── ACW Header ── */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <div style={styles.headerTitle}>After-Call Work</div>
          <div style={styles.headerSub}>
            {caller.customerName} · {caller.company} · {callMeta.duration} call
          </div>
        </div>
        <div style={styles.headerRight}>
          <div style={styles.timerBlock}>
            <div style={styles.timerLabel}>ACW TIMER</div>
            <div style={{ ...styles.timerValue, color: timerColor }}>
              {Math.floor(acwElapsed / 60)}:{String(acwElapsed % 60).padStart(2, '0')}
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={isSaving || isSaved}
            style={{
              ...styles.saveButton,
              backgroundColor: isSaved ? colors.success : colors.primary,
              opacity: isSaving ? 0.7 : 1,
              cursor: isSaving || isSaved ? 'default' : 'pointer',
            }}
          >
            {isSaved ? '✓ Saved' : isSaving ? 'Saving...' : 'Save & Complete'}
          </button>
        </div>
      </div>

      {/* ── Tab Navigation ── */}
      <div style={styles.tabBar}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              ...styles.tab,
              color: activeTab === tab.id ? colors.primary : colors.textLight,
              borderBottom:
                activeTab === tab.id
                  ? `2px solid ${colors.primary}`
                  : '2px solid transparent',
              fontWeight:
                activeTab === tab.id
                  ? typography.fontWeight.bold
                  : typography.fontWeight.medium,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab Content ── */}
      <div style={styles.tabContent}>
        {/* --- Tab 1: Summary & Notes --- */}
        {activeTab === 'summary' && (
          <div style={styles.tabInner}>
            {/* AI Summary (read-only) */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>AI-Generated Summary</span>
                <span style={styles.autoBadge}>AUTO-GENERATED</span>
              </div>
              <div style={styles.summaryText}>
                {finalSummary || 'No summary was generated during this call.'}
              </div>
              {summaryVersions.length > 0 && (
                <div style={styles.versionNote}>
                  {summaryVersions.length} version(s) generated during call
                </div>
              )}
            </div>

            {/* Editable Wrap-Up Notes */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Wrap-Up Notes</span>
                <span style={styles.editableBadge}>EDITABLE</span>
              </div>
              <textarea
                value={wrapUpNotes}
                onChange={(e) => setWrapUpNotes(e.target.value)}
                disabled={isSaved}
                style={{
                  ...styles.textarea,
                  backgroundColor: isSaved ? colors.background : colors.surface,
                }}
              />
              <div style={styles.charCount}>
                AI-drafted · {wrapUpNotes.length} chars
              </div>
            </div>

            {/* Disposition Code Picker */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Disposition Code</span>
                {/* PLACEHOLDER badge — remove when AI suggestions are wired up */}
                <span style={styles.placeholderBadge}>PLACEHOLDER</span>
              </div>
              <div style={styles.dispositionList}>
                {dispositionSuggestions.map((d) => {
                  const isActive = selectedDisposition === d.code;
                  return (
                    <div
                      key={d.code}
                      onClick={() => setSelectedDisposition(d.code)}
                      style={{
                        ...styles.dispositionItem,
                        backgroundColor: isActive ? `${colors.primary}10` : colors.background,
                        border: isActive
                          ? `1.5px solid ${colors.primary}`
                          : '1.5px solid transparent',
                      }}
                    >
                      <div
                        style={{
                          ...styles.radio,
                          borderColor: isActive ? colors.primary : colors.border,
                          backgroundColor: isActive ? colors.primary : 'transparent',
                        }}
                      >
                        {isActive && <span style={styles.radioCheck}>✓</span>}
                      </div>
                      <div style={styles.dispositionLabel}>{d.label}</div>
                      <div style={styles.dispositionCode}>{d.code}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Agent Feedback */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Rate AI Summary Quality</span>
              </div>
              <div style={styles.feedbackRow}>
                {(['up', 'down'] as const).map((val) => (
                  <button
                    key={val}
                    onClick={() => setAgentRating(agentRating === val ? null : val)}
                    style={{
                      ...styles.feedbackButton,
                      backgroundColor:
                        agentRating === val
                          ? val === 'up'
                            ? `${colors.success}15`
                            : `${colors.error}15`
                          : colors.surface,
                      borderColor:
                        agentRating === val
                          ? val === 'up'
                            ? colors.success
                            : colors.error
                          : colors.borderLight,
                      color:
                        agentRating === val
                          ? val === 'up'
                            ? colors.success
                            : colors.error
                          : colors.textLight,
                    }}
                  >
                    {val === 'up' ? '👍 Accurate' : '👎 Needs Work'}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* --- Tab 2: CRM Fields --- */}
        {activeTab === 'crm' && (
          <div style={styles.tabInner}>
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Salesforce Case Fields</span>
                {/* PLACEHOLDER badge — remove when CRM extraction is wired up */}
                <span style={styles.placeholderBadge}>PLACEHOLDER</span>
              </div>
              <div style={styles.crmFieldsList}>
                {crmFields.map((f, i) => (
                  <div
                    key={f.field}
                    style={{
                      ...styles.crmRow,
                      backgroundColor: i % 2 === 0 ? colors.background : colors.surface,
                    }}
                  >
                    <span style={styles.crmLabel}>{f.field}</span>
                    <span style={styles.crmValue}>{f.value}</span>
                    <span
                      style={{
                        ...styles.sourceBadge,
                        color: f.source === 'AI' ? colors.success : colors.info,
                        backgroundColor:
                          f.source === 'AI' ? `${colors.success}15` : `${colors.info}15`,
                      }}
                    >
                      {f.source}
                    </span>
                  </div>
                ))}
              </div>
              <div style={styles.crmNote}>
                AI-extracted fields will auto-populate Salesforce Case on save
              </div>
            </div>
          </div>
        )}

        {/* --- Tab 3: Quality --- */}
        {activeTab === 'quality' && (
          <div style={styles.tabInner}>
            {/* Compliance Checklist */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Call Quality Checklist</span>
                <span
                  style={{
                    ...styles.checkProgress,
                    color:
                      checklistDone === checklistTotal ? colors.success : colors.warning,
                  }}
                >
                  {checklistDone}/{checklistTotal}
                </span>
              </div>
              {/* Progress bar */}
              <div style={styles.progressTrack}>
                <div
                  style={{
                    ...styles.progressFill,
                    width: `${(checklistDone / checklistTotal) * 100}%`,
                    backgroundColor:
                      checklistDone === checklistTotal ? colors.success : colors.warning,
                  }}
                />
              </div>
              {checklist.map((item) => (
                <div
                  key={item.id}
                  onClick={() => toggleCheckItem(item.id)}
                  style={styles.checkItem}
                >
                  <span
                    style={{
                      ...styles.checkBox,
                      color: item.done ? colors.success : colors.border,
                    }}
                  >
                    {item.done ? '☑' : '☐'}
                  </span>
                  <span
                    style={{
                      ...styles.checkLabel,
                      textDecoration: item.done ? 'line-through' : 'none',
                      color: item.done ? colors.textLight : colors.text,
                    }}
                  >
                    {item.label}
                  </span>
                  {item.auto && item.done && (
                    <span style={styles.autoTag}>auto-detected</span>
                  )}
                </div>
              ))}
            </div>

            {/* Interaction Metrics */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Interaction Metrics</span>
                {/* PLACEHOLDER badge — remove when real metrics are wired up */}
                <span style={styles.placeholderBadge}>PLACEHOLDER</span>
              </div>
              <div style={styles.metricsGrid}>
                {[
                  ['Handle Time', callMeta.duration],
                  ['Hold Time', '—'],
                  ['Transfers', '—'],
                  ['Sentiment', '—'],
                  ['FCR', '—'],
                  ['Compliance', `${checklistDone}/${checklistTotal}`],
                ].map(([label, value]) => (
                  <div key={label} style={styles.metricCard}>
                    <div style={styles.metricLabel}>{label}</div>
                    <div style={styles.metricValue}>{value}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Agent Feedback (duplicated on this tab per reference design) */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Rate AI Summary Quality</span>
              </div>
              <div style={styles.feedbackRow}>
                {(['up', 'down'] as const).map((val) => (
                  <button
                    key={val}
                    onClick={() => setAgentRating(agentRating === val ? null : val)}
                    style={{
                      ...styles.feedbackButton,
                      backgroundColor:
                        agentRating === val
                          ? val === 'up'
                            ? `${colors.success}15`
                            : `${colors.error}15`
                          : colors.surface,
                      borderColor:
                        agentRating === val
                          ? val === 'up'
                            ? colors.success
                            : colors.error
                          : colors.borderLight,
                      color:
                        agentRating === val
                          ? val === 'up'
                            ? colors.success
                            : colors.error
                          : colors.textLight,
                    }}
                  >
                    {val === 'up' ? '👍 Accurate' : '👎 Needs Work'}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────
const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100%',
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    boxShadow: shadows.base,
    overflow: 'hidden',
  },
  // Header
  header: {
    backgroundColor: colors.text,
    color: colors.surface,
    padding: '12px 16px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  headerLeft: {
    flex: 1,
    minWidth: 0,
  },
  headerTitle: {
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.bold,
  },
  headerSub: {
    fontSize: typography.fontSize.xs,
    color: '#AAAAAA',
    marginTop: '2px',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  headerRight: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    flexShrink: 0,
  },
  timerBlock: {
    textAlign: 'right' as const,
  },
  timerLabel: {
    fontSize: '10px',
    color: '#AAAAAA',
    letterSpacing: '0.05em',
  },
  timerValue: {
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.bold,
    fontFamily: typography.fontFamily.mono,
  },
  saveButton: {
    padding: '8px 16px',
    borderRadius: borderRadius.sm,
    border: 'none',
    fontWeight: typography.fontWeight.bold,
    fontSize: typography.fontSize.xs,
    color: colors.surface,
    letterSpacing: '0.02em',
    transition: 'all 0.2s',
  },
  // Tabs
  tabBar: {
    display: 'flex',
    gap: '2px',
    padding: `${spacing.sm} ${spacing.md} 0`,
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  tab: {
    flex: 1,
    padding: `${spacing.sm} ${spacing.sm}`,
    background: 'none',
    border: 'none',
    fontSize: typography.fontSize.xs,
    cursor: 'pointer',
    transition: 'all 0.15s',
    textAlign: 'center' as const,
  },
  // Content
  tabContent: {
    flex: 1,
    overflowY: 'auto' as const,
  },
  tabInner: {
    padding: spacing.md,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
  },
  // Sections
  section: {
    padding: spacing.md,
    backgroundColor: colors.surface,
    border: `1px solid ${colors.borderLight}`,
    borderRadius: borderRadius.sm,
  },
  sectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.bold,
    color: colors.textLight,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.07em',
  },
  autoBadge: {
    fontSize: '10px',
    fontWeight: typography.fontWeight.bold,
    color: colors.success,
    backgroundColor: `${colors.success}15`,
    padding: '2px 8px',
    borderRadius: borderRadius.full,
  },
  editableBadge: {
    fontSize: '10px',
    fontWeight: typography.fontWeight.bold,
    color: colors.info,
    backgroundColor: `${colors.info}15`,
    padding: '2px 8px',
    borderRadius: borderRadius.full,
  },
  placeholderBadge: {
    fontSize: '10px',
    fontWeight: typography.fontWeight.bold,
    color: colors.warning,
    backgroundColor: `${colors.warning}20`,
    padding: '2px 8px',
    borderRadius: borderRadius.full,
    border: `1px dashed ${colors.warning}`,
  },
  // Summary
  summaryText: {
    fontSize: typography.fontSize.sm,
    color: colors.text,
    lineHeight: typography.lineHeight.relaxed,
    whiteSpace: 'pre-wrap' as const,
    wordWrap: 'break-word' as const,
    padding: spacing.sm,
    backgroundColor: colors.background,
    borderRadius: borderRadius.sm,
    borderLeft: `3px solid ${colors.primary}`,
  },
  versionNote: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    marginTop: spacing.sm,
    fontStyle: 'italic' as const,
  },
  // Textarea
  textarea: {
    width: '100%',
    minHeight: '88px',
    padding: spacing.sm,
    border: `1px solid ${colors.borderLight}`,
    borderRadius: borderRadius.sm,
    fontSize: typography.fontSize.sm,
    lineHeight: 1.65,
    color: colors.text,
    resize: 'vertical' as const,
    outline: 'none',
    boxSizing: 'border-box' as const,
    fontFamily: typography.fontFamily.primary,
  },
  charCount: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    marginTop: spacing.xs,
    textAlign: 'right' as const,
  },
  // Disposition
  dispositionList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.xs,
  },
  dispositionItem: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: `${spacing.sm} ${spacing.sm}`,
    borderRadius: borderRadius.sm,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  radio: {
    width: '18px',
    height: '18px',
    borderRadius: borderRadius.full,
    border: '2px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    transition: 'all 0.15s',
  },
  radioCheck: {
    color: colors.surface,
    fontSize: '10px',
  },
  dispositionLabel: {
    fontSize: typography.fontSize.sm,
    color: colors.text,
    flex: 1,
  },
  dispositionCode: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
  },
  // Feedback
  feedbackRow: {
    display: 'flex',
    gap: spacing.sm,
  },
  feedbackButton: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    padding: `${spacing.sm} ${spacing.sm}`,
    borderRadius: borderRadius.sm,
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.semibold,
    cursor: 'pointer',
    transition: 'all 0.15s',
    border: '1.5px solid',
    background: 'none',
  },
  // CRM
  crmFieldsList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1px',
  },
  crmRow: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: '7px 10px',
    borderRadius: '3px',
  },
  crmLabel: {
    width: '120px',
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.semibold,
    color: colors.textLight,
    flexShrink: 0,
  },
  crmValue: {
    flex: 1,
    fontSize: typography.fontSize.sm,
    color: colors.text,
  },
  sourceBadge: {
    fontSize: '10px',
    fontWeight: typography.fontWeight.bold,
    padding: '2px 6px',
    borderRadius: borderRadius.sm,
  },
  crmNote: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    marginTop: spacing.sm,
    display: 'flex',
    alignItems: 'center',
    gap: spacing.xs,
  },
  // Quality
  checkProgress: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.bold,
  },
  progressTrack: {
    height: '3px',
    backgroundColor: colors.borderLight,
    borderRadius: '2px',
    marginBottom: spacing.sm,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: '2px',
    transition: 'width 0.3s ease',
  },
  checkItem: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: '5px 8px',
    borderRadius: '3px',
    cursor: 'pointer',
    marginBottom: '2px',
  },
  checkBox: {
    fontSize: typography.fontSize.base,
    flexShrink: 0,
  },
  checkLabel: {
    fontSize: typography.fontSize.sm,
    flex: 1,
  },
  autoTag: {
    fontSize: '9px',
    color: colors.textLight,
    fontStyle: 'italic' as const,
  },
  // Metrics
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: spacing.sm,
  },
  metricCard: {
    padding: `${spacing.sm} ${spacing.sm}`,
    backgroundColor: colors.background,
    borderRadius: borderRadius.sm,
  },
  metricLabel: {
    fontSize: '10px',
    color: colors.textLight,
    fontWeight: typography.fontWeight.semibold,
    marginBottom: '2px',
  },
  metricValue: {
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.bold,
    color: colors.text,
  },
};
```

---

## Step 6: Rewrite `page.tsx` — The 3-Panel Phase-Driven Layout

**File:** `frontend/src/app/page.tsx` (MODIFY existing)

This is the core change. Replace the entire file content. The key changes:

1. **Grid goes from `1fr 1fr` to `240px 1fr 340px`** (active) / `240px 1fr 400px` (ACW)
2. **New `callPhase` state** drives which components render
3. **Left panel** conditionally shows full content (active) or compact (ACW)
4. **Right panel** conditionally shows Summary+MCP (active) or ACWPanel (ACW)
5. **Center panel** (TranscriptViewer) is always rendered unchanged
6. **"End Call" button** in the header triggers the phase transition

Replace the entire `page.tsx` with the following. The structure preserves all existing state variables and WebSocket handlers from the word-streaming refactor, adding call phase management on top.

> **Important:** This code uses the `useTranscriptStream` hook for word-by-word streaming
> (`onWordInterim`/`onWordFinal`), NOT the old batch pattern (`handleTranscriptBatch`/`onTranscriptBatch`).

```typescript
'use client';

/**
 * Main Conversation Page — 3-Panel Phase-Driven Layout
 *
 * Active Call: [Left: Caller + Meta + History] [Center: Transcript] [Right: Summary + MCP]
 * ACW Phase:  [Left: Caller (compact)]         [Center: Transcript] [Right: ACW Panel]
 *
 * The call phase state drives which components render in the left and right columns.
 * No overlays, no drawers, no z-index headaches — just clean conditional renders.
 */

import { useState, useEffect, useCallback } from 'react';
import TranscriptViewer from '@/components/TranscriptViewer';
import SummaryViewer from '@/components/SummaryViewer';
import ConnectionStatus from '@/components/ConnectionStatus';
import MCPSuggestionsBox from '@/components/MCPSuggestionsBox';
import CallerInfoCard from '@/components/CallerInfoCard';
import CallMetaCard from '@/components/CallMetaCard';
import InteractionHistory from '@/components/InteractionHistory';
import ACWPanel from '@/components/ACWPanel';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useTranscriptStream } from '@/hooks/useTranscriptStream';
import {
  Summary,
  ConversationCreateResponse,
  CallPhase,
  CallerInfo,
  CallMeta,
  InteractionHistoryItem,
  ACWState,
} from '@/types/conversation';
import { colors, spacing, typography } from '@/styles/grainger-tokens';

// ── Hardcoded demo data ─────────────────────────────────────────
// PLACEHOLDER: In production, CallerInfo comes from a screen-pop API
// (Genesys Interaction event → customer lookup). CallMeta comes from
// the Genesys Interaction object. History comes from Salesforce CRM.
// See "Capabilities Not Yet Built" at end of guide.
const DEMO_CALLER: CallerInfo = {
  customerName: 'Marcus Johnson',
  company: 'Johnson Industrial Supply',
  accountNumber: '0861537',
  tier: 'Gold',
};

const DEMO_CALL_META: CallMeta = {
  interactionId: 'INT-2026-4829',
  channel: 'Voice',
  queue: 'Industrial MRO — Orders & Returns',
  startTime: new Date().toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  }),
  duration: '0:00',
  agent: 'Sarah Mitchell',
};

const DEMO_HISTORY: InteractionHistoryItem[] = [
  {
    date: 'Jan 28, 2026',
    subject: 'Order placed — #771903 — keyboard & accessories',
    channel: 'Web',
    resolution: 'Resolved — order confirmed',
  },
  {
    date: 'Jan 22, 2026',
    subject: 'Order status inquiry — #784562',
    channel: 'Voice',
    resolution: 'Resolved — provided tracking info',
  },
  {
    date: 'Jan 10, 2026',
    subject: 'Product recommendation — office setup',
    channel: 'Chat',
    resolution: 'Resolved — items added to cart',
  },
];

export default function Home() {
  // ── Call Phase ──
  const [callPhase, setCallPhase] = useState<CallPhase>('active');

  // ── Existing state (preserved from word-streaming refactor) ──
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [currentSummary, setCurrentSummary] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Transcript stream state (word-by-word) — preserved from word-streaming refactor
  const { transcriptLines, handleWordInterim, handleWordFinal } = useTranscriptStream();

  // ── Call duration timer ──
  const [callDuration, setCallDuration] = useState(0);
  useEffect(() => {
    if (callPhase !== 'active') return;
    const timer = setInterval(() => setCallDuration((d) => d + 1), 1000);
    return () => clearInterval(timer);
  }, [callPhase]);

  const formattedDuration = `${Math.floor(callDuration / 60)}:${String(callDuration % 60).padStart(2, '0')}`;

  // ── WebSocket handlers (preserved from word-streaming refactor) ──
  const handleSummaryStart = useCallback((version: number) => {
    setIsGenerating(true);
    setCurrentVersion(version);
    setCurrentSummary('');
  }, []);

  const handleSummaryToken = useCallback((token: string) => {
    setCurrentSummary((prev) => prev + token);
  }, []);

  const handleSummaryComplete = useCallback(
    (summaryText: string, version: number) => {
      setIsGenerating(false);
      setSummaries((prev) => [
        ...prev,
        {
          version,
          summary_text: summaryText,
          transcript_line_count: transcriptLines.length,
          generated_at: new Date().toISOString(),
        },
      ]);
    },
    [transcriptLines.length]
  );

  const handleStreamingComplete = useCallback(() => {
    console.log('Transcript streaming complete');
    setIsLoading(false);
  }, []);

  // Initialize WebSocket — uses word-streaming callbacks
  const { connectionState, reconnect } = useWebSocket(conversationId, {
    onWordInterim: handleWordInterim,
    onWordFinal: handleWordFinal,
    onSummaryStart: handleSummaryStart,
    onSummaryToken: handleSummaryToken,
    onSummaryComplete: handleSummaryComplete,
    onStreamingComplete: handleStreamingComplete,
  });

  // ── Create conversation on mount (preserved exactly) ──
  useEffect(() => {
    const createConversation = async () => {
      try {
        const apiUrl =
          process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
        const response = await fetch(`${apiUrl}/api/conversations`, {
          method: 'POST',
        });
        if (!response.ok) {
          throw new Error(`Failed to create conversation: ${response.status}`);
        }
        const data: ConversationCreateResponse = await response.json();
        setConversationId(data.conversation_id);
        console.log('Conversation created:', data.conversation_id);
      } catch (err) {
        console.error('Error creating conversation:', err);
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to create conversation'
        );
        setIsLoading(false);
      }
    };
    createConversation();
  }, []);

  // ── Phase transition handler ──
  const handleEndCall = useCallback(() => {
    setCallPhase('acw');
    setIsLoading(false);
  }, []);

  const handleACWComplete = useCallback((acwState: ACWState) => {
    console.log('ACW completed:', acwState);
    // PLACEHOLDER: In production, this would call backend APIs
    // to persist disposition, wrap-up notes, and mark conversation complete.
  }, []);

  // ── Compute the final summary text for ACW ──
  // Uses the currentSummary (latest streamed text) if available,
  // otherwise falls back to the most recent completed summary.
  const finalSummaryForACW =
    currentSummary ||
    (summaries.length > 0
      ? summaries[summaries.length - 1].summary_text
      : '');

  // ── Error state (preserved) ──
  if (error) {
    return (
      <div style={styles.errorContainer}>
        <h1 style={styles.errorTitle}>Error</h1>
        <p style={styles.errorMessage}>{error}</p>
        <p style={styles.errorHint}>
          Make sure the backend server is running on port 8765.
        </p>
        <button onClick={() => window.location.reload()} style={styles.retryButton}>
          Retry
        </button>
      </div>
    );
  }

  // ── Determine grid columns based on call phase ──
  const gridColumns =
    callPhase === 'active' ? '240px 1fr 340px' : '240px 1fr 400px';

  return (
    <main style={styles.main}>
      {/* ── Header ── */}
      <header style={styles.header}>
        <div style={styles.headerContent}>
          <h1 style={styles.appTitle}>
            <span style={styles.titleIcon}>🎙️</span>
            Transcript & Summary Streaming
          </h1>
          <div style={styles.headerRight}>
            {callPhase === 'active' && (
              <div style={styles.durationDisplay}>
                {formattedDuration}
              </div>
            )}
            <ConnectionStatus state={connectionState} onReconnect={reconnect} />
            {callPhase === 'active' && (
              <button onClick={handleEndCall} style={styles.endCallButton}>
                End Call
              </button>
            )}
            {callPhase === 'acw' && (
              <span style={styles.acwBadge}>ACW</span>
            )}
          </div>
        </div>
      </header>

      {/* ── 3-Panel Layout ── */}
      <div style={{ ...styles.panelContainer, gridTemplateColumns: gridColumns }}>
        {/* ── LEFT PANEL ── */}
        <div style={styles.leftPanel}>
          <CallerInfoCard caller={DEMO_CALLER} />
          {callPhase === 'active' && (
            <>
              <CallMetaCard
                meta={{ ...DEMO_CALL_META, duration: formattedDuration }}
              />
              <InteractionHistory history={DEMO_HISTORY} />
            </>
          )}
        </div>

        {/* ── CENTER PANEL (always the same) ── */}
        <div style={styles.centerPanel}>
          <TranscriptViewer lines={transcriptLines} isLoading={isLoading} />
        </div>

        {/* ── RIGHT PANEL (phase-driven) ── */}
        <div style={styles.rightPanel}>
          {callPhase === 'active' ? (
            <>
              <div style={styles.mcpBoxInPanel}>
                <MCPSuggestionsBox conversationId={conversationId} />
              </div>
              <SummaryViewer
                summaries={summaries}
                currentSummary={currentSummary}
                isGenerating={isGenerating}
                currentVersion={currentVersion || undefined}
                conversationId={conversationId}
              />
            </>
          ) : (
            <ACWPanel
              finalSummary={finalSummaryForACW}
              summaryVersions={summaries}
              caller={DEMO_CALLER}
              callMeta={{ ...DEMO_CALL_META, duration: formattedDuration }}
              conversationId={conversationId || ''}
              onComplete={handleACWComplete}
            />
          )}
        </div>
      </div>

      {/* ── Footer ── */}
      <footer style={styles.footer}>
        <p style={styles.footerText}>
          Demo - Production-Lite Audio CSA Assistant
        </p>
        {conversationId && (
          <p style={styles.conversationIdText}>
            Conversation: {conversationId}
          </p>
        )}
      </footer>
    </main>
  );
}

// ── Styles ──────────────────────────────────────────────────────
const styles = {
  main: {
    display: 'flex',
    flexDirection: 'column' as const,
    minHeight: '100vh',
    backgroundColor: colors.background,
  },
  header: {
    backgroundColor: colors.surface,
    borderBottom: `2px solid ${colors.primary}`,
    padding: spacing.md,
  },
  headerContent: {
    maxWidth: '1600px',
    margin: '0 auto',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap' as const,
    gap: spacing.md,
  },
  appTitle: {
    fontSize: typography.fontSize['2xl'],
    fontWeight: typography.fontWeight.bold,
    color: colors.text,
    margin: 0,
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  titleIcon: {
    fontSize: typography.fontSize['2xl'],
  },
  headerRight: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.md,
  },
  durationDisplay: {
    fontSize: typography.fontSize.lg,
    fontWeight: typography.fontWeight.bold,
    fontFamily: typography.fontFamily.mono,
    color: colors.text,
    padding: `${spacing.xs} ${spacing.sm}`,
    backgroundColor: colors.background,
    borderRadius: '4px',
  },
  endCallButton: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.bold,
    color: colors.surface,
    backgroundColor: colors.primary,
    border: 'none',
    borderRadius: '6px',
    padding: `${spacing.sm} ${spacing.md}`,
    cursor: 'pointer',
    letterSpacing: '0.02em',
    transition: 'opacity 0.15s',
  },
  acwBadge: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.bold,
    color: colors.surface,
    backgroundColor: colors.warning,
    padding: '4px 12px',
    borderRadius: '4px',
    letterSpacing: '0.05em',
    textTransform: 'uppercase' as const,
  },
  // Layout
  panelContainer: {
    flex: 1,
    maxWidth: '1600px',
    margin: '0 auto',
    padding: spacing.md,
    display: 'grid',
    gap: spacing.md,
    width: '100%',
  },
  leftPanel: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
    overflowY: 'auto' as const,
  },
  centerPanel: {
    minHeight: '600px',
    display: 'flex',
    flexDirection: 'column' as const,
  },
  rightPanel: {
    minHeight: '600px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
  },
  mcpBoxInPanel: {
    flexShrink: 0,
  },
  // Footer
  footer: {
    backgroundColor: colors.surface,
    borderTop: `1px solid ${colors.border}`,
    padding: spacing.md,
    textAlign: 'center' as const,
  },
  footerText: {
    fontSize: typography.fontSize.sm,
    color: colors.textLight,
    margin: 0,
  },
  conversationIdText: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    marginTop: spacing.xs,
    fontFamily: typography.fontFamily.mono,
  },
  // Error states (preserved)
  errorContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    padding: spacing.xl,
    textAlign: 'center' as const,
  },
  errorTitle: {
    fontSize: typography.fontSize['2xl'],
    fontWeight: typography.fontWeight.bold,
    color: colors.error,
    marginBottom: spacing.md,
  },
  errorMessage: {
    fontSize: typography.fontSize.base,
    color: colors.text,
    marginBottom: spacing.sm,
  },
  errorHint: {
    fontSize: typography.fontSize.sm,
    color: colors.textLight,
    marginBottom: spacing.lg,
  },
  retryButton: {
    fontSize: typography.fontSize.base,
    color: colors.surface,
    backgroundColor: colors.primary,
    border: 'none',
    borderRadius: '8px',
    padding: `${spacing.sm} ${spacing.lg}`,
    cursor: 'pointer',
    fontWeight: typography.fontWeight.semibold,
  },
};
```

---

## Step 7: Verify the Build

After making all changes, run:

```bash
cd frontend && npm run build
```

Fix any TypeScript errors. Common issues to watch for:
- Missing imports (ensure all new components are created)
- Type mismatches between props and the types defined in Step 1
- Ensure `as const` is applied to any inline style objects with literal string values

---

## File Summary — What Gets Created / Modified

| Action | File | Purpose |
|--------|------|---------|
| MODIFY | `frontend/src/types/conversation.ts` | Add `CallPhase` + supporting types |
| CREATE | `frontend/src/components/CallerInfoCard.tsx` | Left panel — caller identity |
| CREATE | `frontend/src/components/CallMetaCard.tsx` | Left panel — call metadata (active only) |
| CREATE | `frontend/src/components/InteractionHistory.tsx` | Left panel — past interactions (active only) |
| CREATE | `frontend/src/components/ACWPanel.tsx` | Right panel — ACW with 3 tabs |
| CREATE | `frontend/src/hooks/useTranscriptStream.ts` | Word-by-word transcript stream hook (from streaming refactor) |
| MODIFY | `frontend/src/hooks/useWebSocket.ts` | Added `onWordInterim`/`onWordFinal` callbacks (from streaming refactor) |
| MODIFY | `frontend/src/components/TranscriptViewer.tsx` | Updated to render `is_final` state per line (from streaming refactor) |
| MODIFY | `frontend/src/app/page.tsx` | 3-panel layout with phase-driven rendering + word-streaming |

**No changes** to these existing files:
- `SummaryViewer.tsx` — unchanged
- `MCPSuggestionsBox.tsx` — unchanged
- `ConnectionStatus.tsx` — unchanged
- `grainger-tokens.ts` — unchanged

---

## Capabilities Not Yet Built (Systematic Backlog)

The following capabilities are referenced by placeholders in the implementation above. Each needs its own implementation work.

### Backend API Endpoints Needed

| # | Endpoint | Method | Purpose | Used By |
|---|----------|--------|---------|---------|
| 1 | `/api/conversations/{id}/complete` | PUT | Mark conversation as ACW-complete, set `ended_at` | ACWPanel `handleSave` |
| 2 | `/api/conversations/{id}/disposition` | POST | Save selected disposition code | ACWPanel disposition picker |
| 3 | `/api/conversations/{id}/wrap-up-notes` | PUT | Save agent-edited wrap-up notes | ACWPanel wrap-up textarea |
| 4 | `/api/conversations/{id}/case-fields` | GET | Return AI-predicted Salesforce case fields | ACWPanel CRM tab |
| 5 | `/api/conversations/{id}/feedback` | POST | Save agent's thumbs up/down rating | ACWPanel feedback buttons |
| 6 | `/api/conversations/{id}/checklist` | GET/PUT | Get AI-auto-checked compliance items / save agent edits | ACWPanel quality tab |

### Backend Services Needed

| # | Service | Purpose | Details |
|---|---------|---------|---------|
| 7 | **Disposition Suggestion Service** | Generate AI-suggested disposition codes with confidence scores | Analyze final summary + transcript → suggest 3 ranked codes. Requires a disposition code taxonomy (enum list). Wire into `summary_generator.py` or a new service. |
| 8 | **CRM Field Extraction Service** | Extract Salesforce case fields from transcript/summary | Parse transcript for order numbers, SKUs, root cause, resolution, etc. Output structured `CRMField[]`. Could be an LLM call with structured output or regex extraction pipeline. |
| 9 | **Compliance Checker Service** | Auto-check compliance items by analyzing transcript | Parse transcript to detect: identity verification, order confirmation, root cause identification, resolution explanation, next steps confirmation. Output `ComplianceCheckItem[]` with `auto: true`. |
| 10 | **Interaction Metrics Calculator** | Compute call quality metrics post-call | Calculate: handle time, hold time, transfers, first contact resolution flag, sentiment score arc. Some from Genesys metadata, sentiment from LLM analysis. |

### Frontend Capabilities Needed

| # | Capability | Purpose | Details |
|---|-----------|---------|---------|
| 11 | **Screen-Pop Integration** | Populate `CallerInfo` from real data on inbound call | Currently hardcoded `DEMO_CALLER`. In production: Genesys sends customer ANI/interaction data → frontend calls customer lookup API → populates `CallerInfo` dynamically. |
| 12 | **Call Metadata from Genesys** | Populate `CallMeta` from real interaction data | Currently hardcoded `DEMO_CALL_META`. In production: Genesys Cloud SDK or Platform API provides interaction ID, queue, channel, agent, timing. |
| 13 | **Interaction History from Salesforce** | Fetch past interactions for the customer | Currently hardcoded `DEMO_HISTORY`. In production: query Salesforce Cases/Interactions by Account ID. |
| 14 | **Real Disposition Code Taxonomy** | Replace placeholder disposition codes with production taxonomy | Define the actual set of valid disposition/wrap-up codes used in the contact center. Likely loaded from a config endpoint or Genesys wrap-up code API. |
| 15 | **CRM Field Edit-in-Place** | Let agents edit AI-suggested CRM fields before save | Currently read-only. Add inline editing with validation for each field type. |
| 16 | **Follow-Up Actions** | Render follow-up tasks with assignee and due date | Present in the `acw-summary-panel.jsx` reference but omitted from the initial ACWPanel for simplicity. Add as a sub-section in the Summary & Notes tab. |
| 17 | **Sentiment Arc Visualization** | Show sentiment trend from negative to positive | Present in the reference panel. Requires sentiment analysis from the backend (per-utterance or summary-level). |
| 18 | **ACW Timer Color in Header** | Show ACW countdown/count-up in the main page header | Currently only inside ACWPanel. Optionally mirror it in the page header for extra visibility. |

### Infrastructure / Integration

| # | Capability | Purpose | Details |
|---|-----------|---------|---------|
| 19 | **MCP Tool Calling** | Replace MCPSuggestionsBox placeholder with real product/order lookups | Follow `code_examples/MCP_CLIENT_IMPLEMENTATION_GUIDE.md`. Wire backend MCP client → new WebSocket event type → frontend display. |
| 20 | **Salesforce Save Integration** | Actually persist ACW data to Salesforce Service Cloud | On "Save & Complete": create/update Salesforce Case, attach transcript, set disposition, create follow-up Task. Requires Salesforce Connected App + REST API or Composite API. |
| 21 | **WebSocket Event: `call.ended`** | Backend signals end-of-call to trigger ACW automatically | Currently the agent clicks "End Call" manually. In production, Genesys disconnect event should trigger this server-side, and the frontend should auto-transition to ACW on receiving the event. |
| 22 | **Backend DB Schema for ACW** | Persist wrap-up notes, disposition, checklist, feedback | Add columns/tables to `domain.py`: `Conversation.disposition_code`, `Conversation.wrap_up_notes`, `Conversation.agent_feedback`, `ComplianceCheckResult` table. |

### WebSocket Event Types to Add

Add these to `frontend/src/types/websocket.ts` when implementing the corresponding backend capabilities:

```typescript
// Future event types (add when backend supports them)
| 'call.ended'           // Genesys disconnect → auto-transition to ACW
| 'disposition.suggested' // AI-generated disposition suggestions with confidence
| 'compliance.checked'    // Auto-checked compliance items from transcript analysis
| 'crm.fields.ready'     // AI-extracted CRM fields ready for review
| 'acw.saved'            // Confirmation that ACW data persisted to Salesforce
```

---

## Phase Transition Behavior

The ACW transition is triggered by **the agent clicking the "End Call" button** in the header. This is the only trigger in this implementation.

The `streaming.complete` WebSocket event (which fires when the backend finishes streaming the transcript file) does NOT auto-transition to ACW. It only sets `isLoading = false` to stop the streaming indicator. The rationale: in production, transcript streaming ending does not mean the call is over — the agent may still be wrapping up the conversation. The explicit "End Call" click is the deliberate signal.

**Future enhancement (backlog item #21):** In production, a `call.ended` event from Genesys would auto-transition to ACW when the voice channel disconnects. The "End Call" button would remain as a manual fallback.

---

## Demo Walkthrough

For a demo, the flow works like this:

1. **Page loads** → conversation created → transcript starts streaming in center panel
2. **Active call phase** → left panel shows caller info, call details, history. Right panel shows MCP suggestions box and rolling AI summary with typewriter effect.
3. **Agent clicks "End Call"** → instant transition:
   - Left panel collapses to just CallerInfoCard (compact)
   - Right panel swaps to ACWPanel with 3 tabs
   - Center panel transcript stays put — agent can reference it
4. **ACW phase** → agent reviews AI summary, edits wrap-up notes, selects disposition, checks compliance items, rates summary quality
5. **Agent clicks "Save & Complete"** → ACW timer stops, button turns green

The demo observer sees the transcript and ACW panel side by side the entire time. No modal obscures the transcript. No drawer slides over content. The layout just transitions cleanly.