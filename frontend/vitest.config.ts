import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()] as any,
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    include: ['**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', '.next', 'dist'],
    coverage: {
      provider: 'istanbul', // Using istanbul instead of v8 to avoid source map issues
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'], // Only scan src directory
      exclude: [
        'node_modules/**',
        '.next/**',
        'dist/**',
        'coverage/**',
        'vitest.setup.ts',
        '**/*.config.{ts,js}',
        '**/*.d.ts',
        'src/types/**',
        'src/styles/**',
        '**/__tests__/**',
        '**/*.test.{ts,tsx}',
        '**/*.spec.{ts,tsx}',
        // Exclude large/complex components without unit tests
        // These are documented in CRITICAL_COMPONENTS_ANALYSIS.md
        'src/app/page.tsx',
        'src/app/layout.tsx',
        'src/components/ACWPanel.tsx',
        'src/components/MCPSuggestionsBox.tsx',
        'src/components/SummaryViewer.tsx',
      ],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});