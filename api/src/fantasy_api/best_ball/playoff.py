from dataclasses import dataclass

import httpx

from fantasy_api.sources import google_sheet
from fantasy_api.sources.google_sheet import ParsedTeams, PlayerInfo
from fantasy_api.sources.sheets_api import SheetsAuth, fetch_tabs

ROSTERS_TAB = "Rosters"
ADP_TAB = "ADP Import"


@dataclass(frozen=True)
class PlayoffSheet:
    rosters: ParsedTeams
    players: dict[str, PlayerInfo]  # keyed by normalize.player_name


async def load_playoff_sheet(
    client: httpx.AsyncClient, auth: SheetsAuth, spreadsheet_id: str
) -> PlayoffSheet:
    rosters, adp = await fetch_tabs(
        client, await auth.token(), spreadsheet_id, [ROSTERS_TAB, ADP_TAB]
    )
    return PlayoffSheet(
        rosters=google_sheet.parse_teams(rosters, google_sheet.PLAYOFF_ROSTERS),
        players=google_sheet.parse_players(adp),
    )
