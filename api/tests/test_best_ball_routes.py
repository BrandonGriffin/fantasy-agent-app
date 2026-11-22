from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from fantasy_api.best_ball.routes import draftkings_http
from fantasy_api.config import Settings
from fantasy_api.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"

LEADERBOARD_FIXTURES = {
    "100000001": "draftkings_leaderboard_12.json",
    "100000002": "draftkings_leaderboard_6.json",
}

Handler = Callable[[httpx.Request], httpx.Response]


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def draftkings_settings() -> Settings:
    return Settings(
        _env_file=None,
        draftkings_cookie="session=abc",
        draftkings_draft_group_ids=[900001, 900002],
    )


def fake_draftkings(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/mycontests":
        return httpx.Response(200, text=load_fixture("draftkings_mycontests.html"))

    contest_id = request.url.path.split("/")[-2]
    return httpx.Response(200, text=load_fixture(LEADERBOARD_FIXTURES[contest_id]))


def client_with_draftkings(handler: Handler) -> TestClient:
    app = create_app(draftkings_settings())

    async def mock_draftkings_http() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client

    app.dependency_overrides[draftkings_http] = mock_draftkings_http
    return TestClient(app)


def test_leaderboards_returns_each_best_ball_contest() -> None:
    with client_with_draftkings(fake_draftkings) as client:
        response = client.get("/best-ball/leaderboards")

    assert response.status_code == 200
    body = response.json()
    assert [board["contest_id"] for board in body["leaderboards"]] == ["100000001", "100000002"]
    assert [len(board["entries"]) for board in body["leaderboards"]] == [12, 6]
    assert body["leaderboards"][0]["entries"][5] == {
        "rank": 6,
        "username": "fixture-me",
        "points": 1313.88,
    }
    assert body["failed"] == {}


def test_leaderboards_lists_contests_that_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "100000002" in request.url.path:
            return httpx.Response(503)
        return fake_draftkings(request)

    with client_with_draftkings(handler) as client:
        body = client.get("/best-ball/leaderboards").json()

    assert [board["contest_id"] for board in body["leaderboards"]] == ["100000001"]
    assert body["failed"] == {"100000002": "DraftKings returned HTTP 503"}


def test_leaderboards_reads_saved_responses_by_default(saved_draftkings_db: Path) -> None:
    settings = Settings(
        _env_file=None,
        draftkings_replay_db=saved_draftkings_db,
        draftkings_draft_group_ids=[900001, 900002],
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/best-ball/leaderboards")

    assert response.status_code == 200
    body = response.json()
    assert [board["contest_id"] for board in body["leaderboards"]] == ["100000001", "100000002"]


def test_leaderboards_needs_saved_responses_by_default(client: TestClient) -> None:
    response = client.get("/best-ball/leaderboards")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "No saved DraftKings data: set DRAFTKINGS_REPLAY_DB, or pass live=true"
    }


def test_live_leaderboards_need_a_draftkings_cookie(saved_draftkings_db: Path) -> None:
    settings = Settings(_env_file=None, draftkings_replay_db=saved_draftkings_db)

    with TestClient(create_app(settings)) as client:
        response = client.get("/best-ball/leaderboards", params={"live": True})

    assert response.status_code == 503
    assert response.json() == {"detail": "DraftKings is not configured: set DRAFTKINGS_COOKIE"}


def test_leaderboards_reports_a_rejected_cookie() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!DOCTYPE html><html><title>Log In</title></html>")

    with client_with_draftkings(handler) as client:
        response = client.get("/best-ball/leaderboards")

    assert response.status_code == 502
    assert "session cookie has probably expired" in response.json()["detail"]


def test_leaderboards_reports_draftkings_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with client_with_draftkings(handler) as client:
        response = client.get("/best-ball/leaderboards")

    assert response.status_code == 502
    assert response.json() == {"detail": "DraftKings returned HTTP 500"}
