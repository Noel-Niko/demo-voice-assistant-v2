/**
 * MCP Suggestions Box Component
 *
 * Displays AI-powered suggestions from MCP (Model Context Protocol) server.
 * Uses RAG (Retrieval-Augmented Generation) to provide contextual suggestions
 * for product information, order status, and knowledge base articles.
 *
 * Integration: Connects to any MCP-compatible server via MCP_INGRESS_URL
 */

import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { colors, spacing, typography, borderRadius, shadows } from '@/styles/design-tokens';

interface MCPSuggestion {
  title: string;
  content: string;
  source: string | null;
  relevance: number;
}

interface MCPSuggestionsBoxProps {
  conversationId: string | null;
  isVisible?: boolean;
  autoQueryData?: any;
}

export default function MCPSuggestionsBox({
  conversationId,
  isVisible = true,
  autoQueryData,
}: MCPSuggestionsBoxProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<MCPSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mcpAvailable, setMcpAvailable] = useState(true);
  const [toolUsed, setToolUsed] = useState<string | null>(null);
  const [progressMessages, setProgressMessages] = useState<string[]>([]);
  const [listeningMode, setListeningMode] = useState(false);
  const [listeningModeAvailable, setListeningModeAvailable] = useState<boolean | null>(null);
  const [isTogglingListeningMode, setIsTogglingListeningMode] = useState(false);
  const [isAutoQuery, setIsAutoQuery] = useState(false);
  const [interactionId, setInteractionId] = useState<number | null>(null);
  const [selectedRating, setSelectedRating] = useState<'up' | 'down' | null>(null);

  // Initialize toggle state from backend on mount
  useEffect(() => {
    if (!conversationId) return;

    const fetchListeningModeStatus = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
        const response = await fetch(
          `${apiUrl}/api/conversations/${conversationId}/listening-mode/status`
        );

        if (response.ok) {
          const data = await response.json();
          setListeningModeAvailable(data.available);
          setListeningMode(data.is_active);
          localStorage.setItem('mcp_listening_mode', String(data.is_active));
          console.log('[MCPSuggestionsBox] Listening mode available:', data.available, 'active:', data.is_active);
        }
      } catch (err) {
        console.error('[MCPSuggestionsBox] Failed to fetch listening mode status:', err);
      }
    };

    fetchListeningModeStatus();
  }, [conversationId]);

  // Handle auto-query data updates from WebSocket
  useEffect(() => {
    if (!autoQueryData) return;

    console.log('[MCPSuggestionsBox] Auto-query complete received:', autoQueryData);
    console.log('[MCPSuggestionsBox] Current listening mode state:', listeningMode);

    // IMPORTANT: Only process auto-queries if listening mode is currently active
    // Ignore in-flight queries that complete after user toggled OFF
    if (!listeningMode) {
      console.log('[MCPSuggestionsBox] Ignoring auto-query - listening mode is OFF');
      return;
    }

    // Clear any existing manual query state
    setError(null);
    setIsLoading(false);
    setIsAutoQuery(true);

    // Parse result to suggestions
    const result = autoQueryData.result;
    if (result && result.result && result.result.content) {
      const autoSuggestions: MCPSuggestion[] = [];

      for (const item of result.result.content) {
        const textContent = item.text || item.content || '';
        autoSuggestions.push({
          title: item.title || 'Auto-detected Result',
          content: typeof textContent === 'string' ? textContent : String(textContent),
          source: item.url || item.source || null,
          relevance: item.score || 1.0,
        });
      }

      setSuggestions(autoSuggestions);
      setToolUsed(
        result.tool_name ? `${result.server_path}/${result.tool_name}` : null
      );
      setMcpAvailable(true);

      console.log('[MCPSuggestionsBox] Auto-query suggestions displayed:', autoSuggestions.length);
    }
  }, [autoQueryData]);

  if (!isVisible) {
    return null;
  }

  const handleToggleListeningMode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!conversationId) {
      e.preventDefault();
      return;
    }

    const newMode = e.target.checked;
    const endpoint = newMode ? 'start' : 'stop';

    setIsTogglingListeningMode(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
      const response = await fetch(
        `${apiUrl}/api/conversations/${conversationId}/listening-mode/${endpoint}`,
        { method: 'POST' }
      );

      if (response.status === 503) {
        setError('Listening mode not available. Feature disabled or not configured.');
        setIsTogglingListeningMode(false);
        // Revert checkbox state
        setListeningMode(!newMode);
        return;
      }

      if (!response.ok) {
        throw new Error(`Failed to ${endpoint} listening mode`);
      }

      const data = await response.json();
      // Only update state after successful API call
      setListeningMode(newMode);
      localStorage.setItem('mcp_listening_mode', String(newMode));

      // When toggling OFF, reset auto-query flag so manual queries show correct icon
      if (!newMode) {
        setIsAutoQuery(false);
      }

      console.log(`[MCPSuggestionsBox] Listening mode ${newMode ? 'started' : 'stopped'}`, data);
    } catch (err) {
      console.error('[MCPSuggestionsBox] Toggle failed:', err);
      setError(err instanceof Error ? err.message : 'Failed to toggle listening mode');
      // Revert checkbox state on error
      setListeningMode(!newMode);
    } finally {
      setIsTogglingListeningMode(false);
    }
  };

  const handleRate = async (rating: 'up' | 'down') => {
    if (!interactionId) {
      console.warn('[MCPSuggestionsBox] Cannot rate: no interaction_id available');
      return;
    }

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
      const response = await fetch(
        `${apiUrl}/api/suggestions/${interactionId}/rate`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rating }),
        }
      );

      if (response.ok) {
        setSelectedRating(rating);
        console.log('[MCPSuggestionsBox] Rated suggestion:', rating);
      } else {
        console.error('[MCPSuggestionsBox] Failed to rate suggestion:', await response.text());
      }
    } catch (err) {
      console.error('[MCPSuggestionsBox] Failed to rate suggestion:', err);
    }
  };

  const handleQuery = async () => {
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);
    setToolUsed(null);
    setSuggestions([]);
    setProgressMessages([]);
    setInteractionId(null);
    setSelectedRating(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765';
      const response = await fetch(`${apiUrl}/api/mcp/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query.trim(),
          conversation_id: conversationId,
          preferred_server: null, // Let LLM select best server
        }),
      });

      if (response.status === 503) {
        // MCP not available
        setMcpAvailable(false);
        setError('MCP features not available. MCP_SECRET_KEY not configured.');
        setIsLoading(false);
        return;
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Query failed' }));
        throw new Error(errorData.detail || `Query failed: ${response.status}`);
      }

      // Handle SSE stream
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('Response body is not readable');
      }

      const MAX_BUFFER_SIZE = 10000; // 10KB limit to prevent memory exhaustion
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Guard against unbounded buffer growth
        if (buffer.length > MAX_BUFFER_SIZE) {
          console.error('[MCPSuggestionsBox] Buffer exceeded max size, truncating');
          buffer = buffer.slice(-MAX_BUFFER_SIZE); // Keep last 10KB
        }

        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6); // Remove 'data: ' prefix

            if (data === '[DONE]') {
              setIsLoading(false);
              continue;
            }

            try {
              const event = JSON.parse(data);

              if (event.type === 'progress') {
                setProgressMessages((prev) => [...prev, event.message]);
              } else if (event.type === 'result') {
                setSuggestions(event.data.suggestions || []);
                setToolUsed(
                  event.data.tool_name
                    ? `${event.data.server_path}/${event.data.tool_name}`
                    : null
                );
                setInteractionId(event.data.interaction_id || null);
                setMcpAvailable(true);
              } else if (event.type === 'error') {
                throw new Error(event.message);
              }
            } catch (parseErr) {
              console.warn('[MCPSuggestionsBox] Failed to parse SSE event:', data);
            }
          }
        }
      }
    } catch (err) {
      console.error('[MCPSuggestionsBox] Query failed:', err);
      setError(err instanceof Error ? err.message : 'Query failed');
      setSuggestions([]);
      setIsLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes dots {
          0%, 20% {
            content: '.';
          }
          40% {
            content: '..';
          }
          60%, 100% {
            content: '...';
          }
        }

        .dots-animation::after {
          content: '...';
          animation: dots 1.5s steps(3, end) infinite;
        }
      `}</style>
      <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.headerContent} onClick={() => setIsExpanded(!isExpanded)}>
          <span style={styles.icon}>💡</span>
          <h3 style={styles.title}>AI Suggestions</h3>
          {!mcpAvailable && (
            <span style={styles.badge(colors.warning)}>Unavailable</span>
          )}
          <span style={styles.expandIcon}>{isExpanded ? '▼' : '▶'}</span>
        </div>

        {/* Listening Mode Toggle or MCP Not Configured Message */}
        <div style={styles.toggleContainer} onClick={(e) => e.stopPropagation()}>
          {listeningModeAvailable === false ? (
            <span style={styles.mcpNotConfiguredText}>
              Connect an MCP server to enable listening mode
            </span>
          ) : (
            <label style={{
              ...styles.toggleLabel,
              opacity: isTogglingListeningMode ? 0.6 : 1,
              cursor: isTogglingListeningMode ? 'not-allowed' : 'pointer',
            }}>
              <input
                type="checkbox"
                checked={listeningMode}
                onChange={handleToggleListeningMode}
                disabled={isTogglingListeningMode}
                style={styles.toggleCheckbox}
              />
              <span style={styles.toggleSwitch(listeningMode)}>
                <span style={styles.toggleSlider(listeningMode)}></span>
              </span>
              <span style={styles.toggleText}>
                {isTogglingListeningMode
                  ? '⏳ Updating...'
                  : listeningMode
                  ? '🎧 Listening'
                  : 'Manual Mode'}
              </span>
            </label>
          )}
        </div>
      </div>

      {isExpanded && (
        <div style={styles.content}>
          {/* Listening Mode Info Banner */}
          {listeningMode && (
            <div style={styles.listeningBanner}>
              <span style={styles.listeningIcon}>🎧</span>
              <div style={styles.listeningText}>
                <strong>Listening Mode Active</strong>
              </div>
            </div>
          )}

          {/* Query Input */}
          <div style={styles.queryBox}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
              placeholder="Ask about products, orders, or policies..."
              style={styles.input}
              disabled={isLoading || !mcpAvailable}
            />
            <button
              onClick={handleQuery}
              disabled={isLoading || !query.trim() || !mcpAvailable}
              style={styles.button(isLoading || !query.trim() || !mcpAvailable)}
            >
              {isLoading ? (
                <span>
                  Searching<span className="dots-animation"></span>
                </span>
              ) : (
                'Search'
              )}
            </button>
          </div>

          {/* Progress Messages with Fade-in Animation */}
          {isLoading && progressMessages.length > 0 && (
            <div style={styles.progressContainer}>
              {progressMessages.map((message, index) => (
                <div
                  key={index}
                  style={{
                    ...styles.progressMessage,
                    animation: 'fadeIn 0.5s ease-in',
                    animationFillMode: 'both',
                    animationDelay: `${index * 0.1}s`,
                  }}
                >
                  {message}
                </div>
              ))}
            </div>
          )}

          {/* Tool Used Indicator */}
          {toolUsed && !isLoading && (
            <div style={styles.toolUsed}>
              <span style={styles.toolUsedLabel}>
                {isAutoQuery ? '🎧 Auto-detected:' : '🤖 AI selected tool:'}
              </span>
              <span style={styles.toolUsedValue}>{toolUsed}</span>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div style={styles.errorBox}>
              <span style={styles.errorIcon}>⚠️</span>
              <span style={styles.errorText}>{error}</span>
            </div>
          )}

          {/* Suggestions */}
          {suggestions.length > 0 && (
            <div style={styles.suggestionsList}>
              {suggestions.map((suggestion, index) => (
                <div key={index} style={styles.suggestionCard}>
                  <div style={styles.suggestionHeader}>
                    <h4 style={styles.suggestionTitle}>{suggestion.title}</h4>
                    {/* Relevance score removed from display but preserved in data for metrics/dashboard */}
                  </div>
                  <div style={styles.suggestionContent}>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        // Style links with hover effect
                        a: ({ node, ...props }) => (
                          <a
                            {...props}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: colors.info,
                              textDecoration: 'underline',
                              fontWeight: typography.fontWeight.medium,
                              cursor: 'pointer',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.textDecoration = 'none';
                              e.currentTarget.style.opacity = '0.8';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.textDecoration = 'underline';
                              e.currentTarget.style.opacity = '1';
                            }}
                          />
                        ),
                        // Style bold text
                        strong: ({ node, ...props }) => (
                          <strong
                            {...props}
                            style={{
                              fontWeight: typography.fontWeight.semibold,
                              color: colors.text,
                            }}
                          />
                        ),
                        // Style paragraphs
                        p: ({ node, ...props }) => (
                          <p
                            {...props}
                            style={{
                              margin: `${spacing.xs} 0`,
                              lineHeight: 1.6,
                            }}
                          />
                        ),
                        // Style list items
                        li: ({ node, ...props }) => (
                          <li
                            {...props}
                            style={{
                              marginBottom: spacing.xs,
                              lineHeight: 1.6,
                            }}
                          />
                        ),
                        // Style unordered lists
                        ul: ({ node, ...props }) => (
                          <ul
                            {...props}
                            style={{
                              marginLeft: spacing.md,
                              listStyleType: 'disc',
                            }}
                          />
                        ),
                      }}
                    >
                      {suggestion.content}
                    </ReactMarkdown>
                  </div>
                  {suggestion.source && (
                    <a
                      href={suggestion.source}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={styles.suggestionSource}
                    >
                      View Source →
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Rating Buttons (Fix 2) */}
          {suggestions.length > 0 && interactionId !== null && !isAutoQuery && (
            <div style={styles.ratingContainer}>
              <span style={styles.ratingLabel}>Was this helpful?</span>
              <div style={styles.ratingButtons}>
                <button
                  onClick={() => handleRate('up')}
                  disabled={selectedRating !== null}
                  style={styles.ratingButton(selectedRating === 'up', 'up')}
                  title="Thumbs up"
                >
                  👍 {selectedRating === 'up' && 'Thanks!'}
                </button>
                <button
                  onClick={() => handleRate('down')}
                  disabled={selectedRating !== null}
                  style={styles.ratingButton(selectedRating === 'down', 'down')}
                  title="Thumbs down"
                >
                  👎 {selectedRating === 'down' && 'Thanks!'}
                </button>
              </div>
            </div>
          )}

          {/* Empty State */}
          {suggestions.length === 0 && !error && !isLoading && (
            <div style={styles.emptyState}>
              <p style={styles.emptyText}>
                Enter a query to search for product or order related information.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
    </>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    boxShadow: shadows.base,
    border: `1px solid ${colors.border}`,
    flexShrink: 0,
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    backgroundColor: `${colors.info}10`,
    userSelect: 'none' as const,
    gap: spacing.md,
  },
  headerContent: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
    cursor: 'pointer',
  },
  icon: {
    fontSize: typography.fontSize.lg,
  },
  title: {
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.semibold as any,
    color: colors.text,
    margin: 0,
  },
  badge: (color: string) => ({
    fontSize: typography.fontSize.xs,
    color,
    backgroundColor: colors.surface,
    padding: '2px 8px',
    borderRadius: borderRadius.sm,
    border: `1px solid ${color}`,
  }),
  expandIcon: {
    fontSize: typography.fontSize.sm,
    color: colors.textLight,
  },
  content: {
    padding: spacing.md,
    // No overflow - resizes to content
  },
  queryBox: {
    display: 'flex',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  input: {
    flex: 1,
    padding: spacing.sm,
    fontSize: typography.fontSize.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: borderRadius.sm,
    outline: 'none',
    fontFamily: typography.fontFamily.primary,
  },
  button: (disabled: boolean) => ({
    padding: `${spacing.sm} ${spacing.md}`,
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.medium as any,
    color: colors.surface,
    backgroundColor: disabled ? colors.border : colors.primary,
    border: 'none',
    borderRadius: borderRadius.sm,
    cursor: disabled ? 'not-allowed' : 'pointer',
    whiteSpace: 'nowrap' as const,
  }),
  errorBox: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.sm,
    marginBottom: spacing.md,
    backgroundColor: `${colors.error}10`,
    border: `1px solid ${colors.error}`,
    borderRadius: borderRadius.sm,
  },
  errorIcon: {
    fontSize: typography.fontSize.base,
  },
  errorText: {
    fontSize: typography.fontSize.sm,
    color: colors.error,
  },
  suggestionsList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
  },
  suggestionCard: {
    padding: spacing.md,
    backgroundColor: colors.background,
    border: `1px solid ${colors.border}`,
    borderRadius: borderRadius.sm,
  },
  suggestionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  suggestionTitle: {
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.semibold as any,
    color: colors.text,
    margin: 0,
  },
  relevanceScore: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.medium as any,
    color: colors.success,
    backgroundColor: `${colors.success}10`,
    padding: '2px 6px',
    borderRadius: borderRadius.sm,
  },
  suggestionContent: {
    fontSize: typography.fontSize.sm,
    color: colors.text,
    lineHeight: 1.6,
    marginBottom: spacing.sm,
    // Note: Cannot use CSS pseudo-selectors (:first-child, :last-child) in React inline styles
    // ReactMarkdown has reasonable default margins for child elements
  },
  suggestionSource: {
    fontSize: typography.fontSize.xs,
    color: colors.info,
    textDecoration: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
  },
  emptyState: {
    padding: spacing.lg,
    textAlign: 'center' as const,
    backgroundColor: colors.background,
    borderRadius: borderRadius.sm,
  },
  emptyText: {
    fontSize: typography.fontSize.sm,
    color: colors.textLight,
    lineHeight: 1.6,
  },
  toolUsed: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
    padding: `${spacing.xs} ${spacing.sm}`,
    backgroundColor: `${colors.info}10`,
    borderRadius: borderRadius.sm,
    border: `1px solid ${colors.info}`,
  },
  toolUsedLabel: {
    fontSize: typography.fontSize.xs,
    fontWeight: typography.fontWeight.medium as any,
    color: colors.info,
    whiteSpace: 'nowrap' as const,
  },
  toolUsedValue: {
    fontSize: typography.fontSize.xs,
    color: colors.text,
    fontFamily: 'monospace',
  },
  progressContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.xs,
    marginBottom: spacing.md,
    padding: spacing.sm,
    backgroundColor: `${colors.info}05`,
    borderRadius: borderRadius.sm,
    border: `1px solid ${colors.border}`,
  },
  progressMessage: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    padding: `${spacing.xs} ${spacing.sm}`,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.sm,
    borderLeft: `3px solid ${colors.info}`,
  },
  toggleContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  mcpNotConfiguredText: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    fontStyle: 'italic' as const,
    whiteSpace: 'nowrap' as const,
  },
  toggleLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    cursor: 'pointer',
    userSelect: 'none' as const,
  },
  toggleCheckbox: {
    display: 'none',
  },
  toggleSwitch: (checked: boolean) => ({
    position: 'relative' as const,
    width: '44px',
    height: '24px',
    backgroundColor: checked ? colors.success : colors.border,
    borderRadius: '12px',
    transition: 'background-color 0.2s',
    display: 'inline-block',
  }),
  toggleSlider: (checked: boolean) => ({
    position: 'absolute' as const,
    top: '3px',
    left: checked ? '23px' : '3px',
    width: '18px',
    height: '18px',
    backgroundColor: colors.surface,
    borderRadius: '50%',
    transition: 'left 0.2s',
    boxShadow: shadows.sm,
  }),
  toggleText: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.medium as any,
    color: colors.text,
    whiteSpace: 'nowrap' as const,
  },
  listeningBanner: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: spacing.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
    backgroundColor: `${colors.success}10`,
    border: `1px solid ${colors.success}`,
    borderRadius: borderRadius.sm,
  },
  listeningIcon: {
    fontSize: typography.fontSize.lg,
    lineHeight: 1,
  },
  listeningText: {
    flex: 1,
    fontSize: typography.fontSize.sm,
    color: colors.text,
    lineHeight: typography.lineHeight.normal,
  },
  listeningSubtext: {
    fontSize: typography.fontSize.xs,
    color: colors.textLight,
    fontStyle: 'italic' as const,
  },
  ratingContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceHover,
    borderRadius: borderRadius.sm,
    border: `1px solid ${colors.border}`,
  },
  ratingLabel: {
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.medium as any,
    color: colors.text,
  },
  ratingButtons: {
    display: 'flex',
    gap: spacing.sm,
  },
  ratingButton: (isSelected: boolean, type: 'up' | 'down') => ({
    display: 'flex',
    alignItems: 'center',
    gap: spacing.xs,
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.fontSize.sm,
    fontWeight: typography.fontWeight.medium as any,
    color: isSelected
      ? (type === 'up' ? colors.success : colors.error)
      : colors.text,
    backgroundColor: isSelected
      ? (type === 'up' ? `${colors.success}15` : `${colors.error}15`)
      : colors.surface,
    border: `1px solid ${
      isSelected
        ? (type === 'up' ? colors.success : colors.error)
        : colors.border
    }`,
    borderRadius: borderRadius.sm,
    cursor: isSelected ? 'not-allowed' : 'pointer',
    transition: 'all 0.2s',
    opacity: isSelected ? 1 : 0.8,
    '&:hover': {
      opacity: isSelected ? 1 : 1,
      backgroundColor: isSelected
        ? (type === 'up' ? `${colors.success}15` : `${colors.error}15`)
        : colors.surfaceHover,
    },
    '&:disabled': {
      cursor: 'not-allowed',
      opacity: 0.6,
    },
  }),
};
