'use client';

/**
 * ModelSelector — Runtime LLM model dropdown
 *
 * Fetches current model config from GET /api/model on mount.
 * Sends PUT /api/model on change with optimistic UI and revert on failure.
 * Follows the same pattern as the SummaryViewer interval slider.
 */

import { useEffect, useState } from 'react';
import { ModelConfigResponse } from '@/types/conversation';
import { colors, spacing, typography } from '@/styles/grainger-tokens';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';

export default function ModelSelector() {
  const [config, setConfig] = useState<ModelConfigResponse | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [isUpdating, setIsUpdating] = useState(false);

  // Fetch current model config on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await fetch(`${API_URL}/api/model`);
        if (response.ok) {
          const data: ModelConfigResponse = await response.json();
          setConfig(data);
          setSelectedModelId(data.current_model_id);
        }
      } catch (err) {
        console.error('Failed to fetch model config:', err);
      }
    };
    fetchConfig();
  }, []);

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newModelId = e.target.value;
    const previousModelId = selectedModelId;

    // Optimistic update
    setSelectedModelId(newModelId);
    setIsUpdating(true);

    try {
      const response = await fetch(`${API_URL}/api/model`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: newModelId }),
      });

      if (!response.ok) {
        // Revert on failure
        console.error('Model change failed, reverting');
        setSelectedModelId(previousModelId);
      }
    } catch (err) {
      // Revert on network error
      console.error('Model change error, reverting:', err);
      setSelectedModelId(previousModelId);
    } finally {
      setIsUpdating(false);
    }
  };

  if (!config) {
    return <div style={styles.container} />;
  }

  return (
    <div style={styles.container}>
      <label htmlFor="model-selector" style={styles.label}>
        LLM:
      </label>
      <select
        id="model-selector"
        value={selectedModelId}
        onChange={handleChange}
        disabled={isUpdating}
        style={{
          ...styles.select,
          opacity: isUpdating ? 0.6 : 1,
        }}
      >
        {config.available.map((preset) => (
          <option key={preset.model_id} value={preset.model_id}>
            {preset.display_name}
          </option>
        ))}
      </select>
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.xs,
  },
  label: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.semibold,
    color: colors.textLight,
    whiteSpace: 'nowrap' as const,
  },
  select: {
    fontSize: typography.fontSize.xs,
    padding: `2px ${spacing.xs}`,
    borderRadius: '4px',
    border: `1px solid ${colors.border}`,
    backgroundColor: colors.surface,
    color: colors.text,
    cursor: 'pointer',
    outline: 'none',
    transition: 'opacity 0.15s',
  },
};
