/**
 * Grainger Design System Tokens
 *
 * Extracted from code_examples/acw-summary-panel.jsx
 * Maintains brand consistency across the application
 */

export const colors = {
  // Primary Brand Color
  primary: '#C8102E',        // Grainger Red

  // Speaker Colors
  agent: '#1B6EC2',          // Blue for agent messages
  customer: '#0D7C3F',       // Green for customer messages
  unknown: '#666666',        // Gray for unknown speaker

  // UI Colors
  background: '#F5F5F5',     // Light gray background
  surface: '#FFFFFF',        // White surface/cards
  surfaceHover: '#F0F0F0',   // Light gray hover state
  text: '#333333',           // Dark gray text
  textLight: '#666666',      // Medium gray text
  border: '#CCCCCC',         // Light gray borders
  borderLight: '#E0E0E0',    // Very light gray borders

  // Status Colors
  success: '#0D7C3F',        // Green
  warning: '#F5A623',        // Orange
  error: '#D32F2F',          // Red
  info: '#1B6EC2',           // Blue

  // Connection Status
  connected: '#0D7C3F',      // Green
  disconnected: '#D32F2F',   // Red
  connecting: '#F5A623',     // Orange
} as const;

export const typography = {
  fontFamily: {
    primary: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    mono: '"Courier New", Courier, monospace',
  },
  fontSize: {
    xs: '12px',
    sm: '14px',
    base: '16px',
    lg: '18px',
    xl: '20px',
    '2xl': '24px',
  },
  fontWeight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  lineHeight: {
    tight: 1.2,
    normal: 1.5,
    relaxed: 1.75,
  },
} as const;

export const spacing = {
  xs: '4px',
  sm: '8px',
  md: '16px',
  lg: '24px',
  xl: '32px',
  '2xl': '48px',
  '3xl': '64px',
} as const;

export const borderRadius = {
  none: '0',
  sm: '4px',
  md: '8px',
  lg: '12px',
  full: '9999px',
} as const;

export const shadows = {
  none: 'none',
  sm: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
  base: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
  md: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
  lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
} as const;

export const breakpoints = {
  mobile: '480px',
  tablet: '768px',
  desktop: '1024px',
  wide: '1280px',
} as const;

export const zIndex = {
  base: 0,
  dropdown: 1000,
  sticky: 1020,
  fixed: 1030,
  modalBackdrop: 1040,
  modal: 1050,
  popover: 1060,
  tooltip: 1070,
} as const;
