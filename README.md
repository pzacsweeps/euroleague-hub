# EuroLeague Hub

Schedule, team matchups, defence vs position and every player's game log for the EuroLeague regular season.

## Tabs
- **Schedule**: every round, or one team's full season (tap a team chip). Tap a game to open its matchup.
- **Matchup**: team stat comparison with league ranks, defence vs position (what each side allows to Guards, Forwards and Centers), and each player's PTS / REB / AST / 3PM next to the opponent's rank against that position. #1 = the defence that gives up the most.
- **Game Log**: every player's line for every game. Filter by team, position, player or last 5/10. With one player selected, Prop Check counts how often they went over a line.

## Data
`scripts/update_data.py` pulls the official EuroLeague API (schedule + per-game box scores, which include each player's position) and writes `data/hub.json`. Box scores already stored in `data/raw.json` aren't downloaded again.

The GitHub Action in `.github/workflows/update-data.yml` runs it every Saturday at 06:00 UTC, once the round is done. To refresh by hand: Actions tab → **Update EuroLeague data** → **Run workflow**.

To switch season, change `EL_SEASON` (default `E2026`) in the script.
