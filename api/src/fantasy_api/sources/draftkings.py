"""Fetch and parse best-ball standings from the DraftKings API."""

import json
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import SecretStr

from fantasy_api.best_ball.models import Leaderboard, LeaderboardEntry

_LEADERBOARD_URL = "https://api.draftkings.com/scores/v1/megacontests/{contest_id}/leaderboard"


class DraftKingsError(Exception):
    """Base error for the DraftKings source."""


class DraftKingsResponseError(DraftKingsError):
    """The response doesn't contain usable standings."""


class DraftKingsAuthError(DraftKingsError):
    """DraftKings rejected the session cookie; a fresh one is needed in .env."""


def draftkings_client(cookie: SecretStr) -> httpx.AsyncClient:
    """Create an HTTP client that sends the DraftKings session cookie on every request."""

    return httpx.AsyncClient(headers={"Cookie": cookie.get_secret_value()})


async def fetch_leaderboard(client: httpx.AsyncClient, contest_id: str) -> str:
    """Download one megacontest's leaderboard as JSON text."""

    url = _LEADERBOARD_URL.format(contest_id=contest_id)

    try:
        response = await client.get(url)
    except httpx.HTTPError as err:
        raise DraftKingsResponseError(f"could not reach DraftKings: {type(err).__name__}") from err

    if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        raise DraftKingsAuthError(
            f"DraftKings rejected the session cookie (HTTP {response.status_code})"
        )

    if not response.is_success:
        raise DraftKingsResponseError(f"DraftKings returned HTTP {response.status_code}")

    return response.text


def parse_leaderboard(text: str) -> Leaderboard:
    """Read a megacontest leaderboard response into entries in rank order."""

    try:
        rows = json.loads(text)["Leaderboard"]

        if not rows:
            raise DraftKingsResponseError("leaderboard has no entries")

        return Leaderboard(
            contest_id=rows[0]["MegaContestKey"],
            entries=[_parse_entry(row) for row in rows],
        )
    except (ValueError, TypeError, KeyError) as err:
        raise DraftKingsResponseError(
            f"response is not a leaderboard ({type(err).__name__})"
        ) from err


def _parse_entry(row: Mapping[str, Any]) -> LeaderboardEntry:
    return LeaderboardEntry(
        rank=row["Rank"],
        username=row["UserName"],
        points=row["FantasyPoints"],
    )
