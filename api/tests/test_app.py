import pytest
from fastapi.testclient import TestClient

from fantasy_api.config import Settings


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("field", ["espn_s2", "espn_swid", "draftkings_cookie", "underdog_token"])
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
