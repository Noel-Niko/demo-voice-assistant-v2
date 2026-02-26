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

import {useCallback, useEffect, useRef, useState} from 'react';
import TranscriptViewer from '@/components/TranscriptViewer';
import SummaryViewer from '@/components/SummaryViewer';
import ConnectionStatus from '@/components/ConnectionStatus';
import MCPSuggestionsBox from '@/components/MCPSuggestionsBox';
import CallerInfoCard from '@/components/CallerInfoCard';
import CallMetaCard from '@/components/CallMetaCard';
import InteractionHistory from '@/components/InteractionHistory';
import ACWPanel from '@/components/ACWPanel';
import ModelSelector from '@/components/ModelSelector';
import {ResizeHandle} from '@/components/ResizeHandle';
import {useWebSocket} from '@/hooks/useWebSocket';
import {useTranscriptStream} from '@/hooks/useTranscriptStream';
import {
  ACWState,
  CallerInfo,
  CallMeta,
  CallPhase,
  ConversationCreateResponse,
  InteractionHistoryItem,
  Summary,
} from '@/types/conversation';
import {colors, spacing, typography} from '@/styles/design-tokens';

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

// Initial call meta without time (calculated after mount to prevent hydration mismatch)
const INITIAL_CALL_META: CallMeta = {
  interactionId: 'INT-2026-4829',
  channel: 'Voice',
  queue: 'Industrial MRO — Orders & Returns',
  startTime: '--:--', // Will be set after mount
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
  const [autoQueryData, setAutoQueryData] = useState<any>(null);

  // Transcript stream state (word-by-word) — preserved from word-streaming refactor
  const { transcriptLines, handleWordInterim, handleWordFinal } = useTranscriptStream();

  // Track transcript line count without triggering callback recreations
  const transcriptLineCountRef = useRef(0);

  // ── Call meta state (startTime set after mount to prevent hydration mismatch) ──
  const [callMeta, setCallMeta] = useState<CallMeta>(INITIAL_CALL_META);

  // ── Resize state and constants ──
  const MIN_RIGHT_PANEL_WIDTH = 280; // Minimum usable width
  const MAX_RIGHT_PANEL_WIDTH = 800; // Maximum before it becomes unwieldy
  const DEFAULT_ACTIVE_WIDTH = 340; // Default for active call phase
  const DEFAULT_ACW_WIDTH = 500; // Default for ACW phase (25% increase from original 400px)

  const [rightPanelWidth, setRightPanelWidth] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragStateRef = useRef<{
    startX: number;
    startWidth: number;
    currentWidth: number;
  } | null>(null);

  // Sync ref with transcript line count
  useEffect(() => {
    transcriptLineCountRef.current = transcriptLines.length;
  }, [transcriptLines.length]);

  // Set startTime after mount (client-side only)
  useEffect(() => {
    setCallMeta((prev) => ({
      ...prev,
      startTime: new Date().toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
      }),
    }));
  }, []);

  // DEBUG: Log when component renders (for WebSocket debugging)
  useEffect(() => {
    console.log('[PAGE] Component rendered/re-rendered');
  });

  // ── Load saved panel width from localStorage ──
  useEffect(() => {
    const storageKey =
      callPhase === 'active'
        ? 'callmate_rightPanel_activeWidth'
        : 'callmate_rightPanel_acwWidth';

    try {
      const savedWidth = localStorage.getItem(storageKey);
      if (savedWidth) {
        const width = parseInt(savedWidth, 10);
        if (
          !isNaN(width) &&
          width >= MIN_RIGHT_PANEL_WIDTH &&
          width <= MAX_RIGHT_PANEL_WIDTH
        ) {
          setRightPanelWidth(width);
          return;
        }
      }
    } catch (e) {
      // localStorage may be disabled or unavailable
      console.warn('Failed to load panel width from localStorage:', e);
    }

    // Use defaults if no saved width or invalid
    setRightPanelWidth(
      callPhase === 'active' ? DEFAULT_ACTIVE_WIDTH : DEFAULT_ACW_WIDTH
    );
  }, [callPhase, MIN_RIGHT_PANEL_WIDTH, MAX_RIGHT_PANEL_WIDTH, DEFAULT_ACTIVE_WIDTH, DEFAULT_ACW_WIDTH]);

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
          transcript_line_count: transcriptLineCountRef.current,
          generated_at: new Date().toISOString(),
        },
      ]);
    },
    []
  );

  const handleStreamingComplete = useCallback(() => {
    console.log('Transcript streaming complete');
    setIsLoading(false);
  }, []);

  const handleListeningModeQueryComplete = useCallback((data: any) => {
    console.log('[Page] Auto-query complete received:', data);
    setAutoQueryData(data);
  }, []);

  // Initialize WebSocket — uses word-streaming callbacks
  const { connectionState, reconnect } = useWebSocket(conversationId, {
    onWordInterim: handleWordInterim,
    onWordFinal: handleWordFinal,
    onSummaryStart: handleSummaryStart,
    onSummaryToken: handleSummaryToken,
    onSummaryComplete: handleSummaryComplete,
    onStreamingComplete: handleStreamingComplete,
    onListeningModeQueryComplete: handleListeningModeQueryComplete,
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

  // ── Drag handlers for panel resize ──
  const handleResizeMove = useCallback((e: MouseEvent) => {
    if (!dragStateRef.current) return;

    const { startX, startWidth } = dragStateRef.current;
    const deltaX = startX - e.clientX; // Negative deltaX = dragging right (wider)
    const newWidth = Math.max(
      MIN_RIGHT_PANEL_WIDTH,
      Math.min(MAX_RIGHT_PANEL_WIDTH, startWidth + deltaX)
    );

    dragStateRef.current.currentWidth = newWidth;
    setRightPanelWidth(newWidth);
  }, [MIN_RIGHT_PANEL_WIDTH, MAX_RIGHT_PANEL_WIDTH]);

  const handleResizeEnd = useCallback(() => {
    setIsDragging(false);

    // Remove global listeners
    document.removeEventListener('mousemove', handleResizeMove);
    document.removeEventListener('mouseup', handleResizeEnd);

    // Restore default cursor
    document.body.style.userSelect = '';
    document.body.style.cursor = '';

    // Save to localStorage
    if (dragStateRef.current) {
      const storageKey =
        callPhase === 'active'
          ? 'callmate_rightPanel_activeWidth'
          : 'callmate_rightPanel_acwWidth';

      try {
        localStorage.setItem(
          storageKey,
          dragStateRef.current.currentWidth.toString()
        );
      } catch (e) {
        console.warn('Failed to save panel width to localStorage:', e);
      }
    }

    dragStateRef.current = null;
  }, [callPhase, handleResizeMove]);

  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);

      dragStateRef.current = {
        startX: e.clientX,
        startWidth:
          rightPanelWidth ||
          (callPhase === 'active' ? DEFAULT_ACTIVE_WIDTH : DEFAULT_ACW_WIDTH),
        currentWidth:
          rightPanelWidth ||
          (callPhase === 'active' ? DEFAULT_ACTIVE_WIDTH : DEFAULT_ACW_WIDTH),
      };

      // Add global listeners for smooth dragging
      document.addEventListener('mousemove', handleResizeMove);
      document.addEventListener('mouseup', handleResizeEnd);

      // Prevent text selection during drag
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    },
    [
      rightPanelWidth,
      callPhase,
      DEFAULT_ACTIVE_WIDTH,
      DEFAULT_ACW_WIDTH,
      handleResizeMove,
      handleResizeEnd,
    ]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleResizeMove);
      document.removeEventListener('mouseup', handleResizeEnd);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [handleResizeMove, handleResizeEnd]);

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

  // ── Determine grid columns based on call phase and user resize preference ──
  const currentWidth =
    rightPanelWidth ||
    (callPhase === 'active' ? DEFAULT_ACTIVE_WIDTH : DEFAULT_ACW_WIDTH);
  const gridColumns = `240px 1fr ${currentWidth}px`;

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
            <ModelSelector />
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
                meta={{ ...callMeta, duration: formattedDuration }}
              />
              <InteractionHistory history={DEMO_HISTORY} />
            </>
          )}
        </div>

        {/* ── CENTER PANEL (always the same) ── */}
        <div style={styles.centerPanel}>
          <TranscriptViewer lines={transcriptLines} isLoading={isLoading} />
        </div>

        {/* ── RIGHT PANEL (phase-driven, resizable) ── */}
        <div style={{ ...styles.rightPanel, position: 'relative' }}>
          <ResizeHandle
            onMouseDown={handleResizeStart}
            isDragging={isDragging}
          />
          {callPhase === 'active' ? (
            <>
              <MCPSuggestionsBox
                conversationId={conversationId}
                autoQueryData={autoQueryData}
              />
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
              callMeta={{ ...callMeta, duration: formattedDuration }}
              conversationId={conversationId || ''}
              onComplete={handleACWComplete}
            />
          )}
        </div>
      </div>

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
    maxHeight: 'calc(100vh)',
    overflowY: 'auto' as const,
    overflowX: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
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
