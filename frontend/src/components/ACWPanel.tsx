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
import StructuredSummary from './StructuredSummary';
import {
  Summary,
  CallerInfo,
  CallMeta,
  DispositionSuggestion,
  ComplianceCheckItem,
  CRMField,
  ACWState,
} from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/design-tokens';

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
  const [isEditingNotes, setIsEditingNotes] = useState(false);

  // --- Disposition code ---
  // AI-generated from conversation summary via backend API
  const [dispositionSuggestions, setDispositionSuggestions] = useState<DispositionSuggestion[]>([
    { code: 'LOADING', label: 'Loading suggestions...', confidence: 0 },
  ]);
  const [selectedDisposition, setSelectedDisposition] = useState<string | null>(null);
  const [dispositionLoading, setDispositionLoading] = useState(true);

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
  // AI-extracted from transcript via backend API
  const [crmFields, setCrmFields] = useState<CRMField[]>([
    { field: 'Case Subject', value: 'Loading...', source: 'AI', editable: true },
    { field: 'Case Type', value: 'Loading...', source: 'AI', editable: true },
    { field: 'Priority', value: 'Loading...', source: 'AI', editable: true },
    { field: 'Root Cause', value: 'Loading...', source: 'AI', editable: true },
    { field: 'Resolution Action', value: 'Loading...', source: 'AI', editable: true },
  ]);
  const [crmFieldsLoading, setCrmFieldsLoading] = useState(true);

  // --- Agent feedback ---
  const [agentRating, setAgentRating] = useState<'up' | 'down' | null>(null);

  // --- FCR (First Call Resolution) ---
  // Calculated from disposition code selection
  const [fcr, setFcr] = useState<boolean | null>(null);

  // Calculate FCR when disposition changes
  useEffect(() => {
    if (!selectedDisposition) {
      setFcr(null);
      return;
    }

    // Resolution dispositions (FCR = Yes)
    const resolutionDispositions = new Set([
      'RESOLVED',
      'ORDER_PLACED',
      'INFO_PROVIDED',
      'REQUEST_PROCESSED',
      'NO_ACTION_NEEDED',
    ]);

    setFcr(resolutionDispositions.has(selectedDisposition));
  }, [selectedDisposition]);

  // ACW timer — counts up every second until saved
  useEffect(() => {
    if (isSaved) return;
    const interval = setInterval(() => setAcwElapsed((e) => e + 1), 1000);
    return () => clearInterval(interval);
  }, [isSaved]);

  // Fetch AI-extracted CRM fields when ACW panel mounts
  useEffect(() => {
    const fetchCRMFields = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
        const response = await fetch(
          `${apiUrl}/api/conversations/${conversationId}/crm-fields`
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch CRM fields: ${response.status}`);
        }

        const data = await response.json();

        // Validate and map API response to CRM field format
        if (!data.fields || !Array.isArray(data.fields)) {
          throw new Error('Invalid API response: expected fields array');
        }

        const extractedFields: CRMField[] = data.fields
          .filter((field: any) =>
            field &&
            typeof field === 'object' &&
            typeof field.field_name === 'string' &&
            typeof field.value === 'string'
          )
          .map((field: any) => ({
            field: field.field_name,
            value: field.value,
            source: 'AI',
            editable: true,
            confidence: typeof field.confidence === 'number' ? field.confidence : 0,
          }));

        setCrmFields(extractedFields);
        setCrmFieldsLoading(false);
      } catch (error) {
        console.error('[ACWPanel] Failed to fetch CRM fields:', error);
        // Fallback to placeholder values
        setCrmFields([
          { field: 'Case Subject', value: '[Failed to load]', source: 'AI', editable: true },
          { field: 'Case Type', value: '[Failed to load]', source: 'AI', editable: true },
          { field: 'Priority', value: '[Failed to load]', source: 'AI', editable: true },
          { field: 'Root Cause', value: '[Failed to load]', source: 'AI', editable: true },
          { field: 'Resolution Action', value: '[Failed to load]', source: 'AI', editable: true },
        ]);
        setCrmFieldsLoading(false);
      }
    };

    fetchCRMFields();
  }, [conversationId]);

  // Fetch AI-generated disposition suggestions when ACW panel mounts
  useEffect(() => {
    const fetchDispositionSuggestions = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
        const response = await fetch(
          `${apiUrl}/api/conversations/${conversationId}/disposition-suggestions`
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch disposition suggestions: ${response.status}`);
        }

        const data = await response.json();

        // Validate and update suggestions with AI-generated values
        if (!data.suggestions || !Array.isArray(data.suggestions)) {
          throw new Error('Invalid API response: expected suggestions array');
        }

        const validSuggestions = data.suggestions
          .filter((s: any) =>
            s &&
            typeof s === 'object' &&
            typeof s.code === 'string' &&
            typeof s.label === 'string'
          )
          .map((s: any) => ({
            code: s.code,
            label: s.label,
            confidence: typeof s.confidence === 'number' ? s.confidence : 0,
          }));

        setDispositionSuggestions(validSuggestions);
        setDispositionLoading(false);

        console.log('[ACWPanel] Disposition suggestions loaded', {
          count: data.suggestions.length,
          top_suggestion: data.suggestions[0]?.code,
        });
      } catch (error) {
        console.error('[ACWPanel] Failed to fetch disposition suggestions:', error);
        // Fallback to generic suggestions
        setDispositionSuggestions([
          { code: 'RESOLVED', label: 'Issue Resolved', confidence: 0 },
          { code: 'ESCALATED', label: 'Escalated', confidence: 0 },
          { code: 'FOLLOWUP', label: 'Follow-Up Required', confidence: 0 },
        ]);
        setDispositionLoading(false);
      }
    };

    fetchDispositionSuggestions();
  }, [conversationId]);

  // Fetch AI-detected compliance items when ACW panel mounts
  useEffect(() => {
    const fetchComplianceDetection = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
        const response = await fetch(
          `${apiUrl}/api/conversations/${conversationId}/compliance-check`
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch compliance detection: ${response.status}`);
        }

        const data = await response.json();

        // Validate API response
        if (!data.items || !Array.isArray(data.items)) {
          throw new Error('Invalid API response: expected items array');
        }

        // Update checklist with AI-detected items
        setChecklist((prevChecklist) =>
          prevChecklist.map((item) => {
            // Find matching AI detection by label
            const aiDetection = data.items.find(
              (detected: any) =>
                detected &&
                typeof detected === 'object' &&
                detected.label === item.label
            );

            if (
              aiDetection &&
              typeof aiDetection.detected === 'boolean' &&
              aiDetection.detected
            ) {
              // Validate confidence is a number
              const confidence =
                typeof aiDetection.confidence === 'number'
                  ? aiDetection.confidence
                  : 0;

              // Auto-check items detected by AI with high confidence
              return {
                ...item,
                done: confidence > 0.7, // Auto-check if confidence > 70%
                auto: true, // Mark as auto-detected
              };
            }

            return item;
          })
        );

        console.log('[ACWPanel] Compliance detection completed', {
          detected_count: data.items.filter((i: any) => i.detected).length,
          total_items: data.items.length,
        });
      } catch (error) {
        console.error('[ACWPanel] Failed to fetch compliance detection:', error);
        // Keep default checklist state (all unchecked)
      }
    };

    fetchComplianceDetection();
  }, [conversationId]);

  const handleSave = useCallback(async () => {
    setIsSaving(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';

      // Prepare ACW data payload
      const acwData = {
        disposition_code: selectedDisposition || undefined,
        wrap_up_notes: wrapUpNotes || undefined,
        agent_feedback: agentRating || undefined,
        acw_duration_secs: acwElapsed,
        compliance_checklist: checklist.map((item) => ({
          label: item.label,
          checked: item.done,
          auto_detected: item.auto,
        })),
        // CRM fields are placeholder values for now, will be populated by Phase 3
        crm_fields: crmFields
          .filter((field) => field.value !== '[AI-generated — not yet implemented]')
          .map((field) => ({
            field_name: field.field,
            extracted_value: field.value,
            source: field.source,
            confidence: field.source === 'AI' ? 0.85 : 1.0,
          })),
      };

      const response = await fetch(
        `${apiUrl}/api/conversations/${conversationId}/complete`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(acwData),
        }
      );

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Failed to complete conversation: ${response.status} - ${error}`);
      }

      // Success
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
        fcr,
      });
    } catch (error) {
      console.error('[ACWPanel] Save failed:', error);
      setIsSaving(false);
      // TODO: Show error notification to user
      alert(`Failed to save ACW data: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }, [
    conversationId,
    wrapUpNotes,
    selectedDisposition,
    checklist,
    agentRating,
    acwElapsed,
    crmFields,
    onComplete,
  ]);

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
              <StructuredSummary summaryText={finalSummary || 'No summary was generated during this call.'} />
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
                {!isSaved && !isEditingNotes && (
                  <button
                    onClick={() => setIsEditingNotes(true)}
                    style={styles.editButton}
                  >
                    Edit
                  </button>
                )}
                {isEditingNotes && (
                  <button
                    onClick={() => setIsEditingNotes(false)}
                    style={styles.editButton}
                  >
                    Done Editing
                  </button>
                )}
              </div>
              {isEditingNotes ? (
                // Edit mode: textarea
                <>
                  <textarea
                    value={wrapUpNotes}
                    onChange={(e) => setWrapUpNotes(e.target.value)}
                    style={styles.textarea}
                    autoFocus
                  />
                  <div style={styles.charCount}>
                    AI-drafted · {wrapUpNotes.length} chars
                  </div>
                </>
              ) : (
                // View mode: formatted markdown
                <div style={styles.readOnlyNotes}>
                  <StructuredSummary summaryText={wrapUpNotes || 'No wrap-up notes added.'} />
                </div>
              )}
            </div>

            {/* Disposition Code Picker */}
            <div style={styles.section}>
              <div style={styles.sectionHeader}>
                <span style={styles.sectionTitle}>Disposition Code</span>
                {dispositionLoading && (
                  <span style={{ ...styles.placeholderBadge, backgroundColor: colors.info }}>
                    AI analyzing...
                  </span>
                )}
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
                {crmFieldsLoading && (
                  <span style={{ ...styles.placeholderBadge, backgroundColor: colors.info }}>
                    AI extracting...
                  </span>
                )}
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
              </div>
              {/* FCR calculated from disposition; Hold/Transfers/Sentiment require telephony integration */}
              <div style={styles.metricsGrid}>
                {[
                  ['Handle Time', callMeta.duration],
                  ['Hold Time', '-PLACEHOLDER-'],
                  ['Transfers', '-PLACEHOLDER-'],
                  ['Sentiment', '-PLACEHOLDER-'],
                  ['FCR', fcr === null ? '-PENDING-' : fcr ? 'Yes' : 'No'],
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
    padding: '2px 8px',
    borderRadius: borderRadius.full,
    color: colors.surface,
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
  readOnlyNotes: {
    padding: spacing.sm,
    backgroundColor: colors.background,
    borderRadius: borderRadius.sm,
    borderLeft: `3px solid ${colors.primary}`,
  },
  editButton: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.medium,
    color: colors.primary,
    backgroundColor: 'transparent',
    border: `1px solid ${colors.primary}`,
    padding: '4px 12px',
    borderRadius: borderRadius.sm,
    cursor: 'pointer',
    transition: 'all 0.15s',
    ':hover': {
      backgroundColor: `${colors.primary}10`,
    },
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
