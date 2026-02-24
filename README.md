This repo is a "production-ready" real-time transcript streaming and LLM summarization system for customer service conversations.
It builds on the initial work done in the [demo_voice_assistant](https://github.com/Noel-Niko/demo_voice_assistant) repo.

### PRESENTATION:  [noel_nosse_staff_swe_assessment_presentation.pptx](https://github.com/user-attachments/files/25507521/noel_nosse_staff_swe_assessment_presentation.pptx)

_____
![transcription](https://github.com/user-attachments/assets/2e2352d0-4955-41c9-a7b6-835e7fb842b1)
_____

_____
![Auto_and_Manual_Suggestions](https://github.com/user-attachments/assets/db0cdaa3-d8cd-454a-ad60-fbc8104ef58b)
_____

_____
![End_Of_Call](https://github.com/user-attachments/assets/7c22253b-92ac-4195-b200-995b7879158d)
_____

_____
![dashboard](https://github.com/user-attachments/assets/f81e3467-30c8-46d8-a4a9-20bdfd9a4bd4)
_____



# Transcript & Summary Streaming System

**Production-Lite** real-time transcript streaming and LLM summarization system for customer service conversations.

Demonstrates production-ready architecture with event-driven design, async processing, and real-time WebSocket streaming.

## ✅ Assessment Requirements - Complete Verification

| Requirement | Status | How Met | Enhancement |
|-------------|--------|---------|-------------|
| **Live-updating transcript (10 lines/5 sec)** | ✅ | Reads `Option2_data_file.txt`, streams via WebSocket | Word-by-word streaming with utterance detection |
| **LLM-generated summary** | ✅ | OpenAI GPT-3.5-turbo integration | Token streaming + version history |
| **Summary every 30 seconds** | ✅ | Periodic task with context preservation | Adjustable 5-120s via UI slider |
| **Summary streaming to browser** | ✅ | WebSocket events: `summary.token` streaming | Typewriter effect + auto-reconnect |
| **Clear run instructions** | ✅ | README Quick Start section | `make prod` automation + troubleshooting |
| **Design documentation** | ✅ | Architecture diagrams + implementation details | 15+ ADRs in `ARCHITECTURAL_DECISIONS.md` |
| **Use shared repository** | ✅ | Complete codebase with git history | Clean commits with feature branches |

### 🚀 Exceeded Requirements

| Additional Feature | Status | Implementation |
|-------------------|--------|----------------|
| **Testing Suite** | ✅ | 407 tests (unit, integration, frontend) with 85%+ coverage |
| **ACW Automation** | ✅ | AI-assisted disposition, compliance checking, CRM extraction |
| **Metrics Dashboard** | ✅ | Standalone analytics app at `localhost:8766` |
| **Production Architecture** | ✅ | Event-driven, 12-factor app, AWS Secrets Manager |
| **Full Audit Trail** | ✅ | Database tracking of all AI interactions and agent edits |
| **NLP Enhancement** | ✅ | spaCy for utterance boundaries + semantic completeness |
| **API Documentation** | ✅ | Auto-generated Swagger UI at `/docs` |

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
  - [Swagger UI](#swagger-ui)
  - [REST Endpoints](#rest-endpoints)
  - [WebSocket Protocol](#websocket-protocol)
- [Testing](#testing)
  - [Run All Tests](#run-all-tests)
  - [Test Coverage](#test-coverage)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Tunable Parameters](#tunable-parameters)
- [Word-by-Word Streaming](#word-by-word-streaming)
- [Development](#development)
  - [Code Style](#code-style)
- [Production Considerations](#production-considerations)
- [Troubleshooting](#troubleshooting)

---

## Overview

This system simulates a production customer service environment where:
1. **Transcripts stream in real-time** - Words appear as they're spoken (simulating Genesys Cloud speech-to-text)
2. **AI generates rolling summaries** - Every 30 seconds, an LLM creates updated summaries with context
3. **Agents see live updates** - WebSocket pushes updates to the UI instantly

Built with **FastAPI** (backend) and **Next.js** (frontend) following **12-factor app** principles.

---

## Features

### Core Capabilities
- ✅ **Real-time transcript streaming** - Words appear at natural speaking rate (2.5 words/second)
- ✅ **Word-by-word updates** - Simulates production Genesys interim/final transcription results
- ✅ **Rolling LLM summaries** - OpenAI GPT-3.5 generates context-aware summaries every 30s
- ✅ **Typewriter effect** - Summaries stream token-by-token for natural feel
- ✅ **Version history** - Previous summaries preserved with click-to-expand
- ✅ **Dynamic pacing** - Adjustable summary frequency (5-120 seconds)
- ✅ **Event-driven architecture** - Decoupled services via in-memory event bus
- ✅ **After-Call Work (ACW) automation** - AI-assisted disposition, compliance checking, CRM field extraction
- ✅ **Phase-driven 3-panel UI** - Clean transitions between active-call and ACW phases
- ✅ **Full test coverage** - 89 tests (19 repository unit tests, 30 API integration tests, 40 service unit tests)

### Technical Highlights
- ✅ **Async/await throughout** - Non-blocking I/O for high concurrency
- ✅ **WebSocket auto-reconnect** - Graceful handling of connection issues
- ✅ **SQLite + aiosqlite** - Async database operations
- ✅ **Grainger design system** - Production-ready UI components
- ✅ **12-factor compliant** - Environment-based config, stateless design
- ✅ **TDD methodology** - Tests written first, high confidence

---

## Architecture

### System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                      │
│  ┌──────────────────┐          ┌───────────────────────────┐    │
│  │ TranscriptViewer │◄─────────┤   WebSocket Client        │    │
│  │  (newest first)  │          │   (auto-reconnect)        │    │
│  └──────────────────┘          └───────────────────────────┘    │
│  ┌──────────────────┐                      ▲                    │
│  │  SummaryViewer   │                      │                    │
│  │  (typewriter)    │                      │ WebSocket          │
│  └──────────────────┘                      │                    │
└─────────────────────────────────────────────┼───────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Backend (FastAPI)                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Event Bus (In-Memory)                  │  │
│  └────▲────────────▲────────────▲────────────▲──────────────┘   │
│       │            │            │            │                  │
│  ┌────┴────┐  ┌───┴─────┐  ┌───┴────┐  ┌───┴──────┐           │
│  │  Word   │  │Transcript│  │Summary │  │ WebSocket│           │
│  │Streamer │  │ Streamer │  │Generator│ │  Handler │           │
│  │(interim)│  │(batches) │  │(OpenAI) │  │(broadcast)│          │
│  └────┬────┘  └───┬─────┘  └───┬────┘  └──────────┘           │
│       │           │            │                                │
│       └───────────┴────────────┴──────────────────────────┐     │
│                                                            ▼    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            ConversationRepository (SQLite)                │  │
│  │  - transcript_lines (line_id, is_final, text)            │   │
│  │  - summaries (version, summary_text)                     │   │
│  │  - conversations (id, status, timestamps)                │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Patterns
- **Event-Driven**: Services communicate via publish/subscribe (Observer pattern)
- **Repository Pattern**: Clean separation of business logic and data access
- **Single Responsibility**: Each service has one job
- **Async/Await**: Non-blocking operations throughout
- **Observer Pattern**: Real-time updates via WebSocket subscriptions

---

## Quick Start

### Prerequisites

**System requirements:**
- Python 3.12+ (check: `python3 --version`)
- [uv](https://github.com/astral-sh/uv) package manager (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js 20+ with npm (check: `node --version`)
- AWS CLI with Grainger MLOps access¹
- jq (install: `brew install jq`)

After these are installed, `uv sync` will handle all Python dependencies automatically.

<sup>¹ New to Grainger MLOps? See [CLI Access Setup](https://grainger.atlassian.net/wiki/spaces/MLOPS/pages/163515400694/3.+CLI+Access) and [Team Onboarding](https://grainger.atlassian.net/wiki/spaces/MLOPS/pages/164573151615/Team+Onboarding) for AWS setup.</sup>

### Backend Setup

```bash
cd backend
uv sync
```

**Verify setup:**
```bash
# Run tests (uses mock credentials, no AWS needed)
uv run pytest -v

# Expected: 237+ tests passing
```

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# No additional configuration needed - uses localhost:8765 defaults
```

### Running the Application

#### Terminal 1 - Backend

```bash
cd backend

# Step 1: Get AWS credentials (Digital Assistant Domain team members)
assume your prod MLOps credentials I.e.:
assume aad-mlops-prod-digitalassistantdo

# ✅ Verify credentials:
aws sts get-caller-identity
# Should show your AWS identity

# Step 2: Start backend (auto-fetches secrets from AWS Secrets Manager)
make prod 
(QA available but not recommended due to data quality)
```

**Expected output:**
```
🔐 Loading environment variables for: prod
🔸 Fetching digitalassistantdomain/prod/openai_key_list...
✅ Exported: OPENAI_API_KEY
✅ Exported: MCP_SECRET_KEY
🔑 Starting server on port 8765...
INFO:     Uvicorn running on http://0.0.0.0:8765
```

**If AWS credentials don't work (not on Digital Assistant Domain team):**
- `make prod` will prompt you to manually enter API keys
- Request keys from: **noel.nosse@grainger.com**
- The server will start after you enter them

Backend runs at: `http://localhost:8765`

---

#### Terminal 2 - Frontend

**Choose based on your needs:**

**Option A: Production Build (Recommended for observing/testing)**
```bash
cd frontend

# Install dependencies
npm install

# Build and start production server
npm run build
npm start
```

**Expected output:**
```
   ▲ Next.js 16.1.6
   - Local:        http://localhost:3000
   - Network:      http://0.0.0.0:3000

 ✓ Ready in 1.8s
```

**Option B: Development Server (For making code changes)**
```bash
cd frontend

# Install dependencies
npm install

# Start development server with hot reload
npm run dev
```

**Expected output:**
```
   ▲ Next.js 16.1.6
   - Local:        http://localhost:3000

 ✓ Ready in 2.1s
```

Frontend runs at: `http://localhost:3000` for both options

---

#### Terminal 3 - Metrics Dashboard (Optional)

The metrics dashboard provides analytics across all completed conversations. It is a standalone app that reads JSON export files from `/tmp/`. No AWS credentials required.

```bash
cd backend

# Start dashboard
make dashboard
```

Dashboard runs at: `http://localhost:8766`

**First-time setup:** Click the **"Sync from DB"** button in the dashboard header to export all existing conversations from the database. This requires the backend (Terminal 1) to be running. After the initial sync, new conversations are automatically exported when completed via the UI.

**What the dashboard shows:**
- **KPI cards**: Total conversations, avg duration, avg ACW %, total AI cost, FCR rate
- **Conversation table**: Sortable columns with per-conversation metrics
- **AI cost by model**: Breakdown across gpt-3.5-turbo, gpt-4.1-mini, gpt-4o, etc.
- **Compliance detection**: AI accuracy rate, agent override rate
- **Listening mode**: Sessions, auto queries, opportunities detected
- **Summary metrics**: Generation count, agent edit rate

Data auto-refreshes every 30 seconds.

| Setting | Default | Description |
|---------|---------|-------------|
| `DASHBOARD_PORT` | `8766` | Dashboard server port |
| `DASHBOARD_DATA_DIR` | `/tmp` | Directory containing export JSON files |
| `DASHBOARD_MAIN_APP_URL` | `http://localhost:8765` | Backend URL for "Sync from DB" button |

---

### Testing

#### Backend Tests

```bash
cd backend

# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Expected: 237+ tests passing
```

#### Frontend Tests

```bash
cd frontend

# Run all tests (watch mode)
npm run test

# Run once (CI mode)
npm run test:run

# Run with coverage report
npm run test:coverage

# Run with interactive UI
npm run test:ui
```

**Expected output:**
```
✓ src/utils/__tests__/summaryParser.test.ts (15)
✓ src/hooks/__tests__/useTranscriptStream.test.ts (9)
✓ src/components/__tests__/TranscriptViewer.test.tsx (18)
✓ src/components/__tests__/InteractionHistory.test.tsx (13)
✓ src/components/__tests__/ConnectionStatus.test.tsx (14)
✓ src/components/__tests__/CallMetaCard.test.tsx (12)
✓ src/components/__tests__/CallerInfoCard.test.tsx (11)
✓ src/components/__tests__/StructuredSummary.test.tsx (4)
✓ src/hooks/__tests__/useWebSocket.simplified.test.ts (5)

Test Files  9 passed (9)
     Tests  101 passed (101)
```

**Coverage report:** `frontend/coverage/index.html` (open in browser after running `test:coverage`)

**Test Coverage:**
- ✅ Utilities: summaryParser (fuzzy diff matching)
- ✅ Hooks: useTranscriptStream, useWebSocket
- ✅ Components: 7 presentational components (CallerInfoCard, CallMetaCard, ConnectionStatus, InteractionHistory, TranscriptViewer, StructuredSummary)
- ⚠️ Complex components (ACWPanel, MCPSuggestionsBox, page.tsx) documented in `frontend/CRITICAL_COMPONENTS_ANALYSIS.md`

**Frontend Coverage Summary (Istanbul):**

![Frontend Test Coverage](images/fe-test-cvg.png)

---

#### Open Browser

Navigate to: **http://localhost:3000**

**✅ What you should see:**
1. Empty transcript panel on page load
2. After 2 seconds, transcript lines start streaming (newest at top)
3. After 30 seconds, first AI summary generates with typewriter effect

---

## API Documentation

### Swagger UI

FastAPI **automatically generates** interactive API documentation:

| Documentation Type | URL | Description |
|-------------------|-----|-------------|
| **Swagger UI** | [`http://localhost:8765/docs`](http://localhost:8765/docs) | Interactive API explorer - test endpoints directly |
| **ReDoc** | [`http://localhost:8765/redoc`](http://localhost:8765/redoc) | Clean, readable API reference |
| **OpenAPI Schema** | [`http://localhost:8765/openapi.json`](http://localhost:8765/openapi.json) | Raw OpenAPI 3.0 specification (JSON) |

#### Using Swagger UI

1. Start the backend: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8765`
2. Open browser: [`http://localhost:8765/docs`](http://localhost:8765/docs)
3. Expand any endpoint (e.g., `POST /api/conversations`)
4. Click "Try it out"
5. Click "Execute" to test the endpoint
6. See real responses with schema validation

### REST Endpoints

#### Create Conversation
```http
POST /api/conversations
```

Creates a new conversation and starts transcript streaming.

**Response:**
```json
{
  "conversation_id": "uuid",
  "status": "active",
  "started_at": "2026-02-20T10:00:00Z"
}
```

#### Get Conversation State
```http
GET /api/conversations/{conversation_id}
```

Retrieves current conversation state including all transcript lines and summaries.

**Response:**
```json
{
  "conversation_id": "uuid",
  "status": "active",
  "transcript_lines": [...],
  "summaries": [...],
  "started_at": "2026-02-20T10:00:00Z",
  "ended_at": null
}
```

#### Update Summary Frequency
```http
PUT /api/conversations/{conversation_id}/summary-interval?interval_seconds=60
```

Dynamically adjusts summary generation frequency (5-120 seconds).

**Response:**
```json
{
  "status": "updated",
  "interval": 60,
  "conversation_id": "uuid"
}
```

#### Health Check
```http
GET /api/health
```

Returns service health status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-20T10:00:00Z"
}
```

### WebSocket Protocol

Connect to: `ws://localhost:8765/api/ws/{conversation_id}`

#### Events Sent by Server

**Connection Established:**
```json
{
  "event_type": "connection.established",
  "data": {
    "conversation_id": "uuid",
    "message": "Connected to conversation stream"
  }
}
```

**Word Interim Update (Real-time Streaming):**
```json
{
  "event_type": "transcript.word.interim",
  "data": {
    "conversation_id": "uuid",
    "line_id": "line-1",
    "speaker": "agent",
    "partial_text": "Hello I need",
    "is_final": false,
    "timestamp": "2026-02-20T10:00:00Z",
    "sequence_number": 1
  }
}
```

**Word Final Update:**
```json
{
  "event_type": "transcript.word.final",
  "data": {
    "conversation_id": "uuid",
    "line_id": "line-1",
    "speaker": "agent",
    "text": "Hello I need help with my order",
    "is_final": true,
    "timestamp": "2026-02-20T10:00:00Z",
    "sequence_number": 1
  }
}
```

**Transcript Batch (Legacy - for backward compatibility):**
```json
{
  "event_type": "transcript.batch",
  "data": {
    "conversation_id": "uuid",
    "batch_number": 1,
    "total_batches": 23,
    "lines": [...]
  }
}
```

**Summary Start:**
```json
{
  "event_type": "summary.start",
  "data": {
    "conversation_id": "uuid",
    "version": 1
  }
}
```

**Summary Token (Streaming):**
```json
{
  "event_type": "summary.token",
  "data": {
    "conversation_id": "uuid",
    "version": 1,
    "token": "Hello"
  }
}
```

**Summary Complete:**
```json
{
  "event_type": "summary.complete",
  "data": {
    "conversation_id": "uuid",
    "version": 1,
    "summary_text": "Complete summary text..."
  }
}
```

**Streaming Complete:**
```json
{
  "event_type": "streaming.complete",
  "data": {
    "conversation_id": "uuid"
  }
}
```

---

## Testing

### Run All Tests

```bash
cd backend
uv run pytest -v
```

**Expected output:**
```
======================== 89 passed in 4.82s ========================
```

### Test Coverage

```bash
cd backend
uv run pytest --cov=app --cov-report=html
```

View coverage report: `backend/htmlcov/index.html`

**Coverage by Module:**
- `conversation_repository.py`: 95%
- `transcript_streamer.py`: 92%
- `summary_generator.py`: 88%
- `word_streamer.py`: 100%
- Overall: 85%+

### Test Categories

**Unit Tests** (`tests/unit/`):
- TranscriptParser (12 tests)
- TranscriptStreamer (10 tests)
- WordStreamer (13 tests)
- SummaryGenerator (7 tests)
- ConversationRepository (11 tests)

**Integration Tests** (`tests/integration/`):
- API endpoints (25 tests)
- 12-factor compliance (3 tests)
- Error handling (2 tests)

---

## Configuration

### Single Source of Truth

All configuration defaults are defined in **`backend/app/config.py`** (backend) and **hardcoded fallbacks** in frontend code. No `.env` files are used.

### Environment Variables

#### Backend - AWS Secrets Manager (Production Pattern)

**Secrets are automatically fetched from AWS Secrets Manager** when you run `make prod` or `make qa`.

**AWS Secrets Used:**
- `digitalassistantdomain/prod/openai_key_list` → Exports `OPENAI_API_KEY`
- `digitalassistantdomain/prod/mcp-secret` → Exports `MCP_SECRET_KEY`

**No .env files required.** If you're not on the Digital Assistant Domain team, `setup_env.sh` will prompt you to manually enter keys.

**Optional runtime overrides** (set in terminal before `make prod`):
```bash
export OPENAI_MODEL=gpt-4                    # Change model (default: gpt-3.5-turbo)
export SUMMARY_INTERVAL_SECONDS=60           # Summary frequency (default: 30s)
export TRANSCRIPT_WORDS_PER_SECOND=3.0       # Speaking rate (default: 2.5)
# DATABASE_URL auto-configured to backend/transcripts.db (absolute path)
# Override only for external database:
# export DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
```

#### Frontend (Optional)

Frontend uses hardcoded fallbacks (`localhost:8765`) for local development. Override only if needed:

```bash
# Set environment variables before starting frontend (if needed)
export NEXT_PUBLIC_API_URL=http://different-host:8080
export NEXT_PUBLIC_WS_URL=ws://different-host:8080
npm run dev
```

### Tunable Parameters

#### Summary Generation

**Frequency**: Adjust via UI slider or API
```bash
# Fast updates (for testing)
SUMMARY_INTERVAL_SECONDS=5

# Production default
SUMMARY_INTERVAL_SECONDS=30

# Slower updates (longer conversations)
SUMMARY_INTERVAL_SECONDS=60
```

#### Transcript Streaming

**Speaking Rate**: Change how fast words appear
```bash
# Faster (for demos)
TRANSCRIPT_WORDS_PER_SECOND=5.0

# Natural speaking rate (default)
TRANSCRIPT_WORDS_PER_SECOND=2.5

# Slower (for readability)
TRANSCRIPT_WORDS_PER_SECOND=1.5
```

---

## Word-by-Word Streaming

### Architecture

The system simulates production **Genesys Cloud** real-time transcription where speech-to-text results arrive **word-by-word**:

```
Demo (File-based):
File → WordStreamer → Interim Updates → Final Update

Production (Genesys):
Audio → Genesys STT → Interim Updates → Final Update
```

### How It Works

1. **Complete line read from file**: `"Hello I need help with my order"`
2. **WordStreamer splits into words**: `["Hello", "I", "need", "help", ...]`
3. **Emits interim updates**:
   - `"Hello"` (interim)
   - `"Hello I"` (interim)
   - `"Hello I need"` (interim)
   - ...
4. **Final update**: `"Hello I need help with my order"` (final)

### Database Schema

```sql
CREATE TABLE transcript_lines (
  id INTEGER PRIMARY KEY,
  conversation_id VARCHAR(36),
  line_id VARCHAR(100),          -- Tracks logical line across updates
  speaker VARCHAR(20),
  text TEXT,                      -- Partial or complete text
  is_final BOOLEAN DEFAULT FALSE, -- True when line is complete
  sequence_number INTEGER,
  timestamp DATETIME,
  added_at DATETIME
);

CREATE INDEX idx_line_id ON transcript_lines(line_id);
```

### Production Evolution Path

**Demo → Production Changes:**

| Aspect | Demo (File) | Production (Genesys) |
|--------|------------|---------------------|
| **Input Source** | Static file | Genesys WebSocket |
| **Data Format** | Complete lines | Partial results |
| **Trigger** | File read | Audio stream |
| **Timing** | Simulated (2.5 wps) | Real-time |
| **Backend Change** | Replace `TranscriptParser` | Add `GenesysConnector` |
| **Frontend Change** | None | Already handles interim/final |

**Key Files to Modify for Production:**
1. `backend/app/services/transcript_parser.py` → `genesys_connector.py`
2. `backend/app/services/transcript_streamer.py` → Wire to Genesys events
3. `backend/app/config.py` → Add `GENESYS_WS_URL`, `GENESYS_API_KEY`

---

---

## Development

### Code Style

**Backend (Python):**
- **Style Guide**: PEP 8
- **Type Hints**: Required on all public functions
- **Docstrings**: Google style
- **Testing**: pytest with TDD
- **Linting**: ruff (future)

**Frontend (TypeScript):**
- **Style Guide**: Next.js conventions
- **Type Safety**: Strict mode enabled
- **Components**: Functional with hooks
- **Styling**: Inline styles with design tokens


## Production Considerations

### From Demo → Production

**Replace:**
- ✅ File → Genesys WebSocket
- ✅ SQLite → PostgreSQL + Redis
- ✅ In-memory event bus → RabbitMQ/Kafka
- ✅ Single process → Kubernetes deployment

**Add:**
- ✅ Authentication (OAuth2/JWT)
- ✅ Rate limiting
- ✅ Monitoring (Prometheus/Grafana)
- ✅ Logging aggregation (ELK/Datadog)
- ✅ Secrets management (Vault/AWS Secrets)
- ✅ Load balancing
- ✅ Auto-scaling
- ✅ Database migrations (Alembic)

**See [`DESIGN.md`](./DESIGN.md) for complete production architecture**

### 12-Factor App Compliance

✅ **Codebase**: Single repo, multiple deployments
✅ **Dependencies**: Explicitly declared (`pyproject.toml`, `package.json`)
✅ **Config**: Defaults in code, secrets from environment (Makefile/AWS)
✅ **Backing services**: Swappable via config
✅ **Build, release, run**: Separate stages
✅ **Processes**: Stateless, horizontally scalable
✅ **Port binding**: Self-contained HTTP/WS
✅ **Concurrency**: Process-based scaling
✅ **Disposability**: Fast startup, graceful shutdown
✅ **Dev/prod parity**: Same backing services
✅ **Logs**: Event streams to stdout
✅ **Admin processes**: Same codebase

---

## Troubleshooting

### Backend Won't Start

**Error**: `assume: command not found`
```bash
# Solution: Install AWS CLI and MLOps tooling
# See Prerequisites footnote or https://grainger.atlassian.net/wiki/spaces/MLOPS/pages/163515400694/3.+CLI+Access
```

**Error**: `No valid AWS credentials found!`
```bash
# Solution 1: Run assume command
assume aad-mlops-prod-digitalassistantdo
aws sts get-caller-identity  # Verify it worked

# Then restart
make prod

# Solution 2: Not on Digital Assistant Domain team?
# Just run make prod anyway - it will prompt for manual key entry
# Request keys from: noel.nosse@grainger.com
```

**Error**: `Could not fetch AWS secret: digitalassistantdomain/prod/openai_key_list`
```bash
# This is expected if you're not on the Digital Assistant Domain team
# setup_env.sh will prompt you to enter keys manually
# Request keys from: noel.nosse@grainger.com
```

**Error**: `Port 8765 already in use`
```bash
# Solution: Kill existing process
kill -9 $(lsof -ti :8765)
make prod
```

**Error**: `OPENAI_API_KEY not set`
```bash
# Solution: Always use make prod (not direct uvicorn)
cd backend
make prod  # This handles secret fetching

# For tests (no AWS needed):
uv run pytest -v
```

**Error**: `ModuleNotFoundError: No module named 'app'`
```bash
# Solution: Ensure you're in backend/ directory and dependencies are installed
cd backend
uv sync
make prod
```

### Frontend Issues

**Error**: Black screen in browser
```bash
# Solution: Hard refresh
# Mac: Cmd+Shift+R
# Windows: Ctrl+Shift+R
```

**Error**: WebSocket connection failed
```bash
# Solution: Ensure backend is running on correct port
curl http://localhost:8765/api/health
```

**Error**: "Fixinator" or browser extension errors
```bash
# Solution: Disable extensions or use incognito mode
```

### Summary Not Generating

**Check**: OpenAI API key is valid
```bash
# Test directly
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Check**: Transcripts are streaming
```bash
# Should see transcript lines in UI within 5 seconds
```

**Check**: Backend logs
```bash
# Look for "summary_generator_initialized"
# and "periodic_summarization_started"
```

### Tests Failing

**Error**: `ImportError: cannot import name 'X'`
```bash
# Solution: Recreate virtualenv
cd backend
rm -rf .venv
uv sync
```

**Error**: Database locked
```bash
# Solution: Delete and recreate DB
rm backend/transcripts.db
uv run pytest -v
```
