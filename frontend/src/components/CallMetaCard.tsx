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
