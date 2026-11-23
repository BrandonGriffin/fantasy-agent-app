from datetime import date
from pathlib import Path

import httpx
import pytest

from fantasy_api.best_ball.models import DraftedTeam, DraftPick, Platform
from fantasy_api.sources import google_sheet
from fantasy_api.sources.google_sheet import SheetLayoutError, SheetResponseError, fetch_csv

FIXTURES = Path(__file__).parent / "fixtures"
PUBLISH_ID = "mytest-sheet"
GID = "123"
# (round, overall, name, slot, nfl_team), as the sheet's columns C-G.
type PickRow = tuple[str, str, str, str, str]

# One value per metadata label, in sheet order. Written out here rather than imported
# from google_sheet so the tests check the parser's labels against an independent copy.
DEFAULT_META = {
    "Fantasy Platform": "Underdog",
    "League ID (Required)": "00000000-0000-4000-8000-000000000001",
    "League Type": "Early Bird",
    "League Name": "Example Contest",
    "Entry Fee": "$3.00",
    "Draft Speed": "Slow",
    "Draft Start Date": "2/11/26",
    "Draft Pick": "6",
    "Draft URL": "https://example.com/draft/1",
    "Pod Size": "",
    "Contest URL": "",
    "Regular Season Place": "",
    "Adv. to Quarterfinals": "",
    "Adv. to Semifinals": "",
    "Adv. to Finals": "",
    "Winnings": "",
    "Roster Nickname": "",
    "Co-manager(s)": "",
    "Tags": "",
    "Notes": "",
}

DEFAULT_PICKS: list[PickRow] = [
    ("1", "6", "Bijan Robinson", "RB1", "ATL"),
    ("2", "19", "Drake London", "WR1", "ATL"),
    ("3", "30", "Jaxon Smith-Njigba", "WR2", "SEA"),
]

BLANK_PICK: PickRow = ("", "", "", "", "")

# The sheet's first row names every column; later blocks repeat it with two blanks.
FULL_HEADER = ["Metadata Label", "Metadata", "Round", "Pick #", "Player Name", "Pos #", "Team"]
REPEATED_HEADER = ["Metadata", "", "Round", "Pick #", "", "Pos #", "Team"]


@pytest.mark.anyio
async def test_fetch_csv_returns_body_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert PUBLISH_ID in request.url.path
        assert request.url.params["gid"] == GID
        assert request.url.params["output"] == "csv"
        return httpx.Response(200, text="a,b\r\n1,2\r\n", headers={"content-type": "text/csv"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_csv(client, PUBLISH_ID, GID) == "a,b\r\n1,2\r\n"


@pytest.mark.anyio
async def test_fetch_csv_follows_google_redirect() -> None:
    csv_host = "https://doc-0s-sheets.googleusercontent.com/pub"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "docs.google.com":
            return httpx.Response(307, headers={"location": csv_host})
        return httpx.Response(200, text="a,b\r\n", headers={"content-type": "text/csv"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_csv(client, PUBLISH_ID, GID) == "a,b\r\n"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [404, 500])
async def test_fetch_csv_rejects_error_status(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="Not available")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SheetResponseError, match=str(status)) as excinfo:
            await fetch_csv(client, PUBLISH_ID, GID)

    assert PUBLISH_ID not in str(excinfo.value)


@pytest.mark.anyio
async def test_fetch_csv_rejects_html_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<!DOCTYPE html><html><title>Sign in</title></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SheetResponseError, match="text/html"):
            await fetch_csv(client, PUBLISH_ID, GID)


@pytest.mark.anyio
@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_fetch_csv_wraps_transport_errors(error: type[httpx.TransportError]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error(f"failed to reach {request.url}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SheetResponseError, match=error.__name__) as excinfo:
            await fetch_csv(client, PUBLISH_ID, GID)

    assert isinstance(excinfo.value.__cause__, error)
    assert PUBLISH_ID not in str(excinfo.value)


def test_read_rows_splits_crlf_lines_into_cells() -> None:
    text = (
        "Fantasy Platform,Underdog,1,1,Bijan Robinson,RB1,ATL\r\n"
        "League ID (Required),abc-123,2,24,Nico Collins,WR1,HOU\r\n"
    )

    assert google_sheet.read_rows(text) == [
        ["Fantasy Platform", "Underdog", "1", "1", "Bijan Robinson", "RB1", "ATL"],
        ["League ID (Required)", "abc-123", "2", "24", "Nico Collins", "WR1", "HOU"],
    ]


def test_read_rows_keeps_quoted_commas_in_one_cell() -> None:
    # Real note from the sheet; the old app's split(",") shifted every column after it.
    text = 'Tags,"CT 25, 27, 2DKs",19,222,,,\r\n'

    assert google_sheet.read_rows(text) == [["Tags", "CT 25, 27, 2DKs", "19", "222", "", "", ""]]


def test_read_rows_raises_on_html_page() -> None:
    # An unpublished or deleted sheet serves an HTML sign-in page, not CSV.
    with pytest.raises(SheetResponseError):
        google_sheet.read_rows("<!DOCTYPE html><html><body>Sign in</body></html>")


@pytest.mark.parametrize("response", ["", "\r\n"])
def test_read_rows_raises_on_empty_text(response: str) -> None:
    # A published sheet is never empty; a blank body means something upstream went wrong.
    with pytest.raises(SheetResponseError):
        google_sheet.read_rows(response)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("$3.00", 300, id="dollars"),
        pytest.param("$25.00", 2500, id="two-digit-dollars"),
        pytest.param("$1,000.00", 100000, id="thousands-separator"),
        pytest.param("3.00", 300, id="no-dollar-sign"),
        pytest.param("$3", 300, id="no-cents"),
    ],
)
def test_parse_cents(raw: str, expected: int) -> None:
    assert google_sheet.parse_cents(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("$3.005", id="fraction-of-a-cent"),
        pytest.param("free", id="not-a-number"),
        pytest.param("", id="empty"),
        pytest.param("Infinity", id="infinity"),
        pytest.param("-3", id="negative"),
    ],
)
def test_parse_cents_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        google_sheet.parse_cents(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("2/11/2026", date(2026, 2, 11), id="four-digit-year"),
        pytest.param("2/1/2026", date(2026, 2, 1), id="single-digit-day"),
        pytest.param("2/11/26", date(2026, 2, 11), id="two-digit-year"),
        pytest.param("12/31/25", date(2025, 12, 31), id="two-digit-year-december"),
    ],
)
def test_parse_sheet_date(raw: str, expected: date) -> None:
    assert google_sheet.parse_sheet_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("13/45/2026", id="impossible-date"),
        pytest.param("2026-02-11", id="iso-is-not-a-sheet-format"),
        pytest.param("", id="empty"),
    ],
)
def test_parse_sheet_date_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        google_sheet.parse_sheet_date(raw)


def team_block(
    meta: dict[str, str] | None = None,
    picks: list[PickRow] | None = None,
    *,
    first: bool = True,
) -> list[list[str]]:
    """Build one 21-row team block (columns A-G) like the published sheet's.

    Override only what a test cares about: team_block(meta={"Entry Fee": "$25.00"}).
    Pick rows past the last pick are blank, as on 18-round teams. Pass first=False
    for any block after the first, which gets the sheet's repeated (partly blank) header.
    """
    overrides = meta or {}
    unknown = overrides.keys() - DEFAULT_META.keys()
    if unknown:
        raise KeyError(f"not sheet labels: {sorted(unknown)}")  # catch typos in tests
    fields = DEFAULT_META | overrides
    picks = DEFAULT_PICKS if picks is None else picks

    rows = [list(FULL_HEADER if first else REPEATED_HEADER)]
    for i, (label, value) in enumerate(fields.items()):
        pick = picks[i] if i < len(picks) else BLANK_PICK
        rows.append([label, value, *pick])

    assert len(rows) == google_sheet.BLOCK_SIZE
    return rows


def test_parse_teams_builds_team_from_block() -> None:
    result = google_sheet.parse_teams(team_block())

    assert result.skipped == []
    assert result.teams == [
        DraftedTeam(
            platform=Platform.UNDERDOG,
            league_id="00000000-0000-4000-8000-000000000001",
            league_type="Early Bird",
            league_name="Example Contest",
            entry_fee_cents=300,
            draft_speed="Slow",
            draft_date=date(2026, 2, 11),
            draft_pick=6,
            draft_url="https://example.com/draft/1",
            tags=None,
            notes=None,
            picks=[
                DraftPick(round=1, overall=6, name="Bijan Robinson", slot="RB1", nfl_team="ATL"),
                DraftPick(round=2, overall=19, name="Drake London", slot="WR1", nfl_team="ATL"),
                DraftPick(
                    round=3, overall=30, name="Jaxon Smith-Njigba", slot="WR2", nfl_team="SEA"
                ),
            ],
        )
    ]


def test_parse_teams_returns_one_team_per_block_in_sheet_order() -> None:
    first = team_block(meta={"League ID (Required)": "first"})
    second = team_block(
        meta={"League ID (Required)": "second", "Fantasy Platform": "DraftKings"},
        picks=[("1", "12", "CeeDee Lamb", "WR1", "DAL")],
        first=False,
    )

    teams = google_sheet.parse_teams(first + second).teams

    assert [(team.league_id, team.platform) for team in teams] == [
        ("first", Platform.UNDERDOG),
        ("second", Platform.DRAFTKINGS),
    ]
    # Each team keeps only its own picks; nothing bleeds across the block boundary.
    assert [len(team.picks) for team in teams] == [3, 1]
    assert teams[1].picks[0].name == "CeeDee Lamb"


def test_parse_teams_raises_when_header_is_missing_a_column() -> None:
    rows = team_block()
    rows[0][FULL_HEADER.index("Player Name")] = ""

    with pytest.raises(SheetLayoutError, match="Player Name"):
        google_sheet.parse_teams(rows)


def test_layout_errors_are_not_value_errors() -> None:
    # parse_teams reports ValueErrors from bad cells as skipped blocks. If SheetLayoutError
    # ever became a ValueError, structural problems would be silently skipped too.
    assert not issubclass(SheetLayoutError, ValueError)


def test_parse_teams_skips_template_blocks_without_reporting_them() -> None:
    template = team_block(meta=dict.fromkeys(DEFAULT_META, ""), picks=[], first=False)
    rows = (
        team_block(meta={"League ID (Required)": "first"})
        + template
        + team_block(meta={"League ID (Required)": "third"}, first=False)
    )

    result = google_sheet.parse_teams(rows)

    assert [team.league_id for team in result.teams] == ["first", "third"]
    assert result.skipped == []


def test_parse_teams_skips_and_reports_a_block_with_a_bad_cell() -> None:
    # Real case: block 398 of the live sheet had its draft URL pasted into Entry Fee.
    rows = (
        team_block(meta={"League ID (Required)": "first"})
        + team_block(
            meta={"League ID (Required)": "bad", "Entry Fee": "https://example.com/draft/2"},
            first=False,
        )
        + team_block(meta={"League ID (Required)": "third"}, first=False)
    )

    result = google_sheet.parse_teams(rows)

    assert [team.league_id for team in result.teams] == ["first", "third"]
    [skipped] = result.skipped
    assert (skipped.block, skipped.sheet_row) == (2, 22)
    assert "Entry Fee" in skipped.reason
    assert "https://example.com/draft/2" in skipped.reason


def test_parse_teams_skips_and_reports_an_unknown_platform() -> None:
    result = google_sheet.parse_teams(team_block(meta={"Fantasy Platform": "FanDuel"}))

    assert result.teams == []
    [skipped] = result.skipped
    assert (skipped.block, skipped.sheet_row) == (1, 1)
    assert "Fantasy Platform" in skipped.reason


def test_parse_teams_raises_when_a_block_has_shifted_labels() -> None:
    # A row inserted mid-block pushes every label below it down by one.
    rows = team_block() + team_block(first=False)
    rows.insert(10, ["", "", "", "", "", "", ""])
    rows.pop()  # keep a whole number of blocks so only the labels are wrong

    with pytest.raises(SheetLayoutError, match=r"block 1\b"):
        google_sheet.parse_teams(rows)


def test_parse_teams_raises_when_the_last_block_is_short() -> None:
    rows = team_block() + team_block(first=False)[:-1]

    with pytest.raises(SheetLayoutError):
        google_sheet.parse_teams(rows)


def test_parse_teams_reads_recorded_sheet() -> None:
    # INFO: BG 20261025: read_bytes().decode() keeps CRLFs; read_text() would turn them into "\n".
    text = (FIXTURES / "google_sheet_teams.csv").read_bytes().decode("utf-8")
    assert "\r\n" in text  # INFO: BG 20261025: guards the fixture against line-ending normalization

    result = google_sheet.parse_teams(google_sheet.read_rows(text))

    assert [team.platform for team in result.teams] == [
        Platform.UNDERDOG,
        Platform.DRAFTKINGS,
        Platform.DRAFTERS,
        Platform.UNDERDOG,
    ]
    assert [len(team.picks) for team in result.teams] == [20, 20, 20, 18]
    assert result.teams[1].entry_fee_cents == 0
    assert result.teams[0].picks[0] == DraftPick(
        round=1, overall=1, name="Bijan Robinson", slot="RB1", nfl_team="ATL"
    )
    [skipped] = result.skipped
    assert (skipped.block, skipped.sheet_row) == (5, 85)
    assert skipped.reason.startswith("Entry Fee:")


# The playoff sheet's first row names only some columns, and its 10th label is
# "Draft Progress" where the regular-season sheet has "Pod Size".
PLAYOFF_HEADER = ["0", "", "Round", "Pick #", "", "Pos #", "Team"]
DRAFT_PROGRESS_ROW = 10

# Team and Pos # stay blank until the ADP Import tab is filled in.
PLAYOFF_PICKS: list[PickRow] = [
    ("1", "1", "Puka Nacua", "", ""),
    ("2", "12", "Rashee Rice", "", ""),
    ("3", "13", "Jahmyr Gibbs", "", ""),
]


def playoff_block(
    meta: dict[str, str] | None = None,
    picks: list[PickRow] | None = None,
    *,
    first: bool = True,
) -> list[list[str]]:
    rows = team_block(
        meta={"League Type": "Playoff", **(meta or {})},
        picks=PLAYOFF_PICKS if picks is None else picks,
        first=first,
    )
    rows[0] = list(PLAYOFF_HEADER if first else REPEATED_HEADER)
    rows[DRAFT_PROGRESS_ROW][0] = "Draft Progress"
    return rows


def test_parse_teams_reads_playoff_blocks() -> None:
    result = google_sheet.parse_teams(playoff_block(), google_sheet.PLAYOFF_ROSTERS)

    assert result.skipped == []
    [team] = result.teams
    assert team.league_type == "Playoff"
    assert team.picks == [
        DraftPick(round=1, overall=1, name="Puka Nacua", slot="", nfl_team=""),
        DraftPick(round=2, overall=12, name="Rashee Rice", slot="", nfl_team=""),
        DraftPick(round=3, overall=13, name="Jahmyr Gibbs", slot="", nfl_team=""),
    ]


def test_parse_teams_keeps_however_many_playoff_picks_are_filled_in() -> None:
    draftkings = [(str(r), str(r), f"Player {r}", "", "") for r in range(1, 13)]
    underdog = [(str(r), str(r), f"Player {r}", "", "") for r in range(1, 11)]
    rows = playoff_block({"Fantasy Platform": "DraftKings"}, draftkings) + playoff_block(
        {"Fantasy Platform": "Underdog"}, underdog, first=False
    )

    teams = google_sheet.parse_teams(rows, google_sheet.PLAYOFF_ROSTERS).teams

    assert [len(team.picks) for team in teams] == [12, 10]


def test_parse_teams_rejects_playoff_blocks_with_the_regular_season_layout() -> None:
    with pytest.raises(SheetLayoutError, match="Draft Progress"):
        google_sheet.parse_teams(team_block(), google_sheet.PLAYOFF_ROSTERS)


def test_parse_teams_rejects_regular_season_blocks_with_the_playoff_layout() -> None:
    rows = playoff_block()
    rows[0] = list(FULL_HEADER)

    with pytest.raises(SheetLayoutError, match="Pod Size"):
        google_sheet.parse_teams(rows)


def test_parse_teams_reads_recorded_playoff_sheet() -> None:
    text = (FIXTURES / "google_sheet_playoff_rosters.csv").read_bytes().decode("utf-8")
    assert "\r\n" in text

    result = google_sheet.parse_teams(google_sheet.read_rows(text), google_sheet.PLAYOFF_ROSTERS)

    assert result.skipped == []
    assert [team.platform for team in result.teams] == [Platform.DRAFTKINGS, Platform.UNDERDOG]
    assert [len(team.picks) for team in result.teams] == [12, 10]
    assert result.teams[0].draft_date == date(2025, 12, 1)
    assert result.teams[1].picks[1] == DraftPick(
        round=2, overall=11, name="Drake Maye", slot="", nfl_team=""
    )


ADP_HEADER = ["Player", "Pos", "Team", "ADP", "Value", "Advance Rate", "Underdog ADP"]


def test_parse_players_maps_normalized_names_to_position_and_team() -> None:
    rows = [
        ADP_HEADER,
        ["Puka Nacua", "WR", "LAR", "1.2", "", "", "1.5"],
        ["Kenneth Walker III", "RB", "SEA", "30.1", "", "", ""],
    ]

    players = google_sheet.parse_players(rows)

    assert players == {
        "pukanacua": google_sheet.PlayerInfo(name="Puka Nacua", position="WR", nfl_team="LAR"),
        "kennethwalker": google_sheet.PlayerInfo(
            name="Kenneth Walker III", position="RB", nfl_team="SEA"
        ),
    }


def test_parse_players_skips_blank_rows() -> None:
    # Real case: unused rows hold a space for the name and #N/A for the team.
    rows = [ADP_HEADER, [" ", "", "#N/A", "", "82.772", "", ""]]

    assert google_sheet.parse_players(rows) == {}


def test_parse_players_keeps_the_first_of_two_players_with_the_same_name() -> None:
    rows = [ADP_HEADER, ["Josh Allen", "QB", "BUF"], ["Josh Allen", "LB", "JAX"]]

    players = google_sheet.parse_players(rows)

    assert players["joshallen"].nfl_team == "BUF"


def test_parse_players_raises_when_header_is_missing_a_column() -> None:
    rows = [["Player", "Position", "Team"], ["Puka Nacua", "WR", "LAR"]]

    with pytest.raises(SheetLayoutError, match="Pos"):
        google_sheet.parse_players(rows)
