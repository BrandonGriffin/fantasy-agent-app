from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from fantasy_api.config import Settings
from fantasy_api.main import create_app


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
