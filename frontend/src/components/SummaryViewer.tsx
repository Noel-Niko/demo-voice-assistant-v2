/**
 * Summary Viewer Component
 *
 * Displays AI-generated summaries with:
 * - Typewriter effect for streaming tokens
 * - Version history
 * - Copy to clipboard functionality
 * - Loading states
 */

import { useState, useEffect } from 'react';
import { Summary } from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/design-tokens';
import StructuredSummary from '@/components/StructuredSummary';

interface SummaryViewerProps {
  summaries: Summary[];
  currentSummary?: string;
  isGenerating?: boolean;
  currentVersion?: number;
  conversationId?: string | null;
}

export default function SummaryViewer({
  summaries,
  currentSummary = '',
  isGenerating = false,
  currentVersion,
  conversationId,
}: SummaryViewerProps) {
  const [copiedVersion, setCopiedVersion] = useState<number | null>(null);
  const [summaryInterval, setSummaryInterval] = useState(30); // Default 30 seconds
  const [displayedSummary, setDisplayedSummary] = useState('');

  // Fetch summary interval from API when conversation is created
  useEffect(() => {
    if (conversationId) {
      const fetchSummaryInterval = async () => {
        try {
          const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
          const response = await fetch(`${apiUrl}/api/conversations/${conversationId}`);

          if (response.ok) {
            const data = await response.json();
            if (data.summary_interval) {
              // Validate interval is a number within acceptable range
              const interval = parseInt(data.summary_interval, 10);
              if (!isNaN(interval) && interval >= 5 && interval <= 120) {
                setSummaryInterval(interval);
                console.log(`[UI] Loaded summary interval from API: ${interval}s`);
              } else {
                console.warn(`[UI] Invalid summary_interval from API: ${data.summary_interval}, using default`);
              }
            }
          } else {
            console.error('[UI] Failed to fetch conversation state:', response.status);
          }
        } catch (error) {
          console.error('[UI] Error fetching conversation state:', error);
        }
      };

      fetchSummaryInterval();
    }
  }, [conversationId]);

  // Keep previous summary visible while generating, only update when new content arrives
  useEffect(() => {
    if (currentSummary && currentSummary.trim().length > 0) {
      setDisplayedSummary(currentSummary);
    }
  }, [currentSummary]);

  const handleIntervalChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const newInterval = parseInt(e.target.value, 10);
    setSummaryInterval(newInterval);

    // Update backend interval
    if (conversationId) {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
        const response = await fetch(
          `${apiUrl}/api/conversations/${conversationId}/summary-interval?interval_seconds=${newInterval}`,
          { method: 'PUT' }
        );

        if (response.ok) {
          const data = await response.json();
          console.log(`[UI] Summary interval updated:`, data);
        } else {
          console.error('[UI] Failed to update interval:', response.status);
        }
      } catch (error) {
        console.error('[UI] Error updating interval:', error);
      }
    }
  };

  const handleCopy = async (text: string, version: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedVersion(version);
      setTimeout(() => setCopiedVersion(null), 2000);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.headerTop}>
          <h2 style={styles.title}>AI Summary</h2>
          {isGenerating && (
            <span style={styles.generatingBadge}>Generating...</span>
          )}
          {!isGenerating && currentSummary && (
            <button
              onClick={() => handleCopy(currentSummary, currentVersion || 0)}
              style={styles.copyButtonHeader}
              title="Copy to clipboard"
            >
              {copiedVersion === (currentVersion || 0) ? '✓ Copied' : '📋 Copy'}
            </button>
          )}
        </div>

        {/* Summary Frequency Control - Compact single line */}
        <div style={styles.intervalControl}>
          <span style={styles.intervalLabel}>
            Frequency: <strong>{summaryInterval}s</strong>
          </span>
          <span style={styles.sliderMin}>5s</span>
          <input
            type="range"
            min="5"
            max="120"
            step="5"
            value={summaryInterval}
            onChange={handleIntervalChange}
            style={styles.slider}
            title={`Generate summary every ${summaryInterval} seconds`}
          />
          <span style={styles.sliderMax}>120s</span>
        </div>
      </div>

      <div style={styles.summaryContainer}>
        {/* Single Summary with Fade-In Updates */}
        <div style={styles.currentSummaryText}>
          <StructuredSummary
            summaryText={
              displayedSummary ||
              'Waiting for conversation to begin... \nFirst summary will generate after the configured frequency interval of conversation.'
            }
            isGenerating={isGenerating}
          />
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    boxShadow: shadows.base,
    overflow: 'hidden',
    flexShrink: 0,
  },
  header: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
    padding: spacing.md,
    borderBottom: `1px solid ${colors.border}`,
    backgroundColor: colors.surface,
  },
  headerTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    fontSize: typography.fontSize.lg,
    fontWeight: typography.fontWeight.semibold,
    color: colors.text,
    margin: 0,
  },
  intervalControl: {
    display: 'flex',
    flexDirection: 'row' as const,
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.sm,
    backgroundColor: colors.background,
    borderRadius: borderRadius.sm,
    border: `1px solid ${colors.borderLight}`,
  },
  intervalLabel: {
    fontSize: typography.fontSize.sm,
    color: colors.text,
    whiteSpace: 'nowrap' as const,
    marginRight: spacing.xs,
  },
  slider: {
    flex: 1,
    height: '6px',
    borderRadius: borderRadius.sm,
    outline: 'none',
    cursor: 'pointer',
  },
  sliderMin: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    minWidth: '25px',
  },
  sliderMax: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    minWidth: '35px',
  },
  generatingBadge: {
    fontSize: typography.fontSize.sm,
    color: colors.primary,
    fontWeight: typography.fontWeight.medium,
  },
  copyButtonHeader: {
    fontSize: typography.fontSize.xs,
    color: colors.info,
    backgroundColor: 'transparent',
    border: `1px solid ${colors.info}`,
    borderRadius: borderRadius.sm,
    padding: '4px 12px',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  summaryContainer: {
    padding: spacing.md,
    backgroundColor: colors.background,
    // No overflow - all content visible
  },
  currentSummaryText: {
    fontSize: typography.fontSize.base,
    color: colors.text,
    lineHeight: typography.lineHeight.relaxed,
    whiteSpace: 'normal' as const,  // Collapses excessive whitespace/newlines
    wordWrap: 'break-word' as const,
  },
};
