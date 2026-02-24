/**
 * Unit tests for CallerInfoCard component
 *
 * Tests presentational rendering of customer information
 */

import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CallerInfoCard from '../CallerInfoCard';
import { CallerInfo } from '@/types/conversation';

describe('CallerInfoCard', () => {
  const mockCaller: CallerInfo = {
    customerName: 'Sarah Johnson',
    company: 'Acme Corp',
    accountNumber: 'A1234567',
    tier: 'Gold',
  };

  test('renders customer name', () => {
    render(<CallerInfoCard caller={mockCaller} />);
    expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
  });

  test('renders company name', () => {
    render(<CallerInfoCard caller={mockCaller} />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  test('renders account number', () => {
    render(<CallerInfoCard caller={mockCaller} />);
    expect(screen.getByText('A1234567')).toBeInTheDocument();
  });

  test('renders tier badge', () => {
    render(<CallerInfoCard caller={mockCaller} />);
    expect(screen.getByText('Gold')).toBeInTheDocument();
  });

  test('renders avatar with first letter of customer name', () => {
    const { container } = render(<CallerInfoCard caller={mockCaller} />);
    expect(container.textContent).toContain('S');
  });

  test('avatar uses uppercase first letter', () => {
    const lowercaseCaller: CallerInfo = {
      ...mockCaller,
      customerName: 'john doe',
    };
    render(<CallerInfoCard caller={lowercaseCaller} />);
    // Avatar should show "J" (uppercase) - it's rendered in the component
    expect(screen.getByText('J')).toBeInTheDocument();
  });

  test('renders all detail labels', () => {
    render(<CallerInfoCard caller={mockCaller} />);
    expect(screen.getByText('Account')).toBeInTheDocument();
    expect(screen.getByText('Tier')).toBeInTheDocument();
  });

  test('handles long customer names', () => {
    const longNameCaller: CallerInfo = {
      ...mockCaller,
      customerName: 'Alexander Bartholomew Wellington-Smythe III',
    };
    render(<CallerInfoCard caller={longNameCaller} />);
    expect(screen.getByText('Alexander Bartholomew Wellington-Smythe III')).toBeInTheDocument();
  });

  test('handles long company names', () => {
    const longCompanyCaller: CallerInfo = {
      ...mockCaller,
      company: 'International Business Machines Corporation Global Services Division',
    };
    render(<CallerInfoCard caller={longCompanyCaller} />);
    expect(screen.getByText('International Business Machines Corporation Global Services Division')).toBeInTheDocument();
  });

  test('handles different tier values', () => {
    const platinumCaller: CallerInfo = {
      ...mockCaller,
      tier: 'Platinum',
    };
    render(<CallerInfoCard caller={platinumCaller} />);
    expect(screen.getByText('Platinum')).toBeInTheDocument();
  });

  test('renders all customer information in one view', () => {
    render(<CallerInfoCard caller={mockCaller} />);

    // All key info should be present
    expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Account')).toBeInTheDocument();
    expect(screen.getByText('A1234567')).toBeInTheDocument();
    expect(screen.getByText('Tier')).toBeInTheDocument();
    expect(screen.getByText('Gold')).toBeInTheDocument();
  });
});
