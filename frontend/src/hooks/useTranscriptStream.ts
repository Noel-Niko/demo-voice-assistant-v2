/**
 * Transcript Stream Hook
 *
 * Manages transcript state from word-by-word streaming events.
 * Uses a Map keyed by line_id for O(1) upserts of interim/final updates.
 * Derives a sorted array for rendering.
 */

import { useState, useCallback, useMemo, useRef } from 'react';
import { TranscriptLine } from '@/types/conversation';
import {
  TranscriptWordInterimEvent,
  TranscriptWordFinalEvent,
} from '@/types/websocket';

export function useTranscriptStream() {
  const linesMapRef = useRef<Map<string, TranscriptLine>>(new Map());
  const [version, setVersion] = useState(0);

  const handleWordInterim = useCallback(
    (data: TranscriptWordInterimEvent['data']) => {
      linesMapRef.current.set(data.line_id, {
        line_id: data.line_id,
        timestamp: data.timestamp,
        speaker: data.speaker,
        text: data.partial_text,
        sequence_number: data.sequence_number,
        is_final: false,
      });
      setVersion((v) => v + 1);
    },
    []
  );

  const handleWordFinal = useCallback(
    (data: TranscriptWordFinalEvent['data']) => {
      linesMapRef.current.set(data.line_id, {
        line_id: data.line_id,
        timestamp: data.timestamp,
        speaker: data.speaker,
        text: data.text,
        sequence_number: data.sequence_number,
        is_final: true,
      });
      setVersion((v) => v + 1);
    },
    []
  );

  const transcriptLines = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const _trigger = version;
    return Array.from(linesMapRef.current.values()).sort(
      (a, b) => a.sequence_number - b.sequence_number
    );
  }, [version]);

  return { transcriptLines, handleWordInterim, handleWordFinal };
}
