/**
 * Unit tests for TranscriptViewer component
 *
 * Tests transcript rendering, reverse chronological order, and streaming states
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import TranscriptViewer from '../TranscriptViewer';
import { TranscriptLine } from '@/types/conversation';

describe('TranscriptViewer', () => {
  const mockLines: TranscriptLine[] = [
    {
      line_id: 'line-1',
      timestamp: '2024-01-01T10:00:00Z',
      speaker: 'agent',
      text: 'Hello, how can I help you?',
      sequence_number: 0,
      is_final: true,
    },
    {
      line_id: 'line-2',
      timestamp: '2024-01-01T10:00:05Z',
      speaker: 'customer',
      text: 'I need help with my order',
      sequence_number: 1,
      is_final: true,
    },
  ];

  test('renders "Transcript" title', () => {
    render(<TranscriptViewer lines={[]} />);
    expect(screen.getByText('Transcript')).toBeInTheDocument();
  });

  test('shows empty state when no lines', () => {
    render(<TranscriptViewer lines={[]} />);
    expect(screen.getByText('No transcript lines yet.')).toBeInTheDocument();
    expect(screen.getByText('Waiting for conversation to start...')).toBeInTheDocument();
  });

  test('does not show empty state when loading', () => {
    render(<TranscriptViewer lines={[]} isLoading={true} />);
    expect(screen.queryByText('No transcript lines yet.')).not.toBeInTheDocument();
  });

  test('shows streaming badge when loading', () => {
    render(<TranscriptViewer lines={[]} isLoading={true} />);
    expect(screen.getByText('Streaming...')).toBeInTheDocument();
  });

  test('renders transcript lines', () => {
    render(<TranscriptViewer lines={mockLines} />);

    expect(screen.getByText('Hello, how can I help you?')).toBeInTheDocument();
    expect(screen.getByText('I need help with my order')).toBeInTheDocument();
  });

  test('renders speaker labels in uppercase', () => {
    render(<TranscriptViewer lines={mockLines} />);

    expect(screen.getByText('AGENT')).toBeInTheDocument();
    expect(screen.getByText('CUSTOMER')).toBeInTheDocument();
  });

  test('renders lines in reverse chronological order', () => {
    render(<TranscriptViewer lines={mockLines} />);

    const allText = screen.getAllByText(/Hello|help with my order/);

    // Customer line (sequence 1) should appear BEFORE agent line (sequence 0) in DOM
    // because reverse() puts newest (highest sequence) first
    expect(allText[0].textContent).toContain('help with my order');
    expect(allText[1].textContent).toContain('Hello');
  });

  test('formats timestamps', () => {
    render(<TranscriptViewer lines={mockLines} />);

    // Check that timestamps are formatted (will vary by locale)
    const timestamps = screen.getAllByText(/\d{1,2}:\d{2}:\d{2}/);
    expect(timestamps.length).toBeGreaterThan(0);
  });

  test('renders interim line with reduced opacity', () => {
    const interimLine: TranscriptLine = {
      ...mockLines[0],
      is_final: false,
      text: 'He',
    };

    const { container } = render(<TranscriptViewer lines={[interimLine]} />);

    // Interim lines have opacity: 0.7
    const lineElement = container.querySelector('[style*="opacity"]');
    expect(lineElement).toBeTruthy();
  });

  test('renders blinking cursor for interim lines', () => {
    const interimLine: TranscriptLine = {
      ...mockLines[0],
      is_final: false,
      text: 'He',
    };

    const { container } = render(<TranscriptViewer lines={[interimLine]} />);

    // Blinking cursor renders as "|"
    expect(container.textContent).toContain('|');
  });

  test('does not render cursor for final lines', () => {
    render(<TranscriptViewer lines={mockLines} />);

    // Should not have cursor after final lines
    // Count "|" characters - should only be in speaker labels if any
    const textContent = screen.getByText('Hello, how can I help you?').parentElement?.textContent;
    expect(textContent).not.toMatch(/Hello.*\|/);
  });

  test('handles empty speaker gracefully', () => {
    const lineWithEmptySpeaker: TranscriptLine = {
      ...mockLines[0],
      speaker: '',
    };

    render(<TranscriptViewer lines={[lineWithEmptySpeaker]} />);

    // Should still render without crashing
    expect(screen.getByText('Hello, how can I help you?')).toBeInTheDocument();
  });

  test('handles long text content', () => {
    const longTextLine: TranscriptLine = {
      ...mockLines[0],
      text: 'This is a very long line of text that should wrap properly in the transcript viewer component without breaking the layout or causing horizontal scrolling issues. It continues for quite a while to test the word wrapping behavior.',
    };

    render(<TranscriptViewer lines={[longTextLine]} />);

    expect(screen.getByText(/This is a very long line/)).toBeInTheDocument();
  });

  test('handles many transcript lines', () => {
    const manyLines: TranscriptLine[] = Array.from({ length: 100 }, (_, i) => ({
      line_id: `line-${i}`,
      timestamp: `2024-01-01T10:00:${String(i).padStart(2, '0')}Z`,
      speaker: i % 2 === 0 ? 'agent' : 'customer',
      text: `Line ${i} text`,
      sequence_number: i,
      is_final: true,
    }));

    render(<TranscriptViewer lines={manyLines} />);

    // Should render all lines (spot check first and last)
    expect(screen.getByText('Line 0 text')).toBeInTheDocument();
    expect(screen.getByText('Line 99 text')).toBeInTheDocument();
  });

  test('handles mixed final and interim lines', () => {
    const mixedLines: TranscriptLine[] = [
      { ...mockLines[0], is_final: true },
      { ...mockLines[1], is_final: false, text: 'I need' },
    ];

    const { container } = render(<TranscriptViewer lines={mixedLines} />);

    // Both should be rendered
    expect(screen.getByText('Hello, how can I help you?')).toBeInTheDocument();
    expect(screen.getByText(/I need/)).toBeInTheDocument();
    // Interim line should have cursor
    expect(container.textContent).toContain('|');
  });

  test('handles invalid timestamp gracefully', () => {
    const invalidTimestampLine: TranscriptLine = {
      ...mockLines[0],
      timestamp: 'invalid-timestamp',
    };

    render(<TranscriptViewer lines={[invalidTimestampLine]} />);

    // Should still render, falling back to showing the invalid timestamp
    expect(screen.getByText('Hello, how can I help you?')).toBeInTheDocument();
  });

  test('renders streaming indicator when loading with lines', () => {
    render(<TranscriptViewer lines={mockLines} isLoading={true} />);

    // Should show streaming badge in header
    expect(screen.getByText('Streaming...')).toBeInTheDocument();
  });

  test('does not render streaming indicator when not loading', () => {
    const { container } = render(<TranscriptViewer lines={mockLines} isLoading={false} />);

    // Check that streaming badge is not present
    expect(screen.queryByText('Streaming...')).not.toBeInTheDocument();
  });
});
