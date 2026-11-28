"""
Decides what the scheduled runs should update. The EuroLeague schedule is read
once per day (morning run); the pre-game checks only read the saved state.

    python scripts/auto.py morning   -> once a day: reads the schedule, saves today's
                                        first tip-off, says whether stats and/or
                                        injuries are due
    python scripts/auto.py pregame   -> afternoon/evening checks: is it ~30 min before
                                        today's first tip-off? (no network call)
    python scripts/auto.py <injuries|stats> --mark <slot>   -> record that a slot ran

Inside GitHub Actions the decisions are written to $GITHUB_OUTPUT.
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

# GitHub runs scheduled checks late and sometimes only ~hourly, so the window is
# wide: any check in the 100 min before the first tip-off pulls the report, and a
# later check pulls it again if the last pull is 30+ min old (latest data wins).
PREGAME_FROM = timedelta(minutes=100)
PREGAME_UNTIL = timedelta(minutes=0)
PREGAME_REFRESH = timedelta(minutes=30)


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


def emit_many(**kv):
    print(" ".join(f"{k}={v}" for k, v in kv.items()))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={str(v).lower() if isinstance(v, bool) else v}\n")


def save_today(st, t, games):
    todays = sorted(g["utc"] for g in games if g["utc"].date() == t.date())
    st["today"] = {"date": t.date().isoformat(),
                   "firstTip": todays[0].strftime("%Y-%m-%dT%H:%M:%SZ") if todays else None,
                   "games": len(todays)}
    save_state(st)
    return st["today"]


def main():
    kind = sys.argv[1]
    st = load_state()
    t = now()
    if "--mark" in sys.argv:
        slot = sys.argv[sys.argv.index("--mark") + 1]
        if kind == "injuries" and slot in ("morning", "pregame"):
            st.setdefault("injuries", {})[slot] = t.date().isoformat()
            if slot == "pregame":
                st["injuries"]["pregameAt"] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif kind == "stats" and slot.startswith("round-") and slot[6:].isdigit():
            st.setdefault("stats", {})["round"] = int(slot.split("-", 1)[1])
        st.setdefault("lastRun", {})[kind] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        save_state(st)
        print(f"marked {kind} {slot}")
        return

    if kind == "morning":
        games = schedule()                      # the one schedule read of the day
        today = save_today(st, t, games)
        s_due, s_why, rnd = stats_due(t, games, st)
        i_due = bool(today["games"]) and st.get("injuries", {}).get("morning") != today["date"]
        print(f"stats: {s_why} | injuries: {str(today['games']) + ' game(s) today, first at ' + today['firstTip'] if today['games'] else 'no games today'}")
        emit_many(stats=s_due, round=f"round-{rnd}", injuries=i_due)
        return

    if kind == "pregame":
        today = st.get("today")
        if not today or today.get("date") != t.date().isoformat():
            # morning run missed: read the schedule once and save it for the rest of the day
            today = save_today(st, t, schedule())
        due, why = False, "no games today"
        if today.get("firstTip"):
            first = datetime.strptime(today["firstTip"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            last = st.get("injuries", {}).get("pregameAt")
            last = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if last else None
            if t >= first:
                why = f"first tip-off {first:%H:%M} UTC has passed"
            elif t < first - PREGAME_FROM:
                why = f"not yet (first tip-off {first:%H:%M} UTC)"
            elif last and last.date() == t.date() and t - last < PREGAME_REFRESH:
                why = f"pulled at {last:%H:%M} UTC, recent enough"
            else:
                due, why = True, f"first tip-off {first:%H:%M} UTC in {int((first - t).total_seconds() // 60)} min"
        print(why)
        emit_many(due=due)
        return

    sys.exit(f"unknown command {kind}")


if __name__ == "__main__":
    main()
