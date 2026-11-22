from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from fantasy_api.best_ball.models import LeaderboardsResponse
from fantasy_api.config import Settings
from fantasy_api.sources import draftkings
from fantasy_api.sources.draftkings_replay import ReplayTransport

router = APIRouter(prefix="/best-ball", tags=["best-ball"])


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def draftkings_http(
    settings: Annotated[Settings, Depends(get_settings)],
    live: Annotated[
        bool, Query(description="Fetch from DraftKings instead of the saved responses.")
    ] = False,
) -> AsyncIterator[httpx.AsyncClient]:
    client = _live_draftkings_client(settings) if live else _replay_draftkings_client(settings)

    async with client:
        yield client


def _live_draftkings_client(settings: Settings) -> httpx.AsyncClient:
    if settings.draftkings_cookie is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DraftKings is not configured: set DRAFTKINGS_COOKIE",
        )
    return draftkings.draftkings_client(settings.draftkings_cookie)


def _replay_draftkings_client(settings: Settings) -> httpx.AsyncClient:
    if settings.draftkings_replay_db is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No saved DraftKings data: set DRAFTKINGS_REPLAY_DB, or pass live=true",
        )
    return httpx.AsyncClient(transport=ReplayTransport(settings.draftkings_replay_db))


@router.get("/leaderboards")
async def leaderboards(
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[httpx.AsyncClient, Depends(draftkings_http)],
) -> LeaderboardsResponse:
    """Live standings for every DraftKings best-ball league, plus any contests that failed."""

    try:
        page = await draftkings.fetch_live_contests(client)
        contest_ids = draftkings.parse_live_contests(page, settings.draftkings_draft_group_ids)
        fetched = await draftkings.fetch_leaderboards(
            client, contest_ids, max_concurrent=settings.draftkings_max_concurrent_requests
        )
    except draftkings.DraftKingsError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err

    return LeaderboardsResponse(leaderboards=fetched.leaderboards, failed=fetched.failed)
