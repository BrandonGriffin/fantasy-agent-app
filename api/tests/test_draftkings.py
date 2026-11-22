import asyncio
import json
from collections.abc import Awaitable, Callable
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
async def test_draftkings_client_waits_for_slow_pages() -> None:
    async with draftkings.draftkings_client(SecretStr("session=abc")) as client:
        assert client.timeout == httpx.Timeout(20)


@pytest.mark.anyio
async def test_fetch_leaderboard_returns_body_text() -> None:
    body = load_fixture("draftkings_leaderboard_12.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == (
            "https://api.draftkings.com/scores/v1/megacontests/100000001/leaderboard"
            "?format=json&embed=leaderboard"
        )
        return httpx.Response(200, text=body, headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await draftkings.fetch_leaderboard(client, "100000001") == body


@pytest.mark.anyio
async def test_fetch_live_contests_returns_my_contests_page() -> None:
    page = load_fixture("draftkings_mycontests.html")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == "https://www.draftkings.com/mycontests"
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await draftkings.fetch_live_contests(client) == page


Fetch = Callable[[httpx.AsyncClient], Awaitable[str]]

FETCHES = [
    pytest.param(
        lambda client: draftkings.fetch_leaderboard(client, "100000001"), id="leaderboard"
    ),
    pytest.param(lambda client: draftkings.fetch_live_contests(client), id="live contests"),
]


@pytest.mark.anyio
@pytest.mark.parametrize("fetch", FETCHES)
@pytest.mark.parametrize("status", [401, 403])
async def test_fetch_reports_rejected_cookie(fetch: Fetch, status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DraftKingsAuthError, match=f"HTTP {status}"):
            await fetch(client)


@pytest.mark.anyio
@pytest.mark.parametrize("fetch", FETCHES)
@pytest.mark.parametrize("status", [404, 429, 503])
async def test_fetch_rejects_error_status(fetch: Fetch, status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DraftKingsResponseError, match=f"HTTP {status}"):
            await fetch(client)


@pytest.mark.anyio
@pytest.mark.parametrize("fetch", FETCHES)
@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_fetch_wraps_transport_errors(
    fetch: Fetch, error: type[httpx.TransportError]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("simulated failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DraftKingsResponseError, match=error.__name__) as excinfo:
            await fetch(client)

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


BEST_BALL_DRAFT_GROUPS = frozenset({900001, 900002})


def mycontests_page(live: str) -> str:
    return f"<html><script>var contests = {{ live: {live}, upcoming: [] }};</script></html>"


def test_parse_live_contests_returns_megacontest_ids() -> None:
    page = load_fixture("draftkings_mycontests.html")

    contest_ids = draftkings.parse_live_contests(page, BEST_BALL_DRAFT_GROUPS)

    assert contest_ids == ["100000001", "100000002"]


def test_parse_live_contests_skips_other_draft_groups() -> None:
    page = load_fixture("draftkings_mycontests.html")

    contest_ids = draftkings.parse_live_contests(page, frozenset({900002}))

    assert contest_ids == ["100000001"]


def test_parse_live_contests_lists_each_league_once() -> None:
    entry = '{"MegaContestId": 7, "DraftGroupId": 900001, "PrizeIds": []}'
    page = mycontests_page(f"[{entry}, {entry}]")

    assert draftkings.parse_live_contests(page, BEST_BALL_DRAFT_GROUPS) == ["7"]


def test_parse_live_contests_reports_sign_in_page() -> None:
    page = "<!DOCTYPE html><html><title>Log In</title></html>"

    with pytest.raises(DraftKingsAuthError, match="no contests"):
        draftkings.parse_live_contests(page, BEST_BALL_DRAFT_GROUPS)


@pytest.mark.parametrize(
    "live",
    [
        pytest.param("[{not json", id="invalid json"),
        pytest.param('{"MegaContestId": 7}', id="not a list"),
        pytest.param('[{"MegaContestId": 7}]', id="contest missing fields"),
    ],
)
def test_parse_live_contests_rejects_unexpected_contests(live: str) -> None:
    with pytest.raises(DraftKingsResponseError, match="could not read the live contests"):
        draftkings.parse_live_contests(mycontests_page(live), BEST_BALL_DRAFT_GROUPS)


def leaderboard_response(contest_id: str) -> str:
    entry = {"MegaContestKey": contest_id, "Rank": 1, "UserName": "fixture-me", "FantasyPoints": 1}
    return json.dumps({"Leaderboard": [entry]})


def requested_contest(request: httpx.Request) -> str:
    return request.url.path.split("/")[-2]


@pytest.mark.anyio
async def test_fetch_leaderboards_returns_leaderboards_in_contest_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=leaderboard_response(requested_contest(request)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetched = await draftkings.fetch_leaderboards(client, ["3", "1", "2"], max_concurrent=2)

    assert [leaderboard.contest_id for leaderboard in fetched.leaderboards] == ["3", "1", "2"]
    assert fetched.failed == {}


@pytest.mark.anyio
async def test_fetch_leaderboards_keeps_the_rest_when_a_contest_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        contest_id = requested_contest(request)
        if contest_id == "2":
            return httpx.Response(503)
        if contest_id == "3":
            return httpx.Response(200, text='{"Leaderboard": []}')
        return httpx.Response(200, text=leaderboard_response(contest_id))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetched = await draftkings.fetch_leaderboards(client, ["1", "2", "3"], max_concurrent=2)

    assert [leaderboard.contest_id for leaderboard in fetched.leaderboards] == ["1"]
    assert fetched.failed == {
        "2": "DraftKings returned HTTP 503",
        "3": "leaderboard has no entries",
    }


@pytest.mark.anyio
async def test_fetch_leaderboards_stops_when_the_cookie_is_rejected() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(requested_contest(request))
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DraftKingsAuthError):
            await draftkings.fetch_leaderboards(client, ["1", "2", "3"], max_concurrent=1)

    assert requested == ["1"]


@pytest.mark.anyio
async def test_fetch_leaderboards_limits_requests_in_flight() -> None:
    in_flight = 0
    most_in_flight = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, most_in_flight
        in_flight += 1
        most_in_flight = max(most_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, text=leaderboard_response(requested_contest(request)))

    contest_ids = [str(n) for n in range(10)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetched = await draftkings.fetch_leaderboards(client, contest_ids, max_concurrent=3)

    assert most_in_flight == 3
    assert len(fetched.leaderboards) == 10
