"""
EuroLeague Hub data pipeline.

Stage 1 (fetch): pulls the season schedule and every played game's box score
from the official EuroLeague API and stores a compact copy in data/raw.json.
Box scores already stored are not downloaded again.

Stage 2 (build): turns raw.json into data/hub.json, which the site reads:
schedule, team season stats with ranks, per-player averages, defence vs
position (what each team allows to Guards / Forwards / Centers) and the full
player game log.

Usage:
    python scripts/update_data.py            # fetch + build
    python scripts/update_data.py --build    # build only from existing raw.json
"""
import json
import re
import os
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

SEASON = os.environ.get("EL_SEASON", "E2026")
API = "https://api-live.euroleague.net"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw.json")
OUT = os.path.join(ROOT, "data", "hub.json")

# Player row layout in raw.json (keep in sync with the site)
P_FIELDS = ["id", "name", "pos", "sec", "pts", "reb", "ast", "fg3m", "fg3a",
            "start", "oreb", "dreb", "stl", "blk", "tov", "fgm", "fga",
            "ftm", "fta", "pir"]
# Team total row layout
T_FIELDS = ["pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "fgm",
            "fga", "fg3m", "fg3a", "ftm", "fta", "pf", "sec"]
POS_MAP = {"Guard": "G", "Forward": "F", "Center": "C"}


def get(path, tries=4):
    url = API + path
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "euroleague-hub"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network hiccup, retry with backoff
            if i == tries - 1:
                raise
            print(f"  retry {url}: {e}")
            time.sleep(2 * (i + 1))


ROMAN = {"II", "III", "IV", "V"}


def clean_name(n):
    """Tidy a player name whether it arrives ALL CAPS or already capitalised."""
    out = []
    for w in n.split():
        bare = w.rstrip(".")
        if bare.upper() == "JR":
            out.append("Jr."); continue
        if bare.upper() in ROMAN and out:
            out.append(bare.upper()); continue
        if len(bare) <= 3 and not any(c in "aeiouyAEIOUY" for c in bare):
            out.append(bare.upper()); continue  # initials: TJ, DJ, PJ
        w = w.lower()
        w = "-".join(x[:1].upper() + x[1:] for x in w.split("-"))
        w = "'".join(x[:1].upper() + x[1:] for x in w.split("'"))
        w = re.sub(r"(^|-)Mc([a-z])", lambda m: m.group(1) + "Mc" + m.group(2).upper(), w)
        out.append(w)
    return " ".join(out)


def name_fmt(raw):
    # "DE COLO, NANDO" -> "Nando De Colo"
    if "," in raw:
        last, first = raw.split(",", 1)
        raw = f"{first.strip()} {last.strip()}"
    return clean_name(raw)


def compact_side(side):
    players = []
    for p in side.get("players", []):
        info, s = p["player"], p["stats"]
        if not s.get("timePlayed"):
            continue  # DNP
        players.append([
            info["person"]["code"], name_fmt(info["person"]["name"]),
            POS_MAP.get(info.get("positionName") or "", "F"),
            int(s.get("timePlayed") or 0), s.get("points", 0), s.get("totalRebounds", 0),
            s.get("assistances", 0), s.get("fieldGoalsMade3", 0), s.get("fieldGoalsAttempted3", 0),
            1 if s.get("startFive") else 0, s.get("offensiveRebounds", 0),
            s.get("defensiveRebounds", 0), s.get("steals", 0), s.get("blocksFavour", 0),
            s.get("turnovers", 0), s.get("fieldGoalsMadeTotal", 0),
            s.get("fieldGoalsAttemptedTotal", 0), s.get("freeThrowsMade", 0),
            s.get("freeThrowsAttempted", 0), s.get("valuation", 0),
        ])
    t = side.get("total", {})
    total = [t.get("points", 0), t.get("totalRebounds", 0), t.get("offensiveRebounds", 0),
             t.get("defensiveRebounds", 0), t.get("assistances", 0), t.get("steals", 0),
             t.get("blocksFavour", 0), t.get("turnovers", 0), t.get("fieldGoalsMadeTotal", 0),
             t.get("fieldGoalsAttemptedTotal", 0), t.get("fieldGoalsMade3", 0),
             t.get("fieldGoalsAttempted3", 0), t.get("freeThrowsMade", 0),
             t.get("freeThrowsAttempted", 0), t.get("foulsCommited", 0),
             int(t.get("timePlayed") or 0)]
    return {"players": players, "total": total}


def fetch():
    raw = {"season": SEASON, "games": [], "teams": {}, "box": {}}
    if os.path.exists(RAW):
        with open(RAW) as f:
            old = json.load(f)
        if old.get("season") == SEASON:
            raw["box"] = old.get("box", {})

    sched = get(f"/v2/competitions/E/seasons/{SEASON}/games")
    sched = sched.get("data", sched) if isinstance(sched, dict) else sched
    for g in sched:
        if (g.get("phaseType") or {}).get("code") not in (None, "RS"):
            # keep playoffs etc. too, tagged by phase
            pass
        h, a = g["local"], g["road"]
        for side in (h, a):
            c = side["club"]
            raw["teams"][c["code"]] = {"name": c.get("name"), "short": c.get("abbreviatedName") or c.get("name"),
                                       "crest": (c.get("images") or {}).get("crest")}
        raw["games"].append({
            "code": g["gameCode"], "round": g["round"],
            "phase": (g.get("phaseType") or {}).get("code", "RS"),
            "utc": g.get("utcDate"), "local": g.get("localDate"),
            "home": h["club"]["code"], "away": a["club"]["code"],
            "hs": h.get("score"), "as": a.get("score"),
            "played": bool(g.get("played")),
            "venue": (g.get("venue") or {}).get("name"),
        })

    todo = [g for g in raw["games"] if g["played"] and str(g["code"]) not in raw["box"]]
    print(f"{len(raw['games'])} games in schedule, {len(todo)} new box scores to fetch")
    for g in todo:
        d = get(f"/v3/competitions/E/seasons/{SEASON}/games/{g['code']}/stats")
        raw["box"][str(g["code"])] = {"home": compact_side(d["local"]), "away": compact_side(d["road"])}
        time.sleep(0.25)

    raw["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(RAW, "w") as f:
        json.dump(raw, f, separators=(",", ":"))
    return raw


def rank(values, higher_is_better=True):
    """values: dict team->value. Returns dict team->rank (1 = best)."""
    order = sorted(values, key=lambda k: values[k], reverse=higher_is_better)
    return {t: i + 1 for i, t in enumerate(order)}


def build(raw):
    games = sorted(raw["games"], key=lambda g: (g["round"], g["utc"] or ""))
    box = raw["box"]
    P = {f: i for i, f in enumerate(P_FIELDS)}
    T = {f: i for i, f in enumerate(T_FIELDS)}
    for b in box.values():
        for side in b.values():
            for row in side["players"]:
                row[P["name"]] = clean_name(row[P["name"]])

    team_games = defaultdict(list)       # team -> list of (own total, opp total, won, gameCode)
    allowed = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # team -> pos -> stat sums
    allowed_games = defaultdict(int)
    players = {}
    log = []

    for g in games:
        b = box.get(str(g["code"]))
        if not g["played"] or not b:
            continue
        for side, opp_side, team, opp in (("home", "away", g["home"], g["away"]),
                                          ("away", "home", g["away"], g["home"])):
            own, other = b[side], b[opp_side]
            won = own["total"][T["pts"]] > other["total"][T["pts"]]
            team_games[team].append((own["total"], other["total"], won, g["code"]))
            # what `team` allowed = opponent players' production, by position
            allowed_games[team] += 1
            for row in other["players"]:
                pos = row[P["pos"]]
                a = allowed[team][pos]
                for k in ("pts", "reb", "ast", "fg3m"):
                    a[k] += row[P[k]]
            for row in own["players"]:
                pid = row[P["id"]]
                pl = players.setdefault(pid, {"id": pid, "name": row[P["name"]], "pos": row[P["pos"]],
                                              "team": team, "gp": 0, "min": 0, "pts": 0, "reb": 0,
                                              "ast": 0, "fg3m": 0, "fg3a": 0, "last": 0})
                pl["team"] = team  # latest team (handles mid-season moves)
                pl["gp"] += 1
                pl["min"] += row[P["sec"]] / 60
                for k in ("pts", "reb", "ast", "fg3m", "fg3a"):
                    pl[k] += row[P[k]]
                pl["last"] = g["round"]
                log.append([g["round"], g["code"], g["utc"], team, opp, "H" if side == "home" else "A",
                            "W" if won else "L", pid, row[P["name"]], row[P["pos"]],
                            round(row[P["sec"]] / 60, 1), row[P["pts"]], row[P["reb"]], row[P["ast"]],
                            row[P["fg3m"]], row[P["fg3a"]], row[P["start"]], row[P["stl"]],
                            row[P["blk"]], row[P["tov"]], row[P["pir"]]])

    # ---- team season stats ----
    teams = {}
    for t, rows in team_games.items():
        n = len(rows)
        s = lambda i, which=0: sum(r[which][i] for r in rows)
        pts, opp = s(T["pts"]), s(T["pts"], 1)
        # possessions estimate: FGA - OREB + TOV + 0.44*FTA, averaged with the opponent's
        poss_own = s(T["fga"]) - s(T["oreb"]) + s(T["tov"]) + 0.44 * s(T["fta"])
        poss_opp = s(T["fga"], 1) - s(T["oreb"], 1) + s(T["tov"], 1) + 0.44 * s(T["fta"], 1)
        poss = (poss_own + poss_opp) / 2
        mins = s(T["sec"]) / 60 or 40 * n   # team timePlayed = game length in seconds (2400 = 40 min)
        last5 = [("W" if r[2] else "L") for r in rows[-5:]]
        teams[t] = {
            "gp": n, "w": sum(1 for r in rows if r[2]), "l": sum(1 for r in rows if not r[2]),
            "ppg": pts / n, "oppg": opp / n, "diff": (pts - opp) / n,
            "pace": poss / mins * 40, "ortg": pts / poss * 100, "drtg": opp / poss * 100,
            "rpg": s(T["reb"]) / n, "orpg": s(T["oreb"]) / n, "apg": s(T["ast"]) / n,
            "spg": s(T["stl"]) / n, "bpg": s(T["blk"]) / n, "tpg": s(T["tov"]) / n,
            "fgp": 100 * s(T["fgm"]) / max(1, s(T["fga"])),
            "tpp": 100 * s(T["fg3m"]) / max(1, s(T["fg3a"])),
            "tpm": s(T["fg3m"]) / n,
            "ftp": 100 * s(T["ftm"]) / max(1, s(T["fta"])),
            "opp_tpp": 100 * s(T["fg3m"], 1) / max(1, s(T["fg3a"], 1)),
            "opp_rpg": s(T["reb"], 1) / n,
            "form": last5,
        }
    lower_better = {"oppg", "drtg", "tpg", "opp_tpp", "opp_rpg"}
    for k in ("ppg", "oppg", "diff", "pace", "ortg", "drtg", "rpg", "orpg", "apg", "spg", "bpg",
              "tpg", "fgp", "tpp", "tpm", "ftp", "opp_tpp", "opp_rpg"):
        r = rank({t: v[k] for t, v in teams.items()}, higher_is_better=k not in lower_better)
        for t in teams:
            teams[t].setdefault("rank", {})[k] = r[t]
    for t, info in raw["teams"].items():
        teams.setdefault(t, {"gp": 0, "w": 0, "l": 0, "form": [], "rank": {}})
        teams[t].update(info)

    # ---- defence vs position ----
    dvp = {}
    for t in teams:
        n = allowed_games.get(t, 0)
        dvp[t] = {pos: {k: (allowed[t][pos][k] / n if n else 0) for k in ("pts", "reb", "ast", "fg3m")}
                  for pos in ("G", "F", "C")}
    # rank 1 = allows the MOST (best matchup for the player), 20 = toughest
    for pos in ("G", "F", "C"):
        for k in ("pts", "reb", "ast", "fg3m"):
            r = rank({t: dvp[t][pos][k] for t in dvp if allowed_games.get(t)}, higher_is_better=True)
            for t in dvp:
                dvp[t][pos].setdefault("rank", {})[k] = r.get(t)
    # league average per position (per team-game) for colouring
    lg = {pos: {k: (sum(dvp[t][pos][k] for t in dvp if allowed_games.get(t)) /
                     max(1, sum(1 for t in dvp if allowed_games.get(t))))
                for k in ("pts", "reb", "ast", "fg3m")} for pos in ("G", "F", "C")}

    # ---- player averages ----
    plist = []
    for pl in players.values():
        n = pl["gp"]
        plist.append({"id": pl["id"], "name": pl["name"], "pos": pl["pos"], "team": pl["team"], "gp": n,
                      "min": round(pl["min"] / n, 1), "pts": round(pl["pts"] / n, 1),
                      "reb": round(pl["reb"] / n, 1), "ast": round(pl["ast"] / n, 1),
                      "fg3m": round(pl["fg3m"] / n, 1),
                      "tpp": round(100 * pl["fg3m"] / pl["fg3a"], 1) if pl["fg3a"] else None})
    plist.sort(key=lambda p: -p["min"])

    def r1(x):
        return round(x, 1) if isinstance(x, float) else x
    for t in teams.values():
        for k, v in list(t.items()):
            t[k] = r1(v)
    for t in dvp.values():
        for pos in t.values():
            for k in ("pts", "reb", "ast", "fg3m"):
                pos[k] = round(pos[k], 1)
    for pos in lg.values():
        for k in pos:
            pos[k] = round(pos[k], 1)

    played_rounds = sorted({g["round"] for g in games if g["played"]})
    hub = {
        "season": raw["season"],
        "updated": raw.get("fetched"),
        "lastRound": played_rounds[-1] if played_rounds else 0,
        "rounds": sorted({g["round"] for g in games}),
        "teams": teams,
        "games": games,
        "dvp": dvp,
        "dvpLeague": lg,
        "players": plist,
        "logFields": ["round", "game", "utc", "team", "opp", "ha", "res", "id", "name", "pos", "min",
                      "pts", "reb", "ast", "fg3m", "fg3a", "start", "stl", "blk", "tov", "pir"],
        "log": log,
    }
    with open(OUT, "w") as f:
        json.dump(hub, f, separators=(",", ":"))
    print(f"hub.json: {len(teams)} teams, {len(games)} games, {len(plist)} players, {len(log)} log rows, "
          f"{os.path.getsize(OUT)//1024} KB")


if __name__ == "__main__":
    if "--build" in sys.argv:
        with open(RAW) as f:
            build(json.load(f))
    else:
        build(fetch())
