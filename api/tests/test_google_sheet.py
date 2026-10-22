from datetime import date

import pytest

from fantasy_api.sources import google_sheet
from fantasy_api.sources.google_sheet import SheetResponseError


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
