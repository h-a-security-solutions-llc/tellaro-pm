# Tellaro PM — Claude Code Instructions

## Project Structure

Monorepo with three packages:

- `backend/` — FastAPI backend (Python 3.12+, Poetry)
- `frontend/` — Vue 3 + TypeScript + Vite
- `agent/` — Rust agent daemon (Cargo)

## Running Commands

- **Backend uses Poetry.** Always use `poetry run python` (not bare `python`) when running scripts.
  - Backend: `cd backend && poetry run python -m tellaro_pm.main`
  - Tests: `cd backend && poetry run pytest`
- **Frontend uses npm.** `cd frontend && npm run dev`
- **Rust agent uses Cargo.** `cd agent && cargo run -- <subcommand>`

## Infrastructure

- **OpenSearch** runs in Docker (`docker compose up -d`). Port configured via `OPENSEARCH_PORT` env var (default: 9200, dev: 9210).
- **No Docker for the app itself** — local dev uses `npm run dev` and `poetry run`.

## Configuration

Hierarchical resolution: Docker/K8s Secrets > ENV (`.env`) > Defaults.

- Backend settings: `backend/src/tellaro_pm/core/settings.py`
- Rust agent config: `agent/src/config.rs` (saved to `~/.config/tellaro-pm-agent/config.json`)
- Never commit `.env` files (they contain secrets)

## TQL (Tellaro Query Language)

**Always use TQL for search/filter queries.** Do not hand-build OpenSearch DSL for user-facing queries.

- Backend: `from tql import TQL, OpenSearchBackend` (import is `tql`, not `tellaro_query_language`)
- Backend helper: `from tellaro_pm.core.tql_service import tql_to_opensearch`
- Frontend: `import { TqlInput } from '@tellaro/tql/vue'`
- Frontend table: Use `TellaroTable` component with `fieldSchema` prop for TQL intellisense
- Full docs: `docs/TQL.md`

## GitHub Integration

- **GitHub App** for server-to-server read operations (repos, issues, sync)
- **User's local `gh` CLI** for user-attributed write actions (PRs, comments) via the agent
- Setup docs: `docs/GITHUB_APP_SETUP.md`
