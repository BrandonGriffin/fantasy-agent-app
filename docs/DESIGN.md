# Design decisions

## Fresh repo instead of rewriting history
**Decision:** Started a new repo rather than scrubbing the old fantasyhistory history.
**Why:** The old repo was never made to be public so it had credentials in its history and 4 commits; a clean start was simpler and safer than git filter-repo.
**Tradeoff:** Lost the old commit history (kept locally as an archive).

## FastAPI for the backend
**Decision:** Build the API with FastAPI rather than Django.
**Why:** Deliberately chosen to contrast with my Django experience: async-first, type-driven validation and OpenAPI out of the box. The API mostly aggregates external sources, so Django's admin and auth aren't needed.
**Tradeoff:** No batteries included; ORM, migrations and auth are choices I have to make and wire up myself.

## uv and src layout
**Decision:** Manage the Python version, venv, dependencies and lockfile with uv; package code lives in `src/fantasy_api`.
**Why:** One fast tool with a committed lockfile. The src layout means tests import the installed package, not whatever happens to be on the working directory path.
**Tradeoff:** uv is newer and less universal than pip/Poetry; contributors need it installed.

## Settings: optional secrets, unset means disabled
**Decision:** Config via pydantic-settings; every credential is `SecretStr | None`, and a source with unset credentials is disabled rather than an error.
**Why:** Secrets are masked in repr, logs and JSON dumps. The app, tests and demo run with no credentials at all.
**Tradeoff:** A misconfigured source fails quietly (it just disappears) instead of failing at startup. Plan: log which sources are enabled at startup.

## App factory with no module-level app
**Decision:** `create_app(settings)` is the only entry point; there is no module-level `app`.
**Why:** Importing `fantasy_api.main` reads no config, so tests (which inject `Settings(_env_file=None)`) never touch the real `.env`, and future startup work (DB pools, HTTP clients) only runs when an app is actually built.
**Tradeoff:** `fastapi dev` (fastapi-cli 0.0.32) can't load factories, so the dev server runs via `uvicorn fantasy_api.main:create_app --factory --reload`.

## Postgres replaces Firebase (planned, Phase 6)
**Decision:** Store league history in Postgres instead of Firebase.
**Why:** Removes the Firebase service-account key entirely, history queries are relational, and Postgres fits the Docker Compose / Kubernetes roadmap.
**Tradeoff:** I own the schema, migrations and hosting. Once Firebase is gone, revoke the old key in GCP.

## DraftKings and Underdog are optional
**Decision:** The DraftKings and Underdog adapters use my session credentials, are off by default, and tests and the demo use sanitized recorded fixtures.
**Why:** Session-cookie auth can't be shared or used in CI, and fixtures must not contain other users' data.
**Tradeoff:** Those adapters are only tested against recorded fixtures, which can drift from the live APIs.
