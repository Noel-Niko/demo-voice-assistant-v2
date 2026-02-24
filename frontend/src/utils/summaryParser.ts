/**
 * Summary Parser Utility
 *
 * Parses structured summary format from backend into sections
 * Format: **SECTION_HEADER:** followed by content
 *
 * Source: project_research/summary-formatting-implementation-guide.md
 */

export interface SummarySection {
  header: string;
  content: string[];
  type: 'intent' | 'details' | 'actions' | 'open-items';
}

export interface ParsedSummary {
  sections: SummarySection[];
  raw: string;
}

/**
 * Parse structured summary text into sections
 *
 * @param summaryText - Raw summary text with **SECTION:** headers
 * @returns Parsed sections with type and content
 */
export function parseSummary(summaryText: string): ParsedSummary {
  if (!summaryText || summaryText.trim().length === 0) {
    return { sections: [], raw: summaryText };
  }

  const sections: SummarySection[] = [];

  // Split on section headers: **HEADER:**
  const headerRegex = /\*\*([A-Z\s]+):\*\*/g;
  const parts = summaryText.split(headerRegex);

  // parts[0] is text before first header (usually empty)
  // parts[1] is first header name, parts[2] is its content
  // parts[3] is second header name, parts[4] is its content, etc.

  for (let i = 1; i < parts.length; i += 2) {
    const headerName = parts[i].trim();
    const content = parts[i + 1] ? parts[i + 1].trim() : '';

    if (!content) continue;

    // Parse content into lines (bullets)
    const lines = content
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .map(line => {
        // Remove bullet markers (•, -, *)
        return line.replace(/^[•\-*]\s*/, '');
      })
      .filter(line => line.length > 0);

    // Determine section type
    let type: SummarySection['type'] = 'details';
    if (headerName.includes('INTENT')) {
      type = 'intent';
    } else if (headerName.includes('DETAILS')) {
      type = 'details';
    } else if (headerName.includes('ACTIONS')) {
      type = 'actions';
    } else if (headerName.includes('OPEN')) {
      type = 'open-items';
    }

    sections.push({
      header: headerName,
      content: lines,
      type,
    });
  }

  return {
    sections,
    raw: summaryText,
  };
}

/**
 * Calculate similarity ratio between two strings (Jaro-Winkler-like approximation)
 *
 * @param str1 - First string
 * @param str2 - Second string
 * @returns Similarity ratio between 0 and 1
 */
function calculateSimilarity(str1: string, str2: string): number {
  // Quick exact match check
  if (str1 === str2) return 1;

  // Normalize strings for comparison
  const s1 = str1.toLowerCase().trim();
  const s2 = str2.toLowerCase().trim();

  // Calculate longest common subsequence length as similarity metric
  const longer = s1.length > s2.length ? s1 : s2;
  const shorter = s1.length > s2.length ? s2 : s1;

  if (longer.length === 0) return 1;

  // Count matching characters (order-preserving)
  let matches = 0;
  let shorterIdx = 0;

  for (let i = 0; i < longer.length && shorterIdx < shorter.length; i++) {
    if (longer[i] === shorter[shorterIdx]) {
      matches++;
      shorterIdx++;
    }
  }

  return matches / longer.length;
}

/**
 * Diff two parsed summaries to identify changes
 *
 * @param previous - Previous parsed summary
 * @param current - Current parsed summary
 * @returns Object indicating new, changed, and removed items per section
 */
export function diffSummaries(previous: ParsedSummary, current: ParsedSummary): {
  [sectionHeader: string]: {
    new: string[];
    changed: string[];
    removed: string[];
  };
} {
  const diff: {
    [sectionHeader: string]: {
      new: string[];
      changed: string[];
      removed: string[];
    };
  } = {};

  const SIMILARITY_THRESHOLD = 0.6; // 60% similarity = likely an edit

  // Build map of previous sections
  const prevSectionMap = new Map(
    previous.sections.map(s => [s.header, s.content])
  );

  // Compare current sections to previous
  current.sections.forEach(currSection => {
    const prevContent = prevSectionMap.get(currSection.header) || [];

    const newLines: string[] = [];
    const changedLines: string[] = [];
    const removedLines: string[] = [];
    const matchedPrevLines = new Set<string>();

    // Find new and changed lines
    currSection.content.forEach(currLine => {
      if (prevContent.includes(currLine)) {
        // Exact match - not new or changed
        matchedPrevLines.add(currLine);
      } else {
        // Check if this is a modification of an existing line
        let bestMatch: string | null = null;
        let bestSimilarity = 0;

        prevContent.forEach(prevLine => {
          if (!matchedPrevLines.has(prevLine)) {
            const similarity = calculateSimilarity(currLine, prevLine);
            if (similarity > bestSimilarity && similarity >= SIMILARITY_THRESHOLD) {
              bestSimilarity = similarity;
              bestMatch = prevLine;
            }
          }
        });

        if (bestMatch) {
          // This line is a modification of an existing line
          changedLines.push(currLine);
          matchedPrevLines.add(bestMatch);
        } else {
          // This is a completely new line
          newLines.push(currLine);
        }
      }
    });

    // Find removed lines (lines in previous that weren't matched)
    prevContent.forEach(prevLine => {
      if (!matchedPrevLines.has(prevLine)) {
        removedLines.push(prevLine);
      }
    });

    diff[currSection.header] = {
      new: newLines,
      changed: changedLines,
      removed: removedLines,
    };
  });

  return diff;
}
