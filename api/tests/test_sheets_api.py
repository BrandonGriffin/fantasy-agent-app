import json
from typing import Any

import httpx
import pytest
from google.auth.exceptions import RefreshError

from fantasy_api.sources.google_sheet import SheetResponseError
from fantasy_api.sources.sheets_api import SheetAuthError, SheetsAuth, fetch_tabs

SPREADSHEET_ID = "test-spreadsheet"
TOKEN = "test-token"


def sheets_client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def batch_get(*value_ranges: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200, json={"spreadsheetId": SPREADSHEET_ID, "valueRanges": list(value_ranges)}
    )


@pytest.mark.anyio
async def test_fetch_tabs_requests_each_tab_with_the_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return batch_get({"values": [["a"]]}, {"values": [["b"]]})

    async with sheets_client(handler) as client:
        await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosters", "ADP Import"])

    [request] = requests
    assert request.url.host == "sheets.googleapis.com"
    assert request.url.path == f"/v4/spreadsheets/{SPREADSHEET_ID}/values:batchGet"
    assert request.url.params.get_list("ranges") == ["'Rosters'", "'ADP Import'"]
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.anyio
async def test_fetch_tabs_returns_rows_per_tab_in_request_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return batch_get({"values": [["Rosters A1"]]}, {"values": [["ADP A1"]]})

    async with sheets_client(handler) as client:
        tabs = await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosters", "ADP Import"])

    assert tabs == [[["Rosters A1"]], [["ADP A1"]]]


@pytest.mark.anyio
async def test_fetch_tabs_pads_rows_to_the_widest_row() -> None:
    # The API drops trailing empty cells, and returns blank rows as [].
    def handler(request: httpx.Request) -> httpx.Response:
        return batch_get({"values": [["a", "b", "c"], ["d"], []]})

    async with sheets_client(handler) as client:
        [rows] = await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosters"])

    assert rows == [["a", "b", "c"], ["d", "", ""], ["", "", ""]]


@pytest.mark.anyio
async def test_fetch_tabs_returns_no_rows_for_an_empty_tab() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return batch_get({"range": "Rosters!A1:Z1000"})

    async with sheets_client(handler) as client:
        assert await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosters"]) == [[]]


@pytest.mark.anyio
async def test_fetch_tabs_doubles_apostrophes_in_tab_names() -> None:
    ranges: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ranges.extend(request.url.params.get_list("ranges"))
        return batch_get({})

    async with sheets_client(handler) as client:
        await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Brandon's Teams"])

    assert ranges == ["'Brandon''s Teams'"]


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403])
async def test_fetch_tabs_raises_auth_error_when_access_is_refused(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, json={"error": {"message": "The caller does not have permission"}}
        )

    async with sheets_client(handler) as client:
        with pytest.raises(SheetAuthError, match="shared with the service account"):
            await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosters"])


@pytest.mark.anyio
async def test_fetch_tabs_includes_googles_error_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Unable to parse range: Rosterz"}})

    async with sheets_client(handler) as client:
        with pytest.raises(SheetResponseError, match="HTTP 400: Unable to parse range: Rosterz"):
            await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosterz"])


@pytest.mark.anyio
async def test_fetch_tabs_handles_an_error_without_a_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="<html>Service Unavailable</html>")

    async with sheets_client(handler) as client:
        with pytest.raises(SheetResponseError, match=r"HTTP 503$"):
            await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosters"])


@pytest.mark.anyio
async def test_fetch_tabs_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async with sheets_client(handler) as client:
        with pytest.raises(SheetResponseError, match="ConnectError"):
            await fetch_tabs(client, TOKEN, SPREADSHEET_ID, ["Rosters"])


class FakeCredentials:
    def __init__(self, *, valid: bool, refresh_error: bool = False) -> None:
        self.valid = valid
        self.token: str | None = "cached-token" if valid else None
        self.refreshes = 0
        self._refresh_error = refresh_error

    def refresh(self, request: object) -> None:
        self.refreshes += 1
        if self._refresh_error:
            raise RefreshError("invalid_grant: Invalid JWT Signature.")
        self.valid = True
        self.token = f"fresh-token-{self.refreshes}"


@pytest.mark.anyio
async def test_sheets_auth_reuses_a_valid_token() -> None:
    credentials = FakeCredentials(valid=True)

    assert await SheetsAuth(credentials).token() == "cached-token"
    assert credentials.refreshes == 0


@pytest.mark.anyio
async def test_sheets_auth_refreshes_an_expired_token() -> None:
    credentials = FakeCredentials(valid=False)
    auth = SheetsAuth(credentials)

    assert await auth.token() == "fresh-token-1"
    assert await auth.token() == "fresh-token-1"
    assert credentials.refreshes == 1


@pytest.mark.anyio
async def test_sheets_auth_wraps_refresh_errors() -> None:
    auth = SheetsAuth(FakeCredentials(valid=False, refresh_error=True))

    with pytest.raises(SheetAuthError, match="Invalid JWT Signature"):
        await auth.token()


def test_sheets_auth_reads_a_service_account_key_file(tmp_path: Any) -> None:
    key_file = tmp_path / "key.json"
    key_file.write_text(json.dumps({"type": "authorized_user"}))

    with pytest.raises(SheetAuthError, match="service account key"):
        SheetsAuth.from_key_file(key_file)
