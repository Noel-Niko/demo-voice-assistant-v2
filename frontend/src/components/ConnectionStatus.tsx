/**
 * Connection Status Component
 *
 * Displays WebSocket connection state with visual indicator
 */

import { WebSocketConnectionState } from '@/types/websocket';
import { colors, spacing, typography, borderRadius } from '@/styles/design-tokens';

interface ConnectionStatusProps {
  state: WebSocketConnectionState;
  onReconnect?: () => void;
}

export default function ConnectionStatus({ state, onReconnect }: ConnectionStatusProps) {
  const getStatusColor = (state: WebSocketConnectionState): string => {
    switch (state) {
      case 'connected':
        return colors.connected;
      case 'connecting':
      case 'reconnecting':
        return colors.connecting;
      case 'disconnected':
        return colors.disconnected;
      default:
        return colors.textLight;
    }
  };

  const getStatusText = (state: WebSocketConnectionState): string => {
    switch (state) {
      case 'connected':
        return 'Connected';
      case 'connecting':
        return 'Connecting...';
      case 'reconnecting':
        return 'Reconnecting...';
      case 'disconnected':
        return 'Disconnected';
      default:
        return 'Unknown';
    }
  };

  const statusColor = getStatusColor(state);
  const statusText = getStatusText(state);

  return (
    <div style={styles.container}>
      <div style={styles.statusIndicator}>
        <div
          style={{
            ...styles.dot,
            backgroundColor: statusColor,
          }}
        />
        <span style={styles.statusText}>{statusText}</span>
      </div>

      {state === 'disconnected' && onReconnect && (
        <button onClick={onReconnect} style={styles.reconnectButton}>
          Reconnect
        </button>
      )}
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.sm,
  },
  statusIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  dot: {
    width: '10px',
    height: '10px',
    borderRadius: borderRadius.full,
    flexShrink: 0,
  },
  statusText: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.medium,
    color: colors.text,
  },
  reconnectButton: {
    fontSize: typography.fontSize.sm,
    color: colors.info,
    backgroundColor: 'transparent',
    border: `1px solid ${colors.info}`,
    borderRadius: borderRadius.sm,
    padding: '4px 12px',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
};
