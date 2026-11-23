import csv
from pathlib import Path
from typing import Any

import httpx
import pytest

from fantasy_api.best_ball.models import Platform
from fantasy_api.best_ball.playoff import load_playoff_sheet
from fantasy_api.sources.google_sheet import PlayerInfo
from fantasy_api.sources.sheets_api import SheetsAuth

FIXTURES = Path(__file__).parent / "fixtures"


class ValidCredentials:
    valid = True
    token: str | None = "test-token"

    def refresh(self, request: Any) -> None:
        raise AssertionError("a valid token is never refreshed")


def api_values(rows: list[list[str]]) -> list[list[str]]:
    """Rows as the Sheets API returns them: trailing empty cells left out."""
    trimmed = []
    for row in rows:
        cells = list(row)
        while cells and cells[-1] == "":
            cells.pop()
        trimmed.append(cells)
    return trimmed


@pytest.mark.anyio
async def test_load_playoff_sheet_reads_rosters_and_players() -> None:
    with (FIXTURES / "google_sheet_playoff_rosters.csv").open(newline="", encoding="utf-8") as f:
        rosters = list(csv.reader(f))
    adp = [["Player", "Pos", "Team"], ["Drake Maye", "QB", "NE"]]
    ranges: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ranges.extend(request.url.params.get_list("ranges"))
        value_ranges = [{"values": api_values(rosters)}, {"values": adp}]
        return httpx.Response(200, json={"valueRanges": value_ranges})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sheet = await load_playoff_sheet(client, SheetsAuth(ValidCredentials()), "sheet-id")

    assert ranges == ["'Rosters'", "'ADP Import'"]
    assert [team.platform for team in sheet.rosters.teams] == [
        Platform.DRAFTKINGS,
        Platform.UNDERDOG,
    ]
    assert sheet.rosters.skipped == []
    assert sheet.players == {
        "drakemaye": PlayerInfo(name="Drake Maye", position="QB", nfl_team="NE")
    }
