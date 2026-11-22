"""Answer DraftKings requests from responses the old app saved in SQLite, without the network."""

import asyncio
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx

_LEADERBOARD_PATH = re.compile(r"/scores/v1/megacontests/(?P<contest_id>\d+)/leaderboard")


class ReplayTransport(httpx.AsyncBaseTransport):
    """Serve saved DraftKings responses from the old app's dk_responses table.

    The old app saved the live contests already parsed out of the My Contests page, so they are
    wrapped back into a minimal page. Anything not saved gets a 404.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_uri = f"{db_path.resolve().as_uri()}?mode=ro"

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await asyncio.to_thread(self._saved_body, request.url)
        if body is None:
            return httpx.Response(404, request=request)
        return httpx.Response(200, text=body, request=request)

    def _saved_body(self, url: httpx.URL) -> str | None:
        if url.host == "www.draftkings.com" and url.path == "/mycontests":
            live_contests = self._read("live-contests")
            return None if live_contests is None else _my_contests_page(live_contests)

        leaderboard = _LEADERBOARD_PATH.fullmatch(url.path)
        if url.host == "api.draftkings.com" and leaderboard:
            return self._read(f"league-{leaderboard['contest_id']}")

        return None

    def _read(self, cache_key: str) -> str | None:
        with closing(sqlite3.connect(self._db_uri, uri=True)) as db:
            row = db.execute(
                "SELECT body FROM dk_responses WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        return None if row is None else str(row[0])


def _my_contests_page(live_contests: str) -> str:
    return f"<html><script>var contests = {{ live: {live_contests} }};</script></html>"
