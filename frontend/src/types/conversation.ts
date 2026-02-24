/**
 * TypeScript types for API responses
 * Maps to backend Pydantic schemas
 */

export interface TranscriptLine {
  line_id: string;
  timestamp: string;
  speaker: 'agent' | 'customer' | 'unknown';
  text: string;
  sequence_number: number;
  is_final: boolean;
}

export interface Summary {
  version: number;
  summary_text: string;
  transcript_line_count: number;
  generated_at: string;
}

export interface ConversationCreateResponse {
  conversation_id: string;
  status: 'active' | 'completed';
  started_at: string;
}

export interface ConversationStateResponse {
  conversation_id: string;
  status: 'active' | 'completed';
  started_at: string;
  ended_at: string | null;
  transcript_lines: TranscriptLine[];
  summaries: Summary[];
}

export interface HealthCheckResponse {
  status: 'healthy' | 'unhealthy';
  timestamp: string;
}

export interface ApiError {
  detail: string;
}

export type CallPhase = 'active' | 'acw';

export interface CallerInfo {
  customerName: string;
  company: string;
  accountNumber: string;
  tier: string;
}

export interface CallMeta {
  interactionId: string;
  channel: string;
  queue: string;
  startTime: string;
  duration: string;
  agent: string;
}

export interface InteractionHistoryItem {
  date: string;
  subject: string;
  channel: string;
  resolution: string;
}

export interface DispositionSuggestion {
  code: string;
  label: string;
  confidence: number;
}

export interface ComplianceCheckItem {
  id: number;
  label: string;
  done: boolean;
  auto: boolean;
}

export interface CRMField {
  field: string;
  value: string;
  source: 'AI' | 'Transcript';
  editable: boolean;
  confidence?: number; // AI confidence score (0.0 to 1.0)
}

// ===== Model Selection Types =====

export interface ModelPreset {
  model_id: string;
  model_name: string;
  display_name: string;
  reasoning_effort: string | null;
  description: string;
}

export interface ModelConfigResponse {
  current_model_id: string;
  current: ModelPreset;
  available: ModelPreset[];
}

export interface ACWState {
  wrapUpNotes: string;
  selectedDisposition: string | null;
  checklist: ComplianceCheckItem[];
  agentRating: 'up' | 'down' | null;
  isSaving: boolean;
  isSaved: boolean;
  acwElapsedSeconds: number;
  fcr?: boolean | null;  // First Call Resolution calculated from disposition
}
