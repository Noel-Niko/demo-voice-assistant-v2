/**
 * Unit tests for useTranscriptStream hook
 *
 * Tests Map-based transcript accumulation and sorting
 */

import { describe, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTranscriptStream } from '../useTranscriptStream';

describe('useTranscriptStream', () => {
  test('initializes with empty transcript', () => {
    const { result } = renderHook(() => useTranscriptStream());

    expect(result.current.transcriptLines).toEqual([]);
  });

  test('adds interim transcript line', () => {
    const { result } = renderHook(() => useTranscriptStream());

    act(() => {
      result.current.handleWordInterim({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        partial_text: 'Hello',
        sequence_number: 0,
      });
    });

    expect(result.current.transcriptLines).toHaveLength(1);
    expect(result.current.transcriptLines[0]).toEqual({
      line_id: 'line-1',
      timestamp: '2024-01-01T10:00:00Z',
      speaker: 'agent',
      text: 'Hello',
      sequence_number: 0,
      is_final: false,
    });
  });

  test('updates interim line to final', () => {
    const { result } = renderHook(() => useTranscriptStream());

    // Add interim line
    act(() => {
      result.current.handleWordInterim({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        partial_text: 'Hello wo',
        sequence_number: 0,
      });
    });

    expect(result.current.transcriptLines[0].text).toBe('Hello wo');
    expect(result.current.transcriptLines[0].is_final).toBe(false);

    // Finalize the line
    act(() => {
      result.current.handleWordFinal({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        text: 'Hello world',
        sequence_number: 0,
      });
    });

    expect(result.current.transcriptLines).toHaveLength(1);
    expect(result.current.transcriptLines[0].text).toBe('Hello world');
    expect(result.current.transcriptLines[0].is_final).toBe(true);
  });

  test('sorts lines by sequence number', () => {
    const { result } = renderHook(() => useTranscriptStream());

    // Add lines out of order
    act(() => {
      result.current.handleWordFinal({
        line_id: 'line-3',
        timestamp: '2024-01-01T10:00:02Z',
        speaker: 'customer',
        text: 'Third line',
        sequence_number: 2,
      });

      result.current.handleWordFinal({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        text: 'First line',
        sequence_number: 0,
      });

      result.current.handleWordFinal({
        line_id: 'line-2',
        timestamp: '2024-01-01T10:00:01Z',
        speaker: 'customer',
        text: 'Second line',
        sequence_number: 1,
      });
    });

    expect(result.current.transcriptLines).toHaveLength(3);
    expect(result.current.transcriptLines[0].text).toBe('First line');
    expect(result.current.transcriptLines[1].text).toBe('Second line');
    expect(result.current.transcriptLines[2].text).toBe('Third line');
  });

  test('handles multiple interim updates before final', () => {
    const { result } = renderHook(() => useTranscriptStream());

    // Multiple interim updates for same line
    act(() => {
      result.current.handleWordInterim({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        partial_text: 'H',
        sequence_number: 0,
      });
    });

    expect(result.current.transcriptLines[0].text).toBe('H');

    act(() => {
      result.current.handleWordInterim({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        partial_text: 'Hello',
        sequence_number: 0,
      });
    });

    expect(result.current.transcriptLines[0].text).toBe('Hello');

    act(() => {
      result.current.handleWordInterim({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        partial_text: 'Hello wo',
        sequence_number: 0,
      });
    });

    expect(result.current.transcriptLines[0].text).toBe('Hello wo');

    // Final update
    act(() => {
      result.current.handleWordFinal({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        text: 'Hello world',
        sequence_number: 0,
      });
    });

    expect(result.current.transcriptLines).toHaveLength(1);
    expect(result.current.transcriptLines[0].text).toBe('Hello world');
    expect(result.current.transcriptLines[0].is_final).toBe(true);
  });

  test('handles interleaved interim and final lines', () => {
    const { result } = renderHook(() => useTranscriptStream());

    act(() => {
      // Agent line 1 - final
      result.current.handleWordFinal({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        text: 'Agent line',
        sequence_number: 0,
      });

      // Customer line 2 - interim
      result.current.handleWordInterim({
        line_id: 'line-2',
        timestamp: '2024-01-01T10:00:01Z',
        speaker: 'customer',
        partial_text: 'Customer l',
        sequence_number: 1,
      });

      // Agent line 3 - final
      result.current.handleWordFinal({
        line_id: 'line-3',
        timestamp: '2024-01-01T10:00:02Z',
        speaker: 'agent',
        text: 'Another agent line',
        sequence_number: 2,
      });
    });

    expect(result.current.transcriptLines).toHaveLength(3);
    expect(result.current.transcriptLines[0].is_final).toBe(true);
    expect(result.current.transcriptLines[1].is_final).toBe(false);
    expect(result.current.transcriptLines[2].is_final).toBe(true);
  });

  test('Map-based storage ensures O(1) updates for same line_id', () => {
    const { result } = renderHook(() => useTranscriptStream());

    // Add 100 lines
    act(() => {
      for (let i = 0; i < 100; i++) {
        result.current.handleWordFinal({
          line_id: `line-${i}`,
          timestamp: `2024-01-01T10:00:${i.toString().padStart(2, '0')}Z`,
          speaker: i % 2 === 0 ? 'agent' : 'customer',
          text: `Line ${i}`,
          sequence_number: i,
        });
      }
    });

    expect(result.current.transcriptLines).toHaveLength(100);

    // Update line in the middle (should be O(1) operation via Map)
    act(() => {
      result.current.handleWordFinal({
        line_id: 'line-50',
        timestamp: '2024-01-01T10:00:50Z',
        speaker: 'agent',
        text: 'Updated line 50',
        sequence_number: 50,
      });
    });

    // Still 100 lines (no duplicate)
    expect(result.current.transcriptLines).toHaveLength(100);
    expect(result.current.transcriptLines[50].text).toBe('Updated line 50');
  });

  test('handles speaker transitions correctly', () => {
    const { result } = renderHook(() => useTranscriptStream());

    act(() => {
      result.current.handleWordFinal({
        line_id: 'line-1',
        timestamp: '2024-01-01T10:00:00Z',
        speaker: 'agent',
        text: 'Agent speaks',
        sequence_number: 0,
      });

      result.current.handleWordFinal({
        line_id: 'line-2',
        timestamp: '2024-01-01T10:00:01Z',
        speaker: 'customer',
        text: 'Customer responds',
        sequence_number: 1,
      });

      result.current.handleWordFinal({
        line_id: 'line-3',
        timestamp: '2024-01-01T10:00:02Z',
        speaker: 'agent',
        text: 'Agent replies',
        sequence_number: 2,
      });
    });

    expect(result.current.transcriptLines[0].speaker).toBe('agent');
    expect(result.current.transcriptLines[1].speaker).toBe('customer');
    expect(result.current.transcriptLines[2].speaker).toBe('agent');
  });

  test('preserves timestamp and metadata during updates', () => {
    const { result } = renderHook(() => useTranscriptStream());

    const originalTimestamp = '2024-01-01T10:00:00Z';

    act(() => {
      result.current.handleWordInterim({
        line_id: 'line-1',
        timestamp: originalTimestamp,
        speaker: 'agent',
        partial_text: 'Hello',
        sequence_number: 0,
      });
    });

    const initialTimestamp = result.current.transcriptLines[0].timestamp;

    act(() => {
      result.current.handleWordFinal({
        line_id: 'line-1',
        timestamp: originalTimestamp,
        speaker: 'agent',
        text: 'Hello world',
        sequence_number: 0,
      });
    });

    // Timestamp should remain consistent
    expect(result.current.transcriptLines[0].timestamp).toBe(initialTimestamp);
    expect(result.current.transcriptLines[0].timestamp).toBe(originalTimestamp);
  });
});
