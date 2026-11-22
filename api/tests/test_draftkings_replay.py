from pathlib import Path

import httpx
import pytest

from fantasy_api.sources import draftkings
from fantasy_api.sources.draftkings_replay import ReplayTransport


def replay_client(db_path: Path) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ReplayTransport(db_path))


@pytest.mark.anyio
async def test_replay_serves_saved_leaderboard(saved_draftkings_db: Path) -> None:
    async with replay_client(saved_draftkings_db) as client:
        text = await draftkings.fetch_leaderboard(client, "100000002")

    leaderboard = draftkings.parse_leaderboard(text)
    assert leaderboard.contest_id == "100000002"
    assert len(leaderboard.entries) == 6


@pytest.mark.anyio
async def test_replay_serves_saved_live_contests_as_my_contests_page(
    saved_draftkings_db: Path,
) -> None:
    async with replay_client(saved_draftkings_db) as client:
        page = await draftkings.fetch_live_contests(client)

    assert draftkings.parse_live_contests(page, {900001, 900002}) == ["100000001", "100000002"]


@pytest.mark.anyio
async def test_replay_returns_404_for_unsaved_contest(saved_draftkings_db: Path) -> None:
    async with replay_client(saved_draftkings_db) as client:
        with pytest.raises(draftkings.DraftKingsResponseError, match="HTTP 404"):
            await draftkings.fetch_leaderboard(client, "999")


@pytest.mark.anyio
async def test_replay_returns_404_for_other_urls(saved_draftkings_db: Path) -> None:
    async with replay_client(saved_draftkings_db) as client:
        response = await client.get("https://www.draftkings.com/lobby")

    assert response.status_code == 404
