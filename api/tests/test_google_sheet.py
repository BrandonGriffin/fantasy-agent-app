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
def test_read_rows_raises_on_empty_message(response: str) -> None:
    # An unpublished or deleted sheet serves an HTML sign-in page, not CSV.
    with pytest.raises(SheetResponseError):
        google_sheet.read_rows(response)
