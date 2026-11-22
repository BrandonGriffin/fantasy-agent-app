from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from fantasy_api.best_ball.models import LeaderboardEntry
from fantasy_api.sources import draftkings
from fantasy_api.sources.draftkings import DraftKingsAuthError, DraftKingsResponseError

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_draftkings_client_sends_session_cookie() -> None:
    async with draftkings.draftkings_client(SecretStr("session=abc")) as client:
        assert client.headers["Cookie"] == "session=abc"


@pytest.mark.anyio
async def test_fetch_leaderboard_returns_body_text() -> None:
    body = load_fixture("draftkings_leaderboard_12.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == (
            "https://api.draftkings.com/scores/v1/megacontests/100000001/leaderboard"
        )
        return httpx.Response(200, text=body, headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await draftkings.fetch_leaderboard(client, "100000001") == body


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403])
async def test_fetch_leaderboard_reports_rejected_cookie(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DraftKingsAuthError, match=f"HTTP {status}"):
            await draftkings.fetch_leaderboard(client, "100000001")


@pytest.mark.anyio
@pytest.mark.parametrize("status", [404, 429, 503])
async def test_fetch_leaderboard_rejects_error_status(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DraftKingsResponseError, match=f"HTTP {status}"):
            await draftkings.fetch_leaderboard(client, "100000001")


@pytest.mark.anyio
@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_fetch_leaderboard_wraps_transport_errors(error: type[httpx.TransportError]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("simulated failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DraftKingsResponseError, match=error.__name__) as excinfo:
            await draftkings.fetch_leaderboard(client, "100000001")

    assert isinstance(excinfo.value.__cause__, error)


def test_parse_leaderboard_reads_every_entry_in_rank_order() -> None:
    leaderboard = draftkings.parse_leaderboard(load_fixture("draftkings_leaderboard_12.json"))

    assert leaderboard.contest_id == "100000001"
    assert [entry.rank for entry in leaderboard.entries] == list(range(1, 13))
    assert leaderboard.entries[0] == LeaderboardEntry(rank=1, username="user01", points=1608.28)
    assert leaderboard.entries[5] == LeaderboardEntry(rank=6, username="fixture-me", points=1313.88)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param('{"Leaderboard": []}', id="empty list"),
        pytest.param('{"Leaderboard": null}', id="null"),
    ],
)
def test_parse_leaderboard_rejects_leaderboard_without_entries(text: str) -> None:
    with pytest.raises(DraftKingsResponseError, match="no entries"):
        draftkings.parse_leaderboard(text)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("<!DOCTYPE html><html><title>Log In</title></html>", id="html page"),
        pytest.param("[]", id="not an object"),
        pytest.param('{"errorStatus": {"code": "SCO101"}}', id="missing leaderboard"),
        pytest.param('{"Leaderboard": [{"Rank": 1}]}', id="entry missing fields"),
    ],
)
def test_parse_leaderboard_rejects_unexpected_response(text: str) -> None:
    with pytest.raises(DraftKingsResponseError, match="not a leaderboard"):
        draftkings.parse_leaderboard(text)
