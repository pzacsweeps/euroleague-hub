"""
Decides whether a scheduled run should update anything.

    python scripts/auto.py injuries   -> due on game days: once in the morning,
                                         and once ~30 min before the first tip-off
    python scripts/auto.py stats      -> due the morning after a round is complete

Prints the decision and, inside GitHub Actions, writes `due=true|false` and
`slot=<name>` to $GITHUB_OUTPUT. `--mark <slot>` records that a slot ran
(stored in data/auto_state.json) so each slot fires once per day / round.

Game times come live from the official EuroLeague schedule, so postponed or
moved games are handled automatically.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

SEASON = os.environ.get("EL_SEASON", "E2026")
API = f"https://api-live.euroleague.net/v2/competitions/E/seasons/{SEASON}/games"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "data", "auto_state.json")
HUB = os.path.join(ROOT, "data", "hub.json")

MORNING_FROM = (7, 30)          # UTC: first check from 07:30 UTC (07:30 UK in winter, 08:30 in summer)
MORNING_UNTIL = (12, 0)         # give up on the morning slot after noon
PREGAME_FROM = timedelta(minutes=45)   # run when first tip-off is 45..10 min away
PREGAME_UNTIL = timedelta(minutes=10)


def now():
    override = os.environ.get("AUTO_NOW")   # for testing: 2026-11-20T08:00:00Z
    if override:
        return datetime.strptime(override, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {}


def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)


def schedule():
    path = os.environ.get("AUTO_SCHEDULE")  # for testing: a saved games list
    if path:
        with open(path) as f:
            data = json.load(f)
    else:
        req = urllib.request.Request(API, headers={"User-Agent": "euroleague-hub"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    games = data.get("data", data) if isinstance(data, dict) else data
    out = []
    for g in games:
        utc = g.get("utcDate") or g.get("utc")
        if not utc:
            continue
        out.append({"round": g["round"], "played": bool(g.get("played")),
                    "utc": datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)})
    return out


def injuries_due(t, games, st):
    today = t.date().isoformat()
    todays = sorted(g["utc"] for g in games if g["utc"].date() == t.date())
    if not todays:
        return False, "no games today"
    first = todays[0]
    done = st.get("injuries", {})
    if t < first - PREGAME_UNTIL and first - t <= PREGAME_FROM:
        if done.get("pregame") != today:
            return True, f"pregame (first tip-off {first:%H:%M} UTC)"
        return False, "pregame already done today"
    m_from = t.replace(hour=MORNING_FROM[0], minute=MORNING_FROM[1], second=0, microsecond=0)
    m_until = t.replace(hour=MORNING_UNTIL[0], minute=MORNING_UNTIL[1], second=0, microsecond=0)
    if m_from <= t < min(m_until, first - PREGAME_FROM) and done.get("morning") != today:
        return True, "morning"
    return False, f"nothing due (first tip-off {first:%H:%M} UTC)"


def stats_due(t, games, st):
    rounds = {}
    for g in games:
        rounds.setdefault(g["round"], []).append(g)
    complete = [r for r, gs in rounds.items() if all(x["played"] for x in gs)]
    if not complete:
        return False, "no complete round yet", None
    latest = max(complete)
    have = st.get("stats", {}).get("round")
    if have is None and os.path.exists(HUB):
        # first run: treat the round already in hub.json as done if it is complete there
        with open(HUB) as f:
            hub = json.load(f)
        hg = {}
        for g in hub.get("games", []):
            hg.setdefault(g["round"], []).append(g["played"])
        done_rounds = [r for r, p in hg.items() if all(p)]
        have = max(done_rounds) if done_rounds else None
    if have is not None and latest <= have:
        return False, f"round {latest} already in the hub", latest
    last_game = max(x["utc"] for x in rounds[latest])
    if t.date() <= last_game.date():
        return False, f"round {latest} finished today, waiting for tomorrow morning", latest
    return True, f"round {latest} complete", latest


def emit(due, slot, why):
    print(f"due={str(due).lower()} slot={slot} :: {why}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"due={str(due).lower()}\nslot={slot}\n")


def main():
    kind = sys.argv[1]
    st = load_state()
    t = now()
    if "--mark" in sys.argv:
        slot = sys.argv[sys.argv.index("--mark") + 1]
        if kind == "injuries" and slot in ("morning", "pregame"):
            st.setdefault("injuries", {})[slot] = t.date().isoformat()
        elif kind == "stats" and slot.startswith("round-") and slot[6:].isdigit():
            st.setdefault("stats", {})["round"] = int(slot.split("-", 1)[1])
        st.setdefault("lastRun", {})[kind] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        save_state(st)
        print(f"marked {kind} {slot}")
        return
    games = schedule()
    if kind == "injuries":
        due, why = injuries_due(t, games, st)
        emit(due, "pregame" if why.startswith("pregame") else "morning", why)
    else:
        due, why, rnd = stats_due(t, games, st)
        emit(due, f"round-{rnd}", why)


if __name__ == "__main__":
    main()
