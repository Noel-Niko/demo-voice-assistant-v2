/**
 * Unit tests for ConnectionStatus component
 *
 * Tests state-driven rendering and reconnection button
 */

import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ConnectionStatus from '../ConnectionStatus';
import { WebSocketConnectionState } from '@/types/websocket';

describe('ConnectionStatus', () => {
  test('renders "Connected" state', () => {
    render(<ConnectionStatus state="connected" />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  test('renders "Connecting..." state', () => {
    render(<ConnectionStatus state="connecting" />);
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  test('renders "Reconnecting..." state', () => {
    render(<ConnectionStatus state="reconnecting" />);
    expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
  });

  test('renders "Disconnected" state', () => {
    render(<ConnectionStatus state="disconnected" />);
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
  });

  test('does not show reconnect button when connected', () => {
    render(<ConnectionStatus state="connected" onReconnect={vi.fn()} />);
    expect(screen.queryByText('Reconnect')).not.toBeInTheDocument();
  });

  test('does not show reconnect button when connecting', () => {
    render(<ConnectionStatus state="connecting" onReconnect={vi.fn()} />);
    expect(screen.queryByText('Reconnect')).not.toBeInTheDocument();
  });

  test('does not show reconnect button when reconnecting', () => {
    render(<ConnectionStatus state="reconnecting" onReconnect={vi.fn()} />);
    expect(screen.queryByText('Reconnect')).not.toBeInTheDocument();
  });

  test('shows reconnect button when disconnected', () => {
    render(<ConnectionStatus state="disconnected" onReconnect={vi.fn()} />);
    expect(screen.getByText('Reconnect')).toBeInTheDocument();
  });

  test('does not show reconnect button when disconnected but no onReconnect callback', () => {
    render(<ConnectionStatus state="disconnected" />);
    expect(screen.queryByText('Reconnect')).not.toBeInTheDocument();
  });

  test('calls onReconnect when reconnect button clicked', () => {
    const onReconnect = vi.fn();
    render(<ConnectionStatus state="disconnected" onReconnect={onReconnect} />);

    const reconnectButton = screen.getByText('Reconnect');
    fireEvent.click(reconnectButton);

    expect(onReconnect).toHaveBeenCalledTimes(1);
  });

  test('reconnect button can be clicked multiple times', () => {
    const onReconnect = vi.fn();
    render(<ConnectionStatus state="disconnected" onReconnect={onReconnect} />);

    const reconnectButton = screen.getByText('Reconnect');
    fireEvent.click(reconnectButton);
    fireEvent.click(reconnectButton);
    fireEvent.click(reconnectButton);

    expect(onReconnect).toHaveBeenCalledTimes(3);
  });

  test('renders status indicator dot', () => {
    const { container } = render(<ConnectionStatus state="connected" />);

    // Status dot should be rendered (has borderRadius style)
    const dots = container.querySelectorAll('[style*="10px"]');
    expect(dots.length).toBeGreaterThan(0);
  });

  test('state transitions update text correctly', () => {
    const { rerender } = render(<ConnectionStatus state="disconnected" />);
    expect(screen.getByText('Disconnected')).toBeInTheDocument();

    rerender(<ConnectionStatus state="connecting" />);
    expect(screen.getByText('Connecting...')).toBeInTheDocument();

    rerender(<ConnectionStatus state="connected" />);
    expect(screen.getByText('Connected')).toBeInTheDocument();

    rerender(<ConnectionStatus state="reconnecting" />);
    expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
  });

  test('reconnect button appears/disappears based on state', () => {
    const onReconnect = vi.fn();
    const { rerender } = render(<ConnectionStatus state="connected" onReconnect={onReconnect} />);
    expect(screen.queryByText('Reconnect')).not.toBeInTheDocument();

    rerender(<ConnectionStatus state="disconnected" onReconnect={onReconnect} />);
    expect(screen.getByText('Reconnect')).toBeInTheDocument();

    rerender(<ConnectionStatus state="connecting" onReconnect={onReconnect} />);
    expect(screen.queryByText('Reconnect')).not.toBeInTheDocument();
  });
});
