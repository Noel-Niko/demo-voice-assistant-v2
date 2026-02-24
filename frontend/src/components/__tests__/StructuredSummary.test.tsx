/**
 * Unit tests for StructuredSummary component
 *
 * Tests focus on preventing the "300+ blank lines" bug where
 * excessive whitespace from backend causes unbounded container growth.
 */

import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import StructuredSummary from '../StructuredSummary';

describe('StructuredSummary', () => {
  test('collapses excessive whitespace to prevent empty space bug', () => {
    // Simulate backend summary with excessive newlines
    const summaryWithExcessiveNewlines = `
**CUSTOMER INTENT:**
Product needed


**KEY DETAILS:**
• Desktop computer
• Two monitors






**OPEN ITEMS:**
• Clarify specific needs



    `;

    const { container } = render(
      <StructuredSummary summaryText={summaryWithExcessiveNewlines} />
    );

    // Get the rendered content
    const renderedHTML = container.innerHTML;

    // The bug: whiteSpace: 'pre-wrap' would render all newlines as <br> or blank space
    // The fix: whiteSpace: 'normal' collapses consecutive whitespace

    // Test: Rendered height should be reasonable (not 300+ blank lines)
    // We can't test exact height, but we can check that excessive newlines
    // don't create massive gaps by checking that the container doesn't
    // have hundreds of line breaks or empty divs

    const lineBreaks = (renderedHTML.match(/<br>/g) || []).length;
    const emptyDivs = (renderedHTML.match(/<div[^>]*>\s*<\/div>/g) || []).length;

    // With 'pre-wrap', we'd have 10+ line breaks from the excessive newlines above
    // With 'normal', consecutive whitespace collapses to a single space
    expect(lineBreaks).toBeLessThan(10);
    expect(emptyDivs).toBeLessThan(10);
  });

  test('renders structured content without plain text fallback', () => {
    const structuredSummary = `
**CUSTOMER INTENT:**
Return keyboard

**KEY DETAILS:**
• Uncomfortable keyboard
• Wrist discomfort
    `;

    render(<StructuredSummary summaryText={structuredSummary} />);

    // Should parse and render sections, not fall back to plain text
    expect(screen.getByText(/CUSTOMER INTENT/i)).toBeInTheDocument();
    expect(screen.getByText(/Return keyboard/i)).toBeInTheDocument();
  });

  test('shows typewriter cursor when generating', () => {
    const { container } = render(
      <StructuredSummary
        summaryText="**CUSTOMER INTENT:** Product needed"
        isGenerating={true}
      />
    );

    // Should show cursor when generating
    expect(container.textContent).toContain('|');
  });

  test('hides typewriter cursor when not generating', () => {
    const { container } = render(
      <StructuredSummary
        summaryText="**CUSTOMER INTENT:** Product needed"
        isGenerating={false}
      />
    );

    // Cursor should not appear when not generating
    const cursorCount = (container.textContent?.match(/\|/g) || []).length;
    expect(cursorCount).toBe(0);
  });
});
