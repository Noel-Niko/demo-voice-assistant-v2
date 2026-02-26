# Transcript & Summary Streaming - Frontend

Next.js frontend application for real-time transcript streaming and AI-powered summarization.

## Features

- **Real-time Transcript Streaming** - WebSocket-based live transcript display
- **AI Summary Generation** - Token-by-token streaming with typewriter effect
- **Custom Design System** - UI using design tokens
- **Auto-Reconnection** - Resilient WebSocket with exponential backoff
- **Responsive Layout** - Two-panel desktop, stacked mobile
- **12-Factor Compliant** - Config from environment, stateless frontend

## Prerequisites

- Node.js 20+ (recommended)
- npm or yarn
- Backend server running on port 8765

## Quick Start

### 1. Install Dependencies

```bash
npm install
```

### 2. Configure Environment

Create `.env.local` from the example:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` if your backend uses different URLs:

```env
NEXT_PUBLIC_API_URL=http://localhost:8765
NEXT_PUBLIC_WS_URL=ws://localhost:8765
```

### 3. Start Development Server

```bash
npm run dev
```

The application will be available at: **http://localhost:3000**

### 4. Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── layout.tsx         # Root layout
│   │   └── page.tsx           # Main conversation page
│   ├── components/            # React components
│   │   ├── TranscriptViewer.tsx      # Left panel - transcript display
│   │   ├── SummaryViewer.tsx         # Right panel - AI summaries
│   │   ├── ConnectionStatus.tsx      # WebSocket status indicator
│   │   └── MCPSuggestionsBox.tsx     # MCP integration placeholder
│   ├── hooks/                 # Custom React hooks
│   │   └── useWebSocket.ts    # WebSocket with auto-reconnect
│   ├── types/                 # TypeScript definitions
│   │   ├── conversation.ts    # API response types
│   │   └── websocket.ts       # WebSocket event types
│   └── styles/                # Styling
│       ├── design-tokens.ts  # Design system tokens
│       └── globals.css        # Global styles
├── package.json
├── tsconfig.json
├── next.config.js
└── README.md
```

## WebSocket Events

The frontend handles these real-time events:

- `connection.established` - Initial connection confirmation
- `transcript.batch` - Batch of transcript lines (10 lines/batch)
- `summary.start` - Summary generation begins
- `summary.token` - Individual summary tokens (typewriter effect)
- `summary.complete` - Summary generation finished
- `streaming.complete` - All transcript streaming finished

## Design Tokens

Uses design system colors:
- **Primary**: #C8102E (buttons, headers)
- **Agent Blue**: #1B6EC2 (agent messages)
- **Customer Green**: #0D7C3F (customer messages)

## Troubleshooting

### Backend Connection Errors

If you see "Failed to create conversation":

1. Verify backend is running: `curl http://localhost:8765/api/health`
2. Check port configuration in `.env.local`
3. Review browser console for detailed errors

### WebSocket Disconnects

The WebSocket will automatically reconnect with exponential backoff:
- Attempt 1: 1 second delay
- Attempt 2: 2 seconds delay
- Attempt 3: 4 seconds delay
- ...up to 30 seconds max

### Port Conflicts

If port 3000 is in use, specify a different port:

```bash
PORT=3001 npm run dev
```

## MCP Integration

The `MCPSuggestionsBox` component connects to any MCP-compatible server for tool augmentation:
- **Configuration**: Set `MCP_INGRESS_URL` environment variable on the backend
- **Features**: Auto-discovers tools and provides product/order suggestions based on conversation context
- **Details**: See the main README's [MCP Integration](../README.md#mcp-integration-bring-your-own-server) section

## Development Commands

```bash
# Development server with hot reload
npm run dev

# Production build
npm run build

# Start production server
npm start

# Type checking
npm run type-check

# Linting
npm run lint
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8765` | Backend API URL |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8765` | WebSocket server URL |

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## License

MIT
