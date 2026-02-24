/**
 * WebSocket Custom Hook with Auto-Reconnection
 *
 * Features:
 * - Exponential backoff reconnection strategy
 * - Type-safe event handling
 * - Connection state management
 * - Automatic cleanup on unmount
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import {
  WebSocketConnectionState,
  WebSocketEvent,
  WebSocketHookOptions,
} from '@/types/websocket';

export function useWebSocket(
  conversationId: string | null,
  options: WebSocketHookOptions = {}
) {
  const {
    onConnectionChange,
    onWordInterim,
    onWordFinal,
    onSummaryStart,
    onSummaryToken,
    onSummaryComplete,
    onStreamingComplete,
    onListeningModeSessionStarted,
    onListeningModeSessionEnded,
    onListeningModeOpportunityDetected,
    onListeningModeQueryStarted,
    onListeningModeQueryComplete,
    onListeningModeQueryError,
    reconnectDelay = 1000,
    maxReconnectDelay = 30000,
  } = options;

  const [connectionState, setConnectionState] =
    useState<WebSocketConnectionState>('disconnected');

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(true);

  // Store callbacks in refs to prevent reconnections on every render
  const callbacksRef = useRef(options);
  useEffect(() => {
    callbacksRef.current = options;
  }, [options]);

  const updateConnectionState = useCallback(
    (state: WebSocketConnectionState) => {
      setConnectionState(state);
      callbacksRef.current.onConnectionChange?.(state);
    },
    [] // No dependencies - use callbacksRef instead
  );

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const wsEvent: WebSocketEvent = JSON.parse(event.data);
        const callbacks = callbacksRef.current;

        switch (wsEvent.event_type) {
          case 'connection.established':
            console.log('[WebSocket] Connection established', wsEvent.data);
            updateConnectionState('connected');
            reconnectAttemptRef.current = 0;
            break;

          case 'transcript.word.interim':
            callbacks.onWordInterim?.(wsEvent.data);
            break;

          case 'transcript.word.final':
            console.log(
              '[WebSocket] Transcript line final',
              wsEvent.data.line_id
            );
            callbacks.onWordFinal?.(wsEvent.data);
            break;

          case 'summary.start':
            console.log('[WebSocket] Summary generation started', wsEvent.data);
            callbacks.onSummaryStart?.(wsEvent.data.version);
            break;

          case 'summary.token':
            callbacks.onSummaryToken?.(wsEvent.data.token, wsEvent.data.version);
            break;

          case 'summary.complete':
            console.log('[WebSocket] Summary generation complete', wsEvent.data);
            callbacks.onSummaryComplete?.(
              wsEvent.data.summary_text,
              wsEvent.data.version
            );
            break;

          case 'streaming.complete':
            console.log('[WebSocket] Streaming complete', wsEvent.data);
            callbacks.onStreamingComplete?.();
            break;

          case 'listening_mode.session.started':
            console.log('[WebSocket] Listening mode session started', wsEvent.data);
            callbacks.onListeningModeSessionStarted?.(wsEvent.data);
            break;

          case 'listening_mode.session.ended':
            console.log('[WebSocket] Listening mode session ended', wsEvent.data);
            callbacks.onListeningModeSessionEnded?.(wsEvent.data);
            break;

          case 'listening_mode.opportunity.detected':
            console.log('[WebSocket] Opportunity detected', wsEvent.data);
            callbacks.onListeningModeOpportunityDetected?.(wsEvent.data);
            break;

          case 'listening_mode.query.started':
            console.log('[WebSocket] Auto-query started', wsEvent.data);
            callbacks.onListeningModeQueryStarted?.(wsEvent.data);
            break;

          case 'listening_mode.query.complete':
            console.log('[WebSocket] Auto-query complete', wsEvent.data);
            callbacks.onListeningModeQueryComplete?.(wsEvent.data);
            break;

          case 'listening_mode.query.error':
            console.error('[WebSocket] Auto-query error', wsEvent.data);
            callbacks.onListeningModeQueryError?.(wsEvent.data);
            break;

          case 'ping':
            break;

          default:
            console.warn('[WebSocket] Unknown event type:', wsEvent);
        }
      } catch (error) {
        console.error('[WebSocket] Failed to parse message:', error);
      }
    },
    [updateConnectionState]
  );

  const connect = useCallback(() => {
    if (!conversationId) {
      console.log('[WebSocket] No conversation ID, skipping connection');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Already connected');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[WebSocket] Connection already in progress');
      return;
    }

    try {
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765';
      const url = `${wsUrl}/api/ws/${conversationId}`;

      console.log('[WebSocket] Connecting to:', url);
      updateConnectionState(
        reconnectAttemptRef.current > 0 ? 'reconnecting' : 'connecting'
      );

      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('[WebSocket] Connection opened');
      };

      ws.onmessage = handleMessage;

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Connection closed', event.code, event.reason);
        console.trace('[WebSocket] Close stack trace');
        updateConnectionState('disconnected');

        // Clear stale reference so reconnect doesn't see dead socket
        wsRef.current = null;

        // Attempt reconnection with exponential backoff
        if (shouldReconnectRef.current) {
          const delay = Math.min(
            reconnectDelay * Math.pow(2, reconnectAttemptRef.current),
            maxReconnectDelay
          );

          console.log(
            `[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current + 1})`
          );

          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptRef.current += 1;
            connect();
          }, delay);
        }
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('[WebSocket] Connection failed:', error);
      updateConnectionState('disconnected');
    }
  }, [
    conversationId,
    handleMessage,
    reconnectDelay,
    maxReconnectDelay,
    updateConnectionState,
  ]);

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      console.log('[WebSocket] Disconnecting');
      wsRef.current.close();
      wsRef.current = null;
    }

    updateConnectionState('disconnected');
  }, [updateConnectionState]);

  // Connect when conversation ID is available
  useEffect(() => {
    if (conversationId) {
      shouldReconnectRef.current = true;
      connect();
    }

    return () => {
      disconnect();
    };
  }, [conversationId, connect, disconnect]); // Now stable since handleMessage only depends on updateConnectionState

  return {
    connectionState,
    disconnect,
    reconnect: connect,
  };
}
