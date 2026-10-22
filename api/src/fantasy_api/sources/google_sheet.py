"""Parse drafted best-ball teams from the Google Sheet's published CSV ("Publish to web").

The teams tab is a stack of 21-row blocks, one per drafted team, 30 columns wide:
- row 0: header (column A is "Metadata", or "Metadata Label" on the first block; don't rely on it)
- rows 1-20: column A = metadata label, B = value (see _META_LABELS);
  C = round, D = overall pick, E = player name, F = roster slot ("RB1"), G = NFL team.
  Teams have 20 picks, or 18 on 18-round contests; unused pick rows are blank.
Every value is a string and empty cells are "". Blocks with no platform and no picks are
unused templates. Lines end in CRLF, and notes can contain quoted commas.
"""

import csv
import io
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation

from fantasy_api.best_ball.models import DraftedTeam

BLOCK_SIZE = 21

# Column A of rows 1-20 in every block, in order.
_META_LABELS = (
    "Fantasy Platform",
    "League ID (Required)",
    "League Type",
    "League Name",
    "Entry Fee",
    "Draft Speed",
    "Draft Start Date",
    "Draft Pick",
    "Draft URL",
    "Pod Size",
    "Contest URL",
    "Regular Season Place",
    "Adv. to Quarterfinals",
    "Adv. to Semifinals",
    "Adv. to Finals",
    "Winnings",
    "Roster Nickname",
    "Co-manager(s)",
    "Tags",
    "Notes",
)


class SheetError(Exception):
    """Base error for the Google Sheet source."""


class SheetResponseError(SheetError):
    """The response is not usable CSV (e.g. an HTML sign-in page for an unpublished sheet)."""


class SheetLayoutError(SheetError):
    """The sheet's rows don't match the expected block layout."""


def read_rows(text: str) -> list[list[str]]:
    """Split published CSV text into rows of cell strings."""

    if not text.strip():
        raise SheetResponseError("CSV was empty")

    if text.lstrip().startswith("<"):
        raise SheetResponseError(f"expected CSV, got HTML: {text[:80]!r}")

    csv_text = io.StringIO(text)
    reader = csv.reader(csv_text)

    return list(reader)


def parse_cents(value: str) -> int:
    """Parse a sheet money cell ("$3.00", "$1,000.00") into integer cents.

    Raises ValueError for anything that isn't a whole number of cents.
    """

    cleaned = value.replace("$", "").replace(",", "")

    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as err:
        raise ValueError(f"not a money value: {value!r}") from err

    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"Negative or infinite: {value!r}")

    cents = parsed * 100

    if cents != cents.to_integral_value():
        raise ValueError(f"Fraction of a cent: {value!r}")

    return int(cents)


def parse_sheet_date(value: str) -> date:
    """Parse a sheet date cell ("2/11/2026", "2/1/2026" or "2/11/26").

    Raises ValueError for anything else.
    """
    for format in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return date.strptime(value, format)
        except ValueError:
            continue

    raise ValueError(f"not a parseable date: {value}")


def parse_teams(rows: Sequence[Sequence[str]]) -> list[DraftedTeam]:
    """Turn sheet rows into drafted teams, skipping empty template blocks."""
    return []
