/**
 * Transcript Viewer Component
 *
 * Displays streaming transcript lines with:
 * - Newest messages at TOP (reverse chronological order)
 * - Color-coded speakers (agent=blue, customer=green)
 * - Timestamp display
 * - Loading states
 * - Interim line visual treatment (reduced opacity, blinking cursor)
 * - Manual scroll (no auto-scroll)
 */

import { useState, useEffect, useRef } from 'react';
import { TranscriptLine } from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/grainger-tokens';

interface TranscriptViewerProps {
  lines: TranscriptLine[];
  isLoading?: boolean;
}

function BlinkingCursor() {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible((v) => !v);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  return (
    <span style={{ opacity: visible ? 1 : 0, color: colors.info, fontWeight: 'bold' }}>
      |
    </span>
  );
}

export default function TranscriptViewer({ lines, isLoading = false }: TranscriptViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const getSpeakerColor = (speaker: string): string => {
    switch (speaker.toLowerCase()) {
      case 'agent':
        return colors.agent;
      case 'customer':
        return colors.customer;
      default:
        return colors.unknown;
    }
  };

  const formatTimestamp = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return timestamp;
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h2 style={styles.title}>Transcript</h2>
        {isLoading && <span style={styles.loadingBadge}>Streaming...</span>}
      </div>

      <div
        ref={containerRef}
        style={styles.transcriptContainer}
      >
        {lines.length === 0 && !isLoading && (
          <div style={styles.emptyState}>
            <p>No transcript lines yet.</p>
            <p style={styles.emptyStateSubtext}>Waiting for conversation to start...</p>
          </div>
        )}

        {/* Reverse order: newest messages at TOP */}
        {[...lines].reverse().map((line) => (
          <div
            key={line.line_id}
            style={{
              ...styles.transcriptLine,
              opacity: line.is_final ? 1 : 0.7,
              borderLeftColor: line.is_final
                ? getSpeakerColor(line.speaker)
                : colors.info,
            }}
          >
            <div style={styles.lineHeader}>
              <span
                style={{
                  ...styles.speaker,
                  color: getSpeakerColor(line.speaker),
                }}
              >
                {line.speaker.toUpperCase()}
              </span>
              <span style={styles.timestamp}>
                {formatTimestamp(line.timestamp)}
              </span>
            </div>
            <div style={styles.lineText}>
              {line.text}
              {!line.is_final && (
                <>
                  {' '}
                  <BlinkingCursor />
                </>
              )}
            </div>
          </div>
        ))}

        {isLoading && lines.length > 0 && (
          <div style={styles.streamingIndicator}>
            <div style={styles.dot}></div>
            <div style={styles.dot}></div>
            <div style={styles.dot}></div>
          </div>
        )}
      </div>
    </div>
  );
}

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
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing.md,
    borderBottom: `1px solid ${colors.border}`,
    backgroundColor: colors.surface,
  },
  title: {
    fontSize: typography.fontSize.lg,
    fontWeight: typography.fontWeight.semibold,
    color: colors.text,
    margin: 0,
  },
  loadingBadge: {
    fontSize: typography.fontSize.sm,
    color: colors.info,
    fontWeight: typography.fontWeight.medium,
  },
  transcriptContainer: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: spacing.md,
    backgroundColor: colors.background,
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: colors.textLight,
    textAlign: 'center' as const,
  },
  emptyStateSubtext: {
    fontSize: typography.fontSize.sm,
    marginTop: spacing.sm,
  },
  transcriptLine: {
    marginBottom: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.sm,
    borderLeft: `3px solid ${colors.borderLight}`,
    transition: 'opacity 0.2s ease',
  },
  lineHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  speaker: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.bold,
    letterSpacing: '0.5px',
  },
  timestamp: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    fontFamily: typography.fontFamily.mono,
  },
  lineText: {
    fontSize: typography.fontSize.base,
    color: colors.text,
    lineHeight: typography.lineHeight.relaxed,
    whiteSpace: 'pre-wrap' as const,
    wordWrap: 'break-word' as const,
  },
  streamingIndicator: {
    display: 'flex',
    gap: spacing.sm,
    justifyContent: 'center',
    padding: spacing.md,
  },
  dot: {
    width: '8px',
    height: '8px',
    backgroundColor: colors.info,
    borderRadius: borderRadius.full,
    animation: 'pulse 1.5s ease-in-out infinite',
  },
};
