from datetime import date

import pytest

from fantasy_api.best_ball.models import DraftedTeam, DraftPick, Platform
from fantasy_api.sources import google_sheet
from fantasy_api.sources.google_sheet import SheetLayoutError, SheetResponseError


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


# --- parse_teams -------------------------------------------------------------

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
