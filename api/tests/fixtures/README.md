# Test fixtures

## google_sheet_teams.csv

Six blocks cut from the best-ball sheet's published CSV (teams tab), in sheet order, in
Google's exact export format: 30 columns, CRLF line endings, minimal quoting.

| Block | Source block | Covers |
|---|---|---|
| 1 | 1 | Underdog, 20 picks; the only row with every column header |
| 2 | 6 | DraftKings, `$0.00` entry fee |
| 3 | 31 | Drafters, 20 picks |
| 4 | 218 | Underdog tournament, 18 picks |
| 5 | 398 | DraftKings with its draft URL pasted into Entry Fee (a real data-entry error) |
| 6 | 770 | Empty template block |

Sanitized before committing:
- League IDs and draft URLs replaced with fakes (`00000000-...-00000000000N` / `10000000N`).
- Pod Size, Contest URL, placements, Winnings, Roster Nickname, Co-manager(s), Tags and
  Notes blanked.
- Columns H onward (derived stats the parser doesn't read) blanked.

Kept as-is: labels, platform, league type and name, entry fee, draft speed, date, draft
position, and picks (round, overall, player, slot, NFL team), which are public draft data.

Never commit an unsanitized export: the live sheet has personal notes, winnings and real
contest entry IDs.

## google_sheet_playoff_rosters.csv

Three blocks in the layout of the playoff sheet's Rosters tab: 30 columns, CRLF line endings.
Built from cell values read through the Sheets API (the 2025 playoff sheet isn't published),
so quoting follows Python's csv writer rather than Google's export.

| Block | Source block | Covers |
|---|---|---|
| 1 | 1 | DraftKings, 12 picks; the first row's partial header (`0`, blank Metadata and Player Name) |
| 2 | 4 | Underdog, 10 picks |
| 3 | n/a | Empty template block |

Team and Pos # are blank, as in the sheet before the ADP Import tab is filled in.

Sanitized before committing: league IDs and draft URLs replaced with fakes; Draft Progress,
Contest URL, placements, Winnings, Roster Nickname, Co-manager(s), Tags and Notes blanked;
columns H onward blanked.

## draftkings_*

Real DraftKings responses, cached by the old app during the 2026 season.

| File | Response | Covers |
|---|---|---|
| `draftkings_mycontests.html` | My Contests page: a minimal HTML shell around the real live contests list, trimmed to 2 contests | The contest list; both best-ball draft groups |
| `draftkings_leaderboard_12.json` | Megacontest leaderboard, contest `100000001` | 12 teams, `fixture-me` 6th (outside the cutoff) |
| `draftkings_leaderboard_6.json` | Megacontest leaderboard, contest `100000002` | A 6-team league, `fixture-me` 2nd |

Sanitized before committing:
- Usernames replaced: `fixture-me` for the account owner, `userNN` for everyone else,
  consistently across files.
- Contest, entry, user and lineup IDs replaced with fakes (`10000000N`, `9000NN` draft
  groups, `00000000-0000-4000-8000-...` keys).
- Winnings, prize pools and prize IDs zeroed.

Kept as-is: ranks, fantasy points, contest names, entry fees and dates.

Never commit an unsanitized response: they include other users' usernames and account keys.
