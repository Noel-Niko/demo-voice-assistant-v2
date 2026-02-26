/**
 * Structured Summary Component
 *
 * Renders parsed summary sections with diff-aware animations
 * - Fade-in for new bullets
 * - Highlight changed values
 * - Fixed section headers
 *
 * Source: project_research/summary-formatting-implementation-guide.md
 */

import { useEffect, useState, useRef } from 'react';
import { parseSummary, ParsedSummary, SummarySection } from '@/utils/summaryParser';
import { colors, spacing, typography } from '@/styles/design-tokens';

interface StructuredSummaryProps {
  summaryText: string;
  isGenerating?: boolean;
}

export default function StructuredSummary({
  summaryText,
  isGenerating = false,
}: StructuredSummaryProps) {
  const [parsed, setParsed] = useState<ParsedSummary>({ sections: [], raw: '' });
  const [newItems, setNewItems] = useState<Set<string>>(new Set());
  const prevParsedRef = useRef<ParsedSummary>({ sections: [], raw: '' });

  // Add global fade-in animation
  useEffect(() => {
    const style = document.createElement('style');
    style.innerHTML = `
      @keyframes fadeIn {
        from {
          opacity: 0;
          transform: translateY(-5px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
    `;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, []);

  useEffect(() => {
    const newParsed = parseSummary(summaryText);
    setParsed(newParsed);

    // Only track new items for fade-in when NOT actively streaming tokens.
    // During streaming, content changes on every token which would keep
    // items perpetually at opacity: 0.
    if (!isGenerating) {
      const prevContent = prevParsedRef.current.sections.flatMap(s => s.content);
      const currContent = newParsed.sections.flatMap(s => s.content);
      const newItemsSet = new Set(
        currContent.filter(item => !prevContent.includes(item))
      );
      setNewItems(newItemsSet);

      if (newItemsSet.size > 0) {
        setTimeout(() => setNewItems(new Set()), 1500);
      }
    } else {
      // Clear any lingering fade-in during streaming
      setNewItems(new Set());
    }

    prevParsedRef.current = newParsed;
  }, [summaryText, isGenerating]);

  // Fallback to plain text if no sections parsed
  if (parsed.sections.length === 0) {
    return (
      <div style={styles.plainText}>
        {summaryText || 'Waiting for conversation to begin...'}
        {isGenerating && <span style={styles.cursor}>|</span>}
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {parsed.sections.map((section, sectionIdx) => (
        <div key={`${section.header}-${sectionIdx}`} style={styles.section}>
          {/* Fixed Section Header */}
          <div style={styles.sectionHeader(section.type)}>
            {section.header}:
          </div>

          {/* Section Content */}
          <div style={styles.sectionContent}>
            {section.type === 'intent' ? (
              // CUSTOMER INTENT: Single line, no bullet
              <div
                style={{
                  ...styles.intentLine,
                  ...(newItems.has(section.content[0]) ? styles.fadeIn : {}),
                }}
              >
                {section.content[0]}
              </div>
            ) : (
              // Other sections: Bullets
              section.content.map((line, lineIdx) => (
                <div
                  key={`${section.header}-${lineIdx}`}
                  style={{
                    ...styles.bullet,
                    ...(newItems.has(line) ? styles.fadeIn : {}),
                    ...(section.type === 'actions' && lineIdx === section.content.length - 1
                      ? styles.latestAction
                      : {}),
                  }}
                >
                  <span style={styles.bulletMarker}>•</span>
                  <span style={styles.bulletText}>{line}</span>
                </div>
              ))
            )}
          </div>
        </div>
      ))}

      {isGenerating && <span style={styles.cursor}>|</span>}
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.md,
  },
  plainText: {
    whiteSpace: 'normal' as const,  // Collapses excessive whitespace/newlines
    lineHeight: 1.6,
    color: colors.text,
    fontFamily: typography.fontFamily.primary,
    fontSize: typography.fontSize.sm,
  },
  section: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.xs,
  },
  sectionHeader: (type: SummarySection['type']) => ({
    fontWeight: typography.fontWeight.bold as any,
    fontSize: typography.fontSize.sm,
    color:
      type === 'intent'
        ? colors.primary
        : type === 'open-items'
        ? colors.error
        : colors.textLight,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    marginBottom: spacing.xs,
  }),
  sectionContent: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: spacing.xs,
  },
  intentLine: {
    fontSize: typography.fontSize.base,
    fontWeight: typography.fontWeight.medium as any,
    color: colors.text,
    lineHeight: 1.5,
  },
  bullet: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: spacing.xs,
    fontSize: typography.fontSize.sm,
    lineHeight: 1.6,
    transition: 'opacity 1.5s ease-in, background-color 0.3s ease',
  },
  bulletMarker: {
    color: colors.primary,
    fontWeight: typography.fontWeight.bold as any,
    marginTop: '2px',
    flexShrink: 0,
  },
  bulletText: {
    color: colors.text,
    flex: 1,
  },
  latestAction: {
    // Subtle highlight for most recent action
    backgroundColor: `${colors.success}10`,
    marginLeft: `-${spacing.xs}`,
    padding: spacing.xs,
    borderRadius: '4px',
  },
  fadeIn: {
    animation: 'fadeIn 1.5s ease-in forwards',
  },
  cursor: {
    display: 'inline-block',
    marginLeft: spacing.xs,
    animation: 'blink 1s step-start infinite',
    fontWeight: typography.fontWeight.bold as any,
    color: colors.primary,
  },
};
