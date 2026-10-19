# fantasy-api

FastAPI backend for the fantasy agent app. See the repo root `CLAUDE.md` for conventions.

Run everything from this directory:

- Dev server: `uv run uvicorn fantasy_api.main:create_app --factory --reload`
- Checks: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src tests`, `uv run pytest`

Copy `.env.example` to `.env` and fill in only the sources you use; unset credentials disable that source.
