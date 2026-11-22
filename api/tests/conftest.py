import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fantasy_api.config import Settings
from fantasy_api.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # _env_file=None skips the .env file, but OS env vars are still read.
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


SAVED_LIVE_CONTESTS = [
    {"MegaContestId": 100000001, "DraftGroupId": 900002},
    {"MegaContestId": 100000002, "DraftGroupId": 900001},
]


@pytest.fixture
def saved_draftkings_db(tmp_path: Path) -> Path:
    """A copy of the old app's dk_responses table, filled from the sanitized fixtures."""

    db_path = tmp_path / "bestball.db"
    rows = [
        ("live-contests", json.dumps(SAVED_LIVE_CONTESTS)),
        ("league-100000001", (FIXTURES / "draftkings_leaderboard_12.json").read_text("utf-8")),
        ("league-100000002", (FIXTURES / "draftkings_leaderboard_6.json").read_text("utf-8")),
    ]
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute(
            "CREATE TABLE dk_responses (cache_key TEXT PRIMARY KEY, body TEXT, fetched_at INTEGER)"
        )
        db.executemany("INSERT INTO dk_responses VALUES (?, ?, 0)", rows)
    return db_path
