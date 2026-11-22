"""Fetch and parse best-ball standings from the DraftKings API."""

import asyncio
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from fantasy_api.best_ball.models import Leaderboard, LeaderboardEntry

_LEADERBOARD_URL = "https://api.draftkings.com/scores/v1/megacontests/{contest_id}/leaderboard"
_MY_CONTESTS_URL = "https://www.draftkings.com/mycontests"
_LIVE_CONTESTS_KEY = re.compile(r"\blive:\s*")


class DraftKingsError(Exception):
    """Base error for the DraftKings source."""


class DraftKingsResponseError(DraftKingsError):
    """The response doesn't contain usable standings."""


class DraftKingsAuthError(DraftKingsError):
    """DraftKings rejected the session cookie; a fresh one is needed in .env."""


def draftkings_client(cookie: SecretStr) -> httpx.AsyncClient:
    """Create an HTTP client that sends the DraftKings session cookie on every request."""

    return httpx.AsyncClient(headers={"Cookie": cookie.get_secret_value()})


async def fetch_live_contests(client: httpx.AsyncClient) -> str:
    """Download the My Contests page, which embeds the live contests in an inline script."""

    return await _get(client, _MY_CONTESTS_URL)


async def fetch_leaderboard(client: httpx.AsyncClient, contest_id: str) -> str:
    """Download one megacontest's leaderboard as JSON text."""

    url = _LEADERBOARD_URL.format(contest_id=contest_id)
    return await _get(client, url, params={"format": "json", "embed": "leaderboard"})


@dataclass(frozen=True)
class FetchedLeaderboards:
    leaderboards: list[Leaderboard]
    failed: dict[str, str]  # contest ID -> why it couldn't be fetched or parsed


async def fetch_leaderboards(
    client: httpx.AsyncClient, contest_ids: Sequence[str], *, max_concurrent: int
) -> FetchedLeaderboards:
    """Fetch and parse many leaderboards at once, keeping the rest when one contest fails.

    A rejected cookie stops everything, since every remaining request would fail the same way.
    """

    request_slots = asyncio.Semaphore(max_concurrent)
    cookie_rejected = asyncio.Event()
    leaderboards: dict[str, Leaderboard] = {}
    failed: dict[str, str] = {}

    async def fetch_one(contest_id: str) -> None:
        async with request_slots:
            if cookie_rejected.is_set():
                return
            try:
                text = await fetch_leaderboard(client, contest_id)
                leaderboards[contest_id] = parse_leaderboard(text)
            except DraftKingsAuthError:
                cookie_rejected.set()
                raise
            except DraftKingsResponseError as err:
                failed[contest_id] = str(err)

    try:
        async with asyncio.TaskGroup() as tasks:
            for contest_id in contest_ids:
                tasks.create_task(fetch_one(contest_id))
    except* DraftKingsAuthError as rejected:
        raise rejected.exceptions[0] from None

    return FetchedLeaderboards(
        leaderboards=[leaderboards[id_] for id_ in contest_ids if id_ in leaderboards],
        failed={id_: failed[id_] for id_ in contest_ids if id_ in failed},
    )


async def _get(client: httpx.AsyncClient, url: str, params: Mapping[str, str] | None = None) -> str:
    try:
        response = await client.get(url, params=params)
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


def parse_live_contests(html: str, draft_group_ids: Collection[int]) -> list[str]:
    """Read the IDs of the best-ball leagues embedded in the My Contests page, each listed once."""

    script_start = html.find("var contests")
    if script_start == -1:
        raise DraftKingsAuthError(
            "no contests on the My Contests page; the session cookie has probably expired"
        )

    live_key = _LIVE_CONTESTS_KEY.search(html, script_start)
    if live_key is None:
        raise DraftKingsResponseError("could not read the live contests (no live list)")

    try:
        contests, _ = json.JSONDecoder().raw_decode(html, live_key.end())
        league_ids = [
            str(contest["MegaContestId"])
            for contest in contests
            if contest["DraftGroupId"] in draft_group_ids
        ]
    except (ValueError, TypeError, KeyError) as err:
        raise DraftKingsResponseError(
            f"could not read the live contests ({type(err).__name__})"
        ) from err

    return list(dict.fromkeys(league_ids))


def _parse_entry(row: Mapping[str, Any]) -> LeaderboardEntry:
    return LeaderboardEntry(
        rank=row["Rank"],
        username=row["UserName"],
        points=row["FantasyPoints"],
    )
