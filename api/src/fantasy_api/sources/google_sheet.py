"""Parse drafted best-ball teams from the Google Sheet's published CSV ("Publish to web").

The teams tab is a stack of 21-row blocks, one per drafted team, 30 columns wide:
- row 0: header. Only the sheet's very first row has every column name (see
  _REQUIRED_COLUMNS); later blocks repeat it with "Metadata" and "Player Name" blank.
  Column positions are therefore read once, from the sheet's first row.
- rows 1-20: column A = metadata label, B = value (see _META_LABELS);
  C = round, D = overall pick, E = player name, F = roster slot ("RB1"), G = NFL team.
  Teams have 20 picks, or 18 on 18-round contests; unused pick rows are blank.
Every value is a string and empty cells are "". Blocks with no platform and no picks are
unused templates. Lines end in CRLF, and notes can contain quoted commas.
"""

import csv
import io
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import batched

from fantasy_api.best_ball.models import DraftedTeam, DraftPick, Platform

BLOCK_SIZE = 21

# Header names in the sheet's first row that the parser reads by name.
_REQUIRED_COLUMNS = (
    "Metadata Label",
    "Metadata",
    "Round",
    "Pick #",
    "Player Name",
    "Pos #",
    "Team",
)

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
    """The sheet's rows don't match the expected block layout.

    Deliberately not a ValueError: parse_teams turns ValueErrors from bad cells into
    SkippedBlock reports, and structural errors must never be swallowed that way.
    """


@dataclass(frozen=True)
class SkippedBlock:
    """A team block left out of the results because one of its cells couldn't be parsed."""

    block: int  # 1-based block number
    sheet_row: int  # 1-based sheet row where the block starts, as shown in Google Sheets
    reason: str


@dataclass(frozen=True)
class ParsedTeams:
    teams: list[DraftedTeam]
    skipped: list[SkippedBlock]


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


def parse_teams(rows: Sequence[Sequence[str]]) -> ParsedTeams:
    """Turn sheet rows into drafted teams.

    Empty template blocks are skipped silently. A block with a bad cell is skipped and
    reported in ParsedTeams.skipped. Layout problems raise SheetLayoutError.
    """
    columns = _column_positions(rows[0])
    teams: list[DraftedTeam] = []
    skipped: list[SkippedBlock] = []

    for number, block in enumerate(_blocks(rows), start=1):
        _check_labels(block, columns, number)
        if _is_template(block, columns):
            continue
        try:
            teams.append(_parse_team(block, columns))
        except ValueError as err:
            skipped.append(
                SkippedBlock(block=number, sheet_row=_sheet_row(number), reason=str(err))
            )

    return ParsedTeams(teams=teams, skipped=skipped)


def _blocks(rows: Sequence[Sequence[str]]) -> Iterator[tuple[Sequence[str], ...]]:
    """Split rows into 21-row team blocks; a short final block is a layout error."""
    try:
        # yield from inside the try: batched raises mid-iteration, on the short group.
        yield from batched(rows, BLOCK_SIZE, strict=True)
    except ValueError as err:
        raise SheetLayoutError(
            f"{len(rows)} rows is not a whole number of {BLOCK_SIZE}-row blocks"
        ) from err


def _sheet_row(number: int) -> int:
    """1-based sheet row where block `number` (1-based) starts."""
    return (number - 1) * BLOCK_SIZE + 1


def _check_labels(block: Sequence[Sequence[str]], columns: Mapping[str, int], number: int) -> None:
    """Raise if the block's metadata labels aren't _META_LABELS in order (rows shifted)."""
    label = columns["Metadata Label"]
    start = _sheet_row(number)
    rows = enumerate(zip(_META_LABELS, block[1:], strict=True), start=1)
    for offset, (expected, row) in rows:
        if row[label] != expected:
            raise SheetLayoutError(
                f"block {number} (sheet row {start}): expected {expected!r} "
                f"at sheet row {start + offset}, found {row[label]!r}"
            )


def _is_template(block: Sequence[Sequence[str]], columns: Mapping[str, int]) -> bool:
    """An unused block: no platform and no picks."""
    _header, *body = block
    no_platform = _meta(body, columns)["Fantasy Platform"] == ""
    return no_platform and not any(_has_pick(row, columns) for row in body)


def _column_positions(header: Sequence[str]) -> dict[str, int]:
    """Map each required column name in the sheet's first row to its position."""
    positions = {name: position for position, name in enumerate(header) if name}
    missing = [name for name in _REQUIRED_COLUMNS if name not in positions]
    if missing:
        raise SheetLayoutError(f"sheet header is missing columns: {missing}")
    return {name: positions[name] for name in _REQUIRED_COLUMNS}


def _parse_team(block: Sequence[Sequence[str]], columns: Mapping[str, int]) -> DraftedTeam:
    _header, *body = block
    meta = _meta(body, columns)

    return DraftedTeam(
        platform=_convert(meta, "Fantasy Platform", Platform),
        league_id=meta["League ID (Required)"],
        league_type=meta["League Type"],
        league_name=meta["League Name"],
        entry_fee_cents=_convert(meta, "Entry Fee", parse_cents),
        draft_speed=meta["Draft Speed"],
        draft_date=_convert(meta, "Draft Start Date", parse_sheet_date),
        draft_pick=_convert(meta, "Draft Pick", int),
        draft_url=meta["Draft URL"],
        tags=_blank_to_none(meta["Tags"]),
        notes=_blank_to_none(meta["Notes"]),
        picks=[_parse_pick(row, columns) for row in body if _has_pick(row, columns)],
    )


def _meta(body: Sequence[Sequence[str]], columns: Mapping[str, int]) -> dict[str, str]:
    """Metadata as {label: value}, e.g. {"Entry Fee": "$3.00"}."""
    label, value = columns["Metadata Label"], columns["Metadata"]
    return {row[label]: row[value] for row in body}


def _convert[T](meta: Mapping[str, str], label: str, parse: Callable[[str], T]) -> T:
    """Parse one metadata cell, naming its label in any error."""
    try:
        return parse(meta[label])
    except ValueError as err:
        raise ValueError(f"{label}: {err}") from err


def _parse_pick(row: Sequence[str], columns: Mapping[str, int]) -> DraftPick:
    pick = {header: row[position] for header, position in columns.items()}
    return DraftPick(
        round=int(pick["Round"]),
        overall=int(pick["Pick #"]),
        name=pick["Player Name"],
        slot=pick["Pos #"],
        nfl_team=pick["Team"],
    )


def _has_pick(row: Sequence[str], columns: Mapping[str, int]) -> bool:
    return row[columns["Player Name"]] != ""


def _blank_to_none(value: str) -> str | None:
    return value or None
