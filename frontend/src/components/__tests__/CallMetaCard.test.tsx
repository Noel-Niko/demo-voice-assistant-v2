/**
 * Unit tests for CallMetaCard component
 *
 * Tests presentational rendering of call metadata
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CallMetaCard from '../CallMetaCard';
import { CallMeta } from '@/types/conversation';

describe('CallMetaCard', () => {
  const mockMeta: CallMeta = {
    interactionId: 'INT-789456',
    channel: 'Voice',
    queue: 'Technical Support',
    startTime: '10:23 AM',
    duration: '4:32',
    agent: 'Mike Rodriguez',
  };

  test('renders "Call Details" title', () => {
    render(<CallMetaCard meta={mockMeta} />);
    expect(screen.getByText('Call Details')).toBeInTheDocument();
  });

  test('renders interaction ID', () => {
    render(<CallMetaCard meta={mockMeta} />);
    expect(screen.getByText('Interaction')).toBeInTheDocument();
    expect(screen.getByText('INT-789456')).toBeInTheDocument();
  });

  test('renders channel', () => {
    render(<CallMetaCard meta={mockMeta} />);
    expect(screen.getByText('Channel')).toBeInTheDocument();
    expect(screen.getByText('Voice')).toBeInTheDocument();
  });

  test('renders queue', () => {
    render(<CallMetaCard meta={mockMeta} />);
    expect(screen.getByText('Queue')).toBeInTheDocument();
    expect(screen.getByText('Technical Support')).toBeInTheDocument();
  });

  test('renders start time', () => {
    render(<CallMetaCard meta={mockMeta} />);
    expect(screen.getByText('Start')).toBeInTheDocument();
    expect(screen.getByText('10:23 AM')).toBeInTheDocument();
  });

  test('renders duration', () => {
    render(<CallMetaCard meta={mockMeta} />);
    expect(screen.getByText('Duration')).toBeInTheDocument();
    expect(screen.getByText('4:32')).toBeInTheDocument();
  });

  test('renders agent name', () => {
    render(<CallMetaCard meta={mockMeta} />);
    expect(screen.getByText('Agent')).toBeInTheDocument();
    expect(screen.getByText('Mike Rodriguez')).toBeInTheDocument();
  });

  test('renders all six metadata rows', () => {
    const { container } = render(<CallMetaCard meta={mockMeta} />);

    // Count the detail rows (excluding title)
    const labels = screen.getAllByText(/Interaction|Channel|Queue|Start|Duration|Agent/);
    expect(labels).toHaveLength(6);
  });

  test('handles different channel types', () => {
    const chatMeta: CallMeta = {
      ...mockMeta,
      channel: 'Chat',
    };
    render(<CallMetaCard meta={chatMeta} />);
    expect(screen.getByText('Chat')).toBeInTheDocument();
  });

  test('handles long queue names', () => {
    const longQueueMeta: CallMeta = {
      ...mockMeta,
      queue: 'Enterprise Customer VIP Technical Support Escalation Queue',
    };
    render(<CallMetaCard meta={longQueueMeta} />);
    expect(screen.getByText('Enterprise Customer VIP Technical Support Escalation Queue')).toBeInTheDocument();
  });

  test('handles different time formats', () => {
    const time24Meta: CallMeta = {
      ...mockMeta,
      startTime: '14:23',
      duration: '1:05:42',
    };
    render(<CallMetaCard meta={time24Meta} />);
    expect(screen.getByText('14:23')).toBeInTheDocument();
    expect(screen.getByText('1:05:42')).toBeInTheDocument();
  });

  test('renders all call metadata in one view', () => {
    render(<CallMetaCard meta={mockMeta} />);

    // All metadata should be present
    expect(screen.getByText('Call Details')).toBeInTheDocument();
    expect(screen.getByText('INT-789456')).toBeInTheDocument();
    expect(screen.getByText('Voice')).toBeInTheDocument();
    expect(screen.getByText('Technical Support')).toBeInTheDocument();
    expect(screen.getByText('10:23 AM')).toBeInTheDocument();
    expect(screen.getByText('4:32')).toBeInTheDocument();
    expect(screen.getByText('Mike Rodriguez')).toBeInTheDocument();
  });
});
