/**
 * Simplified unit tests for useWebSocket hook
 *
 * Tests core WebSocket functionality without complex async timing issues
 */

import { describe, test, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWebSocket } from '../useWebSocket';

describe('useWebSocket - Core Functionality', () => {
  test('initializes with disconnected state when no conversationId', () => {
    const { result } = renderHook(() => useWebSocket(null));

    expect(result.current.connectionState).toBe('disconnected');
    expect(result.current.disconnect).toBeTypeOf('function');
    expect(result.current.reconnect).toBeTypeOf('function');
  });

  test('provides disconnect and reconnect functions', () => {
    const { result } = renderHook(() => useWebSocket(null));

    expect(result.current).toHaveProperty('disconnect');
    expect(result.current).toHaveProperty('reconnect');
    expect(result.current).toHaveProperty('connectionState');
  });

  test('accepts WebSocket hook options', () => {
    const mockHandlers = {
      onConnectionChange: () => {},
      onWordInterim: () => {},
      onWordFinal: () => {},
      onSummaryStart: () => {},
      onSummaryToken: () => {},
      onSummaryComplete: () => {},
      reconnectDelay: 2000,
      maxReconnectDelay: 60000,
    };

    const { result } = renderHook(() => useWebSocket(null, mockHandlers));

    // Should initialize without errors
    expect(result.current.connectionState).toBe('disconnected');
  });

  test('accepts custom reconnect delays', () => {
    const { result } = renderHook(() =>
      useWebSocket(null, {
        reconnectDelay: 5000,
        maxReconnectDelay: 120000,
      })
    );

    expect(result.current.connectionState).toBe('disconnected');
  });

  test('handles all event handler options', () => {
    const handlers = {
      onConnectionChange: () => {},
      onWordInterim: () => {},
      onWordFinal: () => {},
      onSummaryStart: () => {},
      onSummaryToken: () => {},
      onSummaryComplete: () => {},
      onStreamingComplete: () => {},
      onListeningModeSessionStarted: () => {},
      onListeningModeSessionEnded: () => {},
      onListeningModeOpportunityDetected: () => {},
      onListeningModeQueryStarted: () => {},
      onListeningModeQueryComplete: () => {},
      onListeningModeQueryError: () => {},
    };

    const { result } = renderHook(() => useWebSocket(null, handlers));

    // Should accept all handlers without errors
    expect(result.current).toBeDefined();
  });
});
