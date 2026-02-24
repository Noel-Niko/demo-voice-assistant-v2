/**
 * TypeScript types for WebSocket events
 * Maps to backend Event schema
 */

import { TranscriptLine } from './conversation';

export type WebSocketConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting';

export type WebSocketEventType =
  | 'connection.established'
  | 'transcript.word.interim'
  | 'transcript.word.final'
  | 'summary.start'
  | 'summary.token'
  | 'summary.complete'
  | 'streaming.complete'
  | 'listening_mode.session.started'
  | 'listening_mode.session.ended'
  | 'listening_mode.opportunity.detected'
  | 'listening_mode.query.started'
  | 'listening_mode.query.complete'
  | 'listening_mode.query.error'
  | 'ping';

export interface BaseWebSocketEvent {
  event_id: string;
  event_type: WebSocketEventType;
  timestamp: string;
  conversation_id: string;
  source: string;
}

export interface ConnectionEstablishedEvent extends BaseWebSocketEvent {
  event_type: 'connection.established';
  data: {
    conversation_id: string;
    message: string;
  };
}

export interface TranscriptWordInterimEvent extends BaseWebSocketEvent {
  event_type: 'transcript.word.interim';
  data: {
    conversation_id: string;
    line_id: string;
    speaker: 'agent' | 'customer' | 'unknown';
    partial_text: string;
    is_final: false;
    timestamp: string;
    sequence_number: number;
  };
}

export interface TranscriptWordFinalEvent extends BaseWebSocketEvent {
  event_type: 'transcript.word.final';
  data: {
    conversation_id: string;
    line_id: string;
    speaker: 'agent' | 'customer' | 'unknown';
    text: string;
    is_final: true;
    timestamp: string;
    sequence_number: number;
  };
}

export interface SummaryStartEvent extends BaseWebSocketEvent {
  event_type: 'summary.start';
  data: {
    conversation_id: string;
    version: number;
  };
}

export interface SummaryTokenEvent extends BaseWebSocketEvent {
  event_type: 'summary.token';
  data: {
    conversation_id: string;
    version: number;
    token: string;
  };
}

export interface SummaryCompleteEvent extends BaseWebSocketEvent {
  event_type: 'summary.complete';
  data: {
    conversation_id: string;
    version: number;
    summary_text: string;
    transcript_line_count: number;
  };
}

export interface StreamingCompleteEvent extends BaseWebSocketEvent {
  event_type: 'streaming.complete';
  data: {
    conversation_id: string;
  };
}

export interface PingEvent {
  event_type: 'ping';
}

export interface ListeningModeSessionStartedEvent extends BaseWebSocketEvent {
  event_type: 'listening_mode.session.started';
  data: {
    session_id: number;
    conversation_id: string;
    started_at: string;
  };
}

export interface ListeningModeSessionEndedEvent extends BaseWebSocketEvent {
  event_type: 'listening_mode.session.ended';
  data: {
    session_id: number;
    conversation_id: string;
    ended_at: string;
    auto_queries_count: number;
    opportunities_detected: number;
  };
}

export interface ListeningModeOpportunityDetectedEvent extends BaseWebSocketEvent {
  event_type: 'listening_mode.opportunity.detected';
  data: {
    opportunity_type: string;
    query_text: string;
    confidence: number;
    trigger_transcript: string;
  };
}

export interface ListeningModeQueryStartedEvent extends BaseWebSocketEvent {
  event_type: 'listening_mode.query.started';
  data: {
    query_text: string;
    opportunity_type: string;
    session_id: number;
  };
}

export interface ListeningModeQueryCompleteEvent extends BaseWebSocketEvent {
  event_type: 'listening_mode.query.complete';
  data: {
    query_text: string;
    opportunity_type: string;
    session_id: number;
    result: {
      success: boolean;
      result: {
        content: Array<{
          title?: string;
          text?: string;
          content?: string;
          url?: string;
          source?: string;
          score?: number;
        }>;
      };
      server_path: string;
      tool_name: string;
    };
  };
}

export interface ListeningModeQueryErrorEvent extends BaseWebSocketEvent {
  event_type: 'listening_mode.query.error';
  data: {
    query_text: string;
    opportunity_type: string;
    session_id: number;
    error: string;
  };
}

export type WebSocketEvent =
  | ConnectionEstablishedEvent
  | TranscriptWordInterimEvent
  | TranscriptWordFinalEvent
  | SummaryStartEvent
  | SummaryTokenEvent
  | SummaryCompleteEvent
  | StreamingCompleteEvent
  | ListeningModeSessionStartedEvent
  | ListeningModeSessionEndedEvent
  | ListeningModeOpportunityDetectedEvent
  | ListeningModeQueryStartedEvent
  | ListeningModeQueryCompleteEvent
  | ListeningModeQueryErrorEvent
  | PingEvent;

export interface WebSocketHookOptions {
  onConnectionChange?: (state: WebSocketConnectionState) => void;
  onWordInterim?: (data: TranscriptWordInterimEvent['data']) => void;
  onWordFinal?: (data: TranscriptWordFinalEvent['data']) => void;
  onSummaryStart?: (version: number) => void;
  onSummaryToken?: (token: string, version: number) => void;
  onSummaryComplete?: (summaryText: string, version: number) => void;
  onStreamingComplete?: () => void;
  onListeningModeSessionStarted?: (data: ListeningModeSessionStartedEvent['data']) => void;
  onListeningModeSessionEnded?: (data: ListeningModeSessionEndedEvent['data']) => void;
  onListeningModeOpportunityDetected?: (data: ListeningModeOpportunityDetectedEvent['data']) => void;
  onListeningModeQueryStarted?: (data: ListeningModeQueryStartedEvent['data']) => void;
  onListeningModeQueryComplete?: (data: ListeningModeQueryCompleteEvent['data']) => void;
  onListeningModeQueryError?: (data: ListeningModeQueryErrorEvent['data']) => void;
  reconnectDelay?: number;
  maxReconnectDelay?: number;
}
