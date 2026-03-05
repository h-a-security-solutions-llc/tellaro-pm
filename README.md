# Tellaro PM

AI-orchestration-first project management platform. AI agents are the primary workforce — humans direct, review, and approve.

## Architecture

| Component | Stack |
|---|---|
| **Backend** | Python 3.12+, FastAPI, OpenSearch, Redis |
| **Frontend** | Vue 3, TypeScript, Vite, Pinia |
| **Agent** | Python asyncio daemon, manages Claude Code |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 22+
- Docker & Docker Compose (for OpenSearch)

### 1. Start OpenSearch

```bash
docker compose up -d
```

OpenSearch runs on port 9200 by default. Override with `OPENSEARCH_PORT`:

```bash
OPENSEARCH_PORT=9201 docker compose up -d
```

Optionally include OpenSearch Dashboards:

```bash
docker compose --profile dashboards up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cp .env.example .env       # edit as needed
python -m tellaro_pm.main
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Agent (optional)

```bash
cd agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # set AGENT_NAME and AGENT_TOKEN
tellaro-agent --agent-name "my-agent"
```

### Configuration

All settings use hierarchical resolution (highest priority first):

| Priority | Backend | Agent |
|---|---|---|
| 1 | Docker/K8s Secrets (`/run/secrets/KEY`) | CLI arguments (`--flag`) |
| 2 | Environment variables / `.env` | Docker/K8s Secrets |
| 3 | Default values | Environment variables / `.env` |
| 4 | — | Default values |

See `.env.example` in each package for available settings.

### Running Tests

```bash
# Backend
cd backend && pytest

# Agent
cd agent && pytest

# Frontend unit tests
cd frontend && npm run test:unit

# Frontend E2E tests
cd frontend && npm run test:e2e
```

### Linting & Type Checking

```bash
# Backend / Agent
ruff check src/ tests/
pyright src/

# Frontend
npm run lint
npm run type-check
```

## Documentation

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full roadmap and architecture.
