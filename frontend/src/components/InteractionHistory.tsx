/**
 * Interaction History — Left Panel (active call only)
 *
 * Shows recent past interactions for the current customer.
 * Hidden during ACW to compact the left panel.
 */

import { useState } from 'react';
import { InteractionHistoryItem } from '@/types/conversation';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/design-tokens';

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
