/**
 * Unit tests for ModelSelector component
 *
 * Tests dropdown rendering, model selection, and error handling
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import ModelSelector from '../ModelSelector';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

const mockModelConfig = {
  current_model_id: 'gpt-3.5-turbo',
  current: {
    model_id: 'gpt-3.5-turbo',
    model_name: 'gpt-3.5-turbo',
    display_name: 'GPT-3.5 Turbo (Recommended)',
    reasoning_effort: null,
    description: 'Fastest model',
  },
  available: [
    {
      model_id: 'gpt-3.5-turbo',
      model_name: 'gpt-3.5-turbo',
      display_name: 'GPT-3.5 Turbo (Recommended)',
      reasoning_effort: null,
      description: 'Fastest model',
    },
    {
      model_id: 'gpt-4.1-mini',
      model_name: 'gpt-4.1-mini',
      display_name: 'GPT-4.1 Mini',
      reasoning_effort: null,
      description: 'Best latency-to-quality ratio',
    },
    {
      model_id: 'gpt-4o',
      model_name: 'gpt-4o',
      display_name: 'GPT-4o',
      reasoning_effort: null,
      description: 'Quality tier',
    },
    {
      model_id: 'gpt-5',
      model_name: 'gpt-5',
      display_name: 'GPT-5 (Low Reasoning)',
      reasoning_effort: 'low',
      description: 'Reasoning model',
    },
  ],
};

describe('ModelSelector', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('renders nothing before fetch completes', () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // never resolves
    const { container } = render(<ModelSelector />);
    // Should render the container but no select element yet
    expect(container.querySelector('select')).toBeNull();
  });

  test('renders dropdown after successful fetch', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockModelConfig,
    });

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    // Should have 4 options
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(4);
  });

  test('current model is selected in dropdown', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockModelConfig,
    });

    render(<ModelSelector />);

    await waitFor(() => {
      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('gpt-3.5-turbo');
    });
  });

  test('sends PUT request on model change', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockModelConfig,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'updated', model_id: 'gpt-4o', display_name: 'GPT-4o' }),
      });

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'gpt-4o' } });
    });

    // Verify PUT was called
    expect(mockFetch).toHaveBeenCalledTimes(2);
    const putCall = mockFetch.mock.calls[1];
    expect(putCall[0]).toContain('/api/model');
    expect(putCall[1].method).toBe('PUT');
    expect(JSON.parse(putCall[1].body)).toEqual({ model_id: 'gpt-4o' });
  });

  test('reverts selection on PUT failure', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockModelConfig,
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Invalid model' }),
      });

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'gpt-4o' } });
    });

    // Should revert to original model after failure
    await waitFor(() => {
      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('gpt-3.5-turbo');
    });
  });

  test('disables dropdown while updating', async () => {
    let resolvePut: (value: any) => void;
    const putPromise = new Promise((resolve) => { resolvePut = resolve; });

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockModelConfig,
      })
      .mockImplementationOnce(() => putPromise);

    render(<ModelSelector />);

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'gpt-4o' } });
    });

    // Select should be disabled while PUT is in flight
    expect(screen.getByRole('combobox')).toBeDisabled();

    // Resolve the PUT request
    await act(async () => {
      resolvePut!({
        ok: true,
        json: async () => ({ status: 'updated', model_id: 'gpt-4o', display_name: 'GPT-4o' }),
      });
    });

    // Should be enabled again
    await waitFor(() => {
      expect(screen.getByRole('combobox')).not.toBeDisabled();
    });
  });
});
