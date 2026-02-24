/**
 * Unit tests for InteractionHistory component
 *
 * Tests expand/collapse state and history rendering
 */

import { describe, test, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import InteractionHistory from '../InteractionHistory';
import { InteractionHistoryItem } from '@/types/conversation';

describe('InteractionHistory', () => {
  const mockHistory: InteractionHistoryItem[] = [
    {
      date: '2024-01-15',
      channel: 'Voice',
      subject: 'Product inquiry',
      resolution: 'Resolved - Information provided',
    },
    {
      date: '2023-12-20',
      channel: 'Chat',
      subject: 'Return request',
      resolution: 'Resolved - Return processed',
    },
  ];

  test('renders collapsed by default', () => {
    render(<InteractionHistory history={mockHistory} />);

    // Header should be visible
    expect(screen.getByText('History (2)')).toBeInTheDocument();

    // Items should not be visible
    expect(screen.queryByText('Product inquiry')).not.toBeInTheDocument();
    expect(screen.queryByText('Return request')).not.toBeInTheDocument();
  });

  test('shows correct history count in header', () => {
    render(<InteractionHistory history={mockHistory} />);
    expect(screen.getByText('History (2)')).toBeInTheDocument();
  });

  test('shows zero count when empty', () => {
    render(<InteractionHistory history={[]} />);
    expect(screen.getByText('History (0)')).toBeInTheDocument();
  });

  test('expands when header clicked', () => {
    render(<InteractionHistory history={mockHistory} />);

    const header = screen.getByText('History (2)');
    fireEvent.click(header);

    // Items should now be visible
    expect(screen.getByText('Product inquiry')).toBeInTheDocument();
    expect(screen.getByText('Return request')).toBeInTheDocument();
  });

  test('collapses when header clicked again', () => {
    render(<InteractionHistory history={mockHistory} />);

    const header = screen.getByText('History (2)');

    // Expand
    fireEvent.click(header);
    expect(screen.getByText('Product inquiry')).toBeInTheDocument();

    // Collapse
    fireEvent.click(header);
    expect(screen.queryByText('Product inquiry')).not.toBeInTheDocument();
  });

  test('toggles expand icon', () => {
    render(<InteractionHistory history={mockHistory} />);

    // Should show collapsed icon (▶)
    expect(screen.getByText('▶')).toBeInTheDocument();

    const header = screen.getByText('History (2)');
    fireEvent.click(header);

    // Should show expanded icon (▼)
    expect(screen.getByText('▼')).toBeInTheDocument();
  });

  test('renders all history item fields', () => {
    render(<InteractionHistory history={mockHistory} />);

    const header = screen.getByText('History (2)');
    fireEvent.click(header);

    // First item
    expect(screen.getByText('2024-01-15')).toBeInTheDocument();
    expect(screen.getByText('Voice')).toBeInTheDocument();
    expect(screen.getByText('Product inquiry')).toBeInTheDocument();
    expect(screen.getByText('Resolved - Information provided')).toBeInTheDocument();

    // Second item
    expect(screen.getByText('2023-12-20')).toBeInTheDocument();
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Return request')).toBeInTheDocument();
    expect(screen.getByText('Resolved - Return processed')).toBeInTheDocument();
  });

  test('shows empty state when no history', () => {
    render(<InteractionHistory history={[]} />);

    const header = screen.getByText('History (0)');
    fireEvent.click(header);

    expect(screen.getByText('No previous interactions')).toBeInTheDocument();
  });

  test('empty state only visible when expanded', () => {
    render(<InteractionHistory history={[]} />);

    // Collapsed - empty state not visible
    expect(screen.queryByText('No previous interactions')).not.toBeInTheDocument();

    const header = screen.getByText('History (0)');
    fireEvent.click(header);

    // Expanded - empty state visible
    expect(screen.getByText('No previous interactions')).toBeInTheDocument();
  });

  test('handles single history item', () => {
    const singleItem: InteractionHistoryItem[] = [
      {
        date: '2024-02-01',
        channel: 'Email',
        subject: 'Billing question',
        resolution: 'Resolved - Refund issued',
      },
    ];

    render(<InteractionHistory history={singleItem} />);

    expect(screen.getByText('History (1)')).toBeInTheDocument();

    const header = screen.getByText('History (1)');
    fireEvent.click(header);

    expect(screen.getByText('2024-02-01')).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('Billing question')).toBeInTheDocument();
    expect(screen.getByText('Resolved - Refund issued')).toBeInTheDocument();
  });

  test('handles many history items', () => {
    const manyItems: InteractionHistoryItem[] = Array.from({ length: 10 }, (_, i) => ({
      date: `2024-01-${String(i + 1).padStart(2, '0')}`,
      channel: i % 2 === 0 ? 'Voice' : 'Chat',
      subject: `Subject ${i + 1}`,
      resolution: `Resolution ${i + 1}`,
    }));

    render(<InteractionHistory history={manyItems} />);

    expect(screen.getByText('History (10)')).toBeInTheDocument();

    const header = screen.getByText('History (10)');
    fireEvent.click(header);

    // All 10 items should be rendered
    expect(screen.getByText('Subject 1')).toBeInTheDocument();
    expect(screen.getByText('Subject 10')).toBeInTheDocument();
  });

  test('renders different channel types', () => {
    const multiChannelHistory: InteractionHistoryItem[] = [
      { date: '2024-01-01', channel: 'Voice', subject: 'Test 1', resolution: 'Resolved' },
      { date: '2024-01-02', channel: 'Chat', subject: 'Test 2', resolution: 'Resolved' },
      { date: '2024-01-03', channel: 'Email', subject: 'Test 3', resolution: 'Resolved' },
      { date: '2024-01-04', channel: 'SMS', subject: 'Test 4', resolution: 'Resolved' },
    ];

    render(<InteractionHistory history={multiChannelHistory} />);

    const header = screen.getByText('History (4)');
    fireEvent.click(header);

    expect(screen.getByText('Voice')).toBeInTheDocument();
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('SMS')).toBeInTheDocument();
  });

  test('maintains expanded state when clicking within list', () => {
    render(<InteractionHistory history={mockHistory} />);

    const header = screen.getByText('History (2)');
    fireEvent.click(header);

    // Expanded
    expect(screen.getByText('Product inquiry')).toBeInTheDocument();

    // Click on an item (not the header)
    const item = screen.getByText('Product inquiry');
    fireEvent.click(item);

    // Should remain expanded
    expect(screen.getByText('Product inquiry')).toBeInTheDocument();
  });
});
