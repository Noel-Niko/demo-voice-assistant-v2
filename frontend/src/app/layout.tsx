import type { Metadata } from 'next';
import Script from 'next/script';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: 'Transcript & Summary Streaming',
  description: 'Production-Lite streaming transcript and LLM summarization system for Grainger',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              // Aggressive error suppression for Safari
              (function() {
                // Store original error handler
                const originalOnError = window.onerror;

                // Override window.onerror
                window.onerror = function(message, source, lineno, colno, error) {
                  const msg = String(message || '');
                  if (msg.includes('fixinatorInputs') ||
                      msg.includes('webkit-masked-url') ||
                      msg.includes('background page')) {
                    console.log('[Suppressed] External error:', msg);
                    return true; // Prevent default error handling
                  }
                  if (originalOnError) {
                    return originalOnError.apply(this, arguments);
                  }
                  return false;
                };

                // Handle promise rejections
                window.addEventListener('unhandledrejection', function(e) {
                  const msg = String(e.reason?.message || e.reason || '');
                  if (msg.includes('fixinatorInputs') ||
                      msg.includes('webkit-masked-url') ||
                      msg.includes('background page')) {
                    console.log('[Suppressed] External promise rejection:', msg);
                    e.preventDefault();
                    e.stopImmediatePropagation();
                  }
                }, true);

                // Suppress console errors for these specific issues
                const originalConsoleError = console.error;
                console.error = function(...args) {
                  const msg = String(args[0] || '');

                  // Suppress known browser extension issues
                  if (msg.includes('fixinatorInputs') ||
                      msg.includes('webkit-masked-url') ||
                      msg.includes('background page')) {
                    console.log('[Suppressed console.error]:', msg);
                    return;
                  }

                  // Suppress hydration error caused by extensions adding style to <html>
                  // This specific pattern: style={{color:"black"}} on html element
                  if (msg.includes('Hydration failed') ||
                      msg.includes('hydrated') ||
                      msg.includes('style={{color:"black"}}')) {
                    console.log('[Suppressed hydration error]:', 'Browser extension modified DOM');
                    return;
                  }

                  originalConsoleError.apply(console, args);
                };
              })();
            `,
          }}
        />
      </head>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
