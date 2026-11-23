"""Read Google Sheet tabs through the Sheets API, as a service account the sheet is shared with."""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, Self

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from fantasy_api.sources.google_sheet import SheetError, SheetResponseError

_BATCH_GET_URL = "https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
_READ_ONLY_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
_TIMEOUT_SECONDS = 60


class SheetAuthError(SheetError):
    """The service account couldn't get a token, or the sheet isn't shared with it."""


class _Credentials(Protocol):
    valid: bool
    token: str | None

    def refresh(self, request: Any) -> None: ...


class SheetsAuth:
    """Hands out access tokens, refreshing them when they expire (after about an hour)."""

    def __init__(self, credentials: _Credentials) -> None:
        self._credentials = credentials

    @classmethod
    def from_key_file(cls, path: Path) -> Self:
        try:
            credentials = service_account.Credentials.from_service_account_file(
                str(path), scopes=_READ_ONLY_SCOPES
            )
        except ValueError as err:
            raise SheetAuthError(f"not a service account key file: {err}") from err
        return cls(credentials)

    async def token(self) -> str:
        if not self._credentials.valid:
            try:
                # google-auth refreshes with blocking requests calls, so keep it off the loop.
                await asyncio.to_thread(self._credentials.refresh, Request())
            except GoogleAuthError as err:
                raise SheetAuthError(f"could not get a Google access token: {err}") from err
        if self._credentials.token is None:
            raise SheetAuthError("Google returned no access token")
        return self._credentials.token


async def fetch_tabs(
    client: httpx.AsyncClient, token: str, spreadsheet_id: str, tabs: Sequence[str]
) -> list[list[list[str]]]:
    """Read whole tabs in one request, as rows of cell strings like the published CSV's.

    The API leaves out trailing empty cells, so every tab's rows are padded to its widest row.
    """
    url = _BATCH_GET_URL.format(spreadsheet_id=spreadsheet_id)
    params = {"ranges": [_quote_tab(tab) for tab in tabs]}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = await client.get(url, params=params, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as err:
        raise SheetResponseError(f"could not reach the Sheets API: {type(err).__name__}") from err

    if response.status_code in (401, 403):
        raise SheetAuthError(
            f"Sheets API refused access (HTTP {response.status_code}); "
            "check the sheet is shared with the service account"
        )
    if not response.is_success:
        message = _error_message(response)
        detail = f": {message}" if message else ""
        raise SheetResponseError(f"Sheets API returned HTTP {response.status_code}{detail}")

    value_ranges = response.json()["valueRanges"]
    return [_pad(value_range.get("values", [])) for value_range in value_ranges]


def _quote_tab(tab: str) -> str:
    """A1 notation for a whole tab; quotes allow spaces, and doubled quotes escape them."""
    escaped = tab.replace("'", "''")
    return f"'{escaped}'"


def _pad(rows: list[list[str]]) -> list[list[str]]:
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]


def _error_message(response: httpx.Response) -> str | None:
    try:
        message = response.json()["error"]["message"]
    except ValueError, KeyError, TypeError:
        return None
    return str(message)
