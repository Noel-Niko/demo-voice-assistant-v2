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