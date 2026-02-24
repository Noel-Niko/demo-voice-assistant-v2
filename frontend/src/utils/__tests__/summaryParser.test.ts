/**
 * Unit tests for summaryParser utility
 *
 * Tests parsing of structured summary format and diff algorithm
 */

import { describe, test, expect } from 'vitest';
import { parseSummary, diffSummaries } from '../summaryParser';

describe('parseSummary', () => {
  test('parses empty string', () => {
    const result = parseSummary('');
    expect(result.sections).toEqual([]);
    expect(result.raw).toBe('');
  });

  test('parses single section with single line', () => {
    const input = '**CUSTOMER INTENT:** Return keyboard';
    const result = parseSummary(input);

    expect(result.sections).toHaveLength(1);
    expect(result.sections[0]).toEqual({
      header: 'CUSTOMER INTENT',
      content: ['Return keyboard'],
      type: 'intent',
    });
    expect(result.raw).toBe(input);
  });

  test('parses multiple sections', () => {
    const input = `**CUSTOMER INTENT:**
Return keyboard

**KEY DETAILS:**
• Uncomfortable keyboard
• Wrist discomfort

**ACTIONS TAKEN:**
Processed return request`;

    const result = parseSummary(input);

    expect(result.sections).toHaveLength(3);
    expect(result.sections[0].header).toBe('CUSTOMER INTENT');
    expect(result.sections[0].type).toBe('intent');
    expect(result.sections[1].header).toBe('KEY DETAILS');
    expect(result.sections[1].type).toBe('details');
    expect(result.sections[2].header).toBe('ACTIONS TAKEN');
    expect(result.sections[2].type).toBe('actions');
  });

  test('removes bullet markers from content lines', () => {
    const input = `**KEY DETAILS:**
• First item
- Second item
* Third item
Fourth item (no bullet)`;

    const result = parseSummary(input);

    expect(result.sections[0].content).toEqual([
      'First item',
      'Second item',
      'Third item',
      'Fourth item (no bullet)',
    ]);
  });

  test('filters out empty lines', () => {
    const input = `**CUSTOMER INTENT:**

Return keyboard


Another line

`;

    const result = parseSummary(input);

    expect(result.sections[0].content).toEqual([
      'Return keyboard',
      'Another line',
    ]);
  });

  test('identifies section types correctly', () => {
    const input = `**CUSTOMER INTENT:**
Intent text

**KEY DETAILS:**
Details text

**ACTIONS TAKEN:**
Actions text

**OPEN ITEMS:**
Open items text

**OTHER SECTION:**
Other text`;

    const result = parseSummary(input);

    expect(result.sections[0].type).toBe('intent');
    expect(result.sections[1].type).toBe('details');
    expect(result.sections[2].type).toBe('actions');
    expect(result.sections[3].type).toBe('open-items');
    expect(result.sections[4].type).toBe('details'); // Default fallback
  });

  test('handles section with no content', () => {
    const input = `**CUSTOMER INTENT:**

**KEY DETAILS:**
Some content`;

    const result = parseSummary(input);

    // Section with no content should be skipped
    expect(result.sections).toHaveLength(1);
    expect(result.sections[0].header).toBe('KEY DETAILS');
  });

  test('handles text before first header', () => {
    const input = `Some preamble text

**CUSTOMER INTENT:**
Intent text`;

    const result = parseSummary(input);

    // Preamble should be ignored
    expect(result.sections).toHaveLength(1);
    expect(result.sections[0].header).toBe('CUSTOMER INTENT');
  });
});

describe('diffSummaries', () => {
  test('identifies new items in section', () => {
    const previous = parseSummary(`**KEY DETAILS:**
• Item A
• Item B`);

    const current = parseSummary(`**KEY DETAILS:**
• Item A
• Item B
• Item C`);

    const diff = diffSummaries(previous, current);

    expect(diff['KEY DETAILS'].new).toEqual(['Item C']);
    expect(diff['KEY DETAILS'].removed).toEqual([]);
  });

  test('identifies removed items in section', () => {
    const previous = parseSummary(`**KEY DETAILS:**
• Item A
• Item B
• Item C`);

    const current = parseSummary(`**KEY DETAILS:**
• Item A
• Item B`);

    const diff = diffSummaries(previous, current);

    expect(diff['KEY DETAILS'].new).toEqual([]);
    expect(diff['KEY DETAILS'].removed).toEqual(['Item C']);
  });

  test('handles new section added', () => {
    const previous = parseSummary(`**CUSTOMER INTENT:**
Intent text`);

    const current = parseSummary(`**CUSTOMER INTENT:**
Intent text

**KEY DETAILS:**
• New detail`);

    const diff = diffSummaries(previous, current);

    expect(diff['CUSTOMER INTENT']).toBeDefined();
    expect(diff['KEY DETAILS']).toBeDefined();
    expect(diff['KEY DETAILS'].new).toEqual(['New detail']);
  });

  test('handles empty previous summary', () => {
    const previous = parseSummary('');
    const current = parseSummary(`**CUSTOMER INTENT:**
Intent text`);

    const diff = diffSummaries(previous, current);

    expect(diff['CUSTOMER INTENT'].new).toEqual(['Intent text']);
    expect(diff['CUSTOMER INTENT'].removed).toEqual([]);
  });

  test('detects changed lines with fuzzy matching', () => {
    // Changed lines should be detected when similarity >= 60%
    const previous = parseSummary(`**KEY DETAILS:**
• Customer needs desktop computer`);

    const current = parseSummary(`**KEY DETAILS:**
• Customer needs desktop computer with monitor`);

    const diff = diffSummaries(previous, current);

    // Should detect as changed (similar but modified)
    expect(diff['KEY DETAILS'].changed).toContain('Customer needs desktop computer with monitor');
    expect(diff['KEY DETAILS'].removed).toEqual([]);
    expect(diff['KEY DETAILS'].new).toEqual([]);
  });

  test('treats completely different lines as removed + new', () => {
    const previous = parseSummary(`**KEY DETAILS:**
• Keyboard return`);

    const current = parseSummary(`**KEY DETAILS:**
• Monitor purchase`);

    const diff = diffSummaries(previous, current);

    // Too different (< 60% similarity) - should be removed + new
    expect(diff['KEY DETAILS'].changed).toEqual([]);
    expect(diff['KEY DETAILS'].removed).toContain('Keyboard return');
    expect(diff['KEY DETAILS'].new).toContain('Monitor purchase');
  });

  test('handles identical summaries', () => {
    const previous = parseSummary(`**CUSTOMER INTENT:**
Intent text

**KEY DETAILS:**
• Detail A
• Detail B`);

    const current = parseSummary(`**CUSTOMER INTENT:**
Intent text

**KEY DETAILS:**
• Detail A
• Detail B`);

    const diff = diffSummaries(previous, current);

    expect(diff['CUSTOMER INTENT'].new).toEqual([]);
    expect(diff['CUSTOMER INTENT'].removed).toEqual([]);
    expect(diff['KEY DETAILS'].new).toEqual([]);
    expect(diff['KEY DETAILS'].removed).toEqual([]);
  });
});
