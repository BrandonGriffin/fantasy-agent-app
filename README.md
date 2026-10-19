# About

- This app is mainly used to help keep track of exposures while drafting best ball teams, it is also used
for tracking historical data of other fantasy leagues I am in.

## Setup (run from `api/`)

```bash
uv sync                      # create .venv and install deps from uv.lock
cp .env.example .env         # then fill in only the sources you use
```

## Dev server

```bash
uv run uvicorn fantasy_api.main:create_app --factory --reload
```

Health check: `curl localhost:8000/healthz` -> `{"status":"ok"}`

## Checks (run from `api/`, not the repo root)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv lock --check
```

Auto-fix: `uv run ruff check . --fix` and `uv run ruff format .`


## Tests

```bash
uv run pytest tests
```