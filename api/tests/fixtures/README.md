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
