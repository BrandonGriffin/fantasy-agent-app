# Fantasy Agent App

Rebuild of my fantasy football app (originally Vue, then a partial React port with a Node/Express server) as a
portfolio project: a React frontend, a FastAPI backend that aggregates ESPN, Sleeper,
Fleaflicker, DraftKings and Underdog data, and an AI agent layer on top.

## Working rules
- Never commit secrets. Credentials live in `api/.env` (gitignored); `.env.example`
  lists names only.
- Small, reviewable commits. Every phase ends with passing checks and updated docs.
- Record design decisions in `docs/DESIGN.md`.

## Layout
- `api/` – FastAPI service (uv, src layout, package `fantasy_api`)
- `web/` – React 19 + Vite + TypeScript (not started)
- `agent/` – hand-written tool-calling agent, triage, evals (not started)
- `docs/` – DESIGN.md and other docs

## Commands (run from `api/`)
- Dev server: `uv run uvicorn fantasy_api.main:create_app --factory --reload`
- Checks: `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy src tests` · `uv run pytest`

## Conventions
- App factory: `create_app(settings)`; no module-level `app`, so importing reads no config.
  Tests build the app with explicit settings.
- Config via pydantic-settings; every credential is `SecretStr | None`. A source whose
  credentials are unset is disabled, not an error.
- Tests use `Settings(_env_file=None)` and never read the real `.env`; an autouse fixture
  also clears credential env vars from the process.
- mypy strict on `src` and `tests`.
- Agent: keep the hand-written tool loop; no agent frameworks.

## Data sources
- ESPN (cookie auth), Sleeper and Fleaflicker (public APIs), Google Sheet (drafted teams).
- DraftKings and Underdog use my session credentials: optional, off by default, never
  required for tests or the demo.
- Test fixtures and demo data must not contain other users' data.

## Roadmap
1. Foundation: repo, API skeleton, tooling
2. Source adapters with recorded-fixture tests (best-ball endpoints first)
3. Web foundation: Vite + TS, design system, generated API client, best-ball pages
4. Feature parity: matchup dashboard, league history / title belt, guillotine
5. Docker Compose (web, api, postgres, redis)
6. Postgres history + ingestion + agent/triage (port loop from sheet-agent)
7. Evals (accuracy, token cost, latency)
8. Kubernetes (Helm on kind: Deployment, CronJob, probes, HPA)
9. CI/CD (GitHub Actions: lint, test, image build + scan, evals)
10. Observability (Prometheus, Grafana, OpenTelemetry)
11. Terraform on AWS
12. MCP server for league tools
Stretch: rewrite the ingestion worker in Go.
