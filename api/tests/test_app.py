from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fantasy_api.config import Settings


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "field",
    [
        "espn_s2",
        "espn_swid",
        "draftkings_cookie",
        "underdog_token",
        "google_sheet_publish_id",
        "google_sheet_playoff_id",
    ],
)
def test_secrets_do_not_leak(field: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(field.upper(), "secret-key")
    settings = Settings(_env_file=None)

    secret = getattr(settings, field)
    assert secret is not None and secret.get_secret_value() == "secret-key"
    assert "secret-key" not in repr(settings)
    assert "secret-key" not in str(settings)
    assert "secret-key" not in settings.model_dump_json()


def test_secrets_can_be_read_deliberately() -> None:
    settings = Settings(_env_file=None, espn_s2="secret-key")

    assert settings.espn_s2 is not None
    assert settings.espn_s2.get_secret_value() == "secret-key"


def test_draftkings_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.draftkings_cookie is None
    assert settings.draftkings_username is None
    assert settings.draftkings_draft_group_ids == []
    assert settings.draftkings_max_concurrent_requests == 4
    assert settings.draftkings_replay_db is None


def test_draftkings_draft_group_ids_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAFTKINGS_DRAFT_GROUP_IDS", "[146136, 141336]")

    assert Settings(_env_file=None).draftkings_draft_group_ids == [146136, 141336]


@pytest.mark.parametrize("limit", [0, -1])
def test_draftkings_max_concurrent_requests_must_be_positive(limit: int) -> None:
    with pytest.raises(ValidationError, match="draftkings_max_concurrent_requests"):
        Settings(_env_file=None, draftkings_max_concurrent_requests=limit)


def test_blank_env_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRAFTKINGS_COOKIE", "")
    monkeypatch.setenv("DRAFTKINGS_USERNAME", "")

    settings = Settings(_env_file=None)

    assert settings.draftkings_cookie is None
    assert settings.draftkings_username is None


def test_draftkings_replay_db_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="draftkings_replay_db"):
        Settings(_env_file=None, draftkings_replay_db=tmp_path / "missing.db")


def test_playoff_sheet_settings_default_to_unset() -> None:
    settings = Settings(_env_file=None)

    assert settings.google_sheet_playoff_id is None
    assert settings.google_service_account_file is None


def test_google_service_account_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="google_service_account_file"):
        Settings(_env_file=None, google_service_account_file=tmp_path / "missing.json")
