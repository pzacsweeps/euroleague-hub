# EuroLeague Hub

Schedule, team matchups, defence vs position and every player's game log for the EuroLeague regular season.

## Tabs
- **Schedule**: every round, or one team's full season (tap a team chip). Tap a game to open its matchup.
- **Matchup**: team stat comparison with league ranks, defence vs position (what each side allows to Guards, Forwards and Centers), and each player's PTS / REB / AST / 3PM next to the opponent's rank against that position. #1 = the defence that gives up the most.
- **Injuries**: the BasketNews EuroLeague injury report (status, round, short reason, expected return) for teams playing next round or all teams, with each player's season averages. Credited and linked to BasketNews.
- **Game Log**: every player's line for every game. Filter by team, position, player or last 5/10. With one player selected, Prop Check counts how often they went over a line.

## Data
`scripts/update_data.py` pulls the official EuroLeague API (schedule + per-game box scores, which include each player's position) and writes `data/hub.json`. Box scores already stored in `data/raw.json` aren't downloaded again.

The GitHub Action in `.github/workflows/update-data.yml` checks every morning at 06:17 UTC and updates the stats when a round has been completed (the morning after its last game). To refresh by hand: Actions tab → **Update EuroLeague data** → **Run workflow**.

To switch season, change `EL_SEASON` (default `E2026`) in the script.

## Injuries
`scripts/update_injuries.py` reads the [BasketNews injury report](https://basketnews.com/news-212393-euroleague-injury-report-updated-daily.html) and writes `data/injuries.json`. It runs automatically on game days, once in the morning (from 07:30 UTC) and once about 30 minutes before the first tip-off; game times come live from the EuroLeague schedule (`scripts/auto.py`). To run it by hand: Actions tab → **Update injuries** → **Run workflow** (works from the GitHub mobile app too). Injured players are also flagged on the Matchup tab.
