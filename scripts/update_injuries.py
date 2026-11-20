"""
EuroLeague Hub injury report.

Reads the BasketNews EuroLeague injury report and writes data/injuries.json:
for every team, each listed player's position, status, round and a short
reason / expected return that this script extracts itself (BasketNews' own
notes are not copied; the site links to their report for the full detail).

Players are matched to the hub's player ids (data/hub.json) so the Matchup tab
can flag them.

Usage:
    python scripts/update_injuries.py                 # fetch from basketnews.com
    python scripts/update_injuries.py --file page.html # parse a saved copy
"""
import html
import json
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

SOURCE = "https://basketnews.com/news-212393-euroleague-injury-report-updated-daily.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB = os.path.join(ROOT, "data", "hub.json")
OUT = os.path.join(ROOT, "data", "injuries.json")

# distinctive words in each club's name -> EuroLeague API team code
TEAM_KEYS = [
    ("anadolu", "IST"), ("efes", "IST"), ("olimpia", "MIL"), ("milan", "MIL"), ("besiktas", "BES"),
    ("zvezda", "RED"), ("dubai", "DUB"), ("bayern", "MUN"), ("barcelona", "BAR"), ("fenerbahce", "ULK"),
    ("hapoel", "HTA"), ("baskonia", "BAS"), ("asvel", "ASV"), ("maccabi", "TEL"), ("olympiacos", "OLY"),
    ("panathinaikos", "PAN"), ("partizan", "PAR"), ("real madrid", "MAD"), ("valencia", "PAM"),
    ("virtus", "VIR"), ("zalgiris", "ZAL"), ("paris", "PRS"),
]
STATUS_ORDER = ["Out", "Doubtful", "Uncertain", "Game-time", "Ready"]

# (pattern, label) checked in order; first body-part hit wins, extra tags appended
REASONS = [
    (r"achilles", "Achilles"), (r"\bacl\b|cruciate", "ACL"), (r"meniscus|\bknee", "Knee"), (r"ankle", "Ankle"),
    (r"\bcalf", "Calf"), (r"hamstring", "Hamstring"), (r"thigh|quadricep|\bquad\b", "Thigh"), (r"groin|adductor", "Groin"),
    (r"\bhip\b|psoas", "Hip"), (r"\bback (injury|spasm|pain|problem|issue)|lower back|lumbar", "Back"),
    (r"shoulder", "Shoulder"), (r"\bfoot\b|plantar", "Foot"), (r"wrist", "Wrist"),
    (r"\bhand\b|finger|thumb", "Hand"), (r"oblique", "Oblique"), (r"abdominal|abdomen", "Abdominal"),
    (r"concussion|head (injury|blow)", "Head"), (r"\bnose\b|\bface\b|facial|\beye\b", "Face"),
    (r"contusion|bone bruise|\bbruise", "Bruise"), (r"\bleg\b", "Leg"), (r"muscle|strain", "Muscle"),
    (r"illness|\bill\b|\bsick|\bflu\b|virus", "Illness"), (r"personal reason|family reason", "Personal"),
    (r"suspen", "Suspended"), (r"\bfitness\b", "Fitness"), (r"new signing", "New signing"),
    (r"not included in (the )?official euroleague roster|deregistered|not registered", "Not registered"),
    (r"coach'?s decision", "Coach's decision"), (r"\brest\b|load management", "Rest"),
    (r"undisclosed", "Undisclosed"), (r"\binjur", "Injury"),
]
GENERIC = ("Coach's decision", "Undisclosed", "Muscle", "Injury", "Leg", "Fitness", "New signing")
WORDNUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "eight": "8", "a few": "few"}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower().replace("-", " ")).strip()


def team_code(name):
    n = norm(name)
    for key, code in TEAM_KEYS:
        if key in n:
            return code
    return None


def reason_of(comment):
    c = comment.lower()
    tags = []
    for pat, lab in REASONS:
        if re.search(pat, c) and lab not in tags:
            tags.append(lab)
    body = [t for t in tags if t not in GENERIC]
    if body:
        out = body[0]
    elif tags:
        pref = ["Muscle", "Leg", "Fitness", "New signing", "Undisclosed", "Coach's decision", "Injury"]
        out = sorted(tags, key=lambda t: pref.index(t) if t in pref else 99)[0]
        if out == "Undisclosed" and "Injury" in tags:
            out = "Undisclosed injury"
    else:
        out = ""
    if "surgery" in c and out not in ("", "Coach's decision"):
        out += " (surgery)"
    elif "surgery" in c and not out:
        out = "Surgery"
    return out


def return_of(comment, rnd):
    c = comment.lower()
    if "season" in rnd.lower() or "out for (the )?season" in c or "season-ending" in c:
        return "Season"
    m = re.search(r"(?:until|return is|return in|back for|before) round (\d+(?:\s*-\s*\d+)?)", c)
    if m:
        return "R" + m.group(1).replace(" ", "")
    m = re.search(r"(\d+(?:\s*-\s*\d+)?|one|two|three|four|five|six|eight|a few)\s+(week|month)s?", c)
    if m:
        n = WORDNUM.get(m.group(1), m.group(1).replace(" ", ""))
        return f"~{n} {m.group(2)}{'s' if n != '1' else ''}"
    m = re.search(r"(?:until|before|return in|out until|by) (?:the )?(?:(early|mid|late|end of)[- ]?)?(?:the )?(?:end of )?(january|february|march|april|may|june|october|november|december)", c)
    if m:
        part = {"early": "Early ", "mid": "Mid ", "late": "Late ", "end of": "End "}.get(m.group(1) or "", "")
        if "end of" in c[m.start():m.end()] and not part:
            part = "End "
        return part + m.group(2)[:3].capitalize()
    if "indefinite" in c:
        return "Indefinite"
    return ""


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.team, self.in_table, self.depth = [], None, False, 0
        self.tr = None          # current row: {"kind":..., "cells":[...]}
        self.cell = None
        self.published = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if tag == "div" and "date" in cls and "times" in cls and a.get("data-time") and not self.published:
            try:
                self.published = datetime.fromtimestamp(int(a["data-time"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass
        if tag == "table" and "table_02" in cls:
            self.in_table = True
        if not self.in_table:
            return
        if tag == "tr":
            kind = "team" if "team-row" in cls else "banner" if "banner" in cls else "head" if "head" in cls else "row"
            self.tr = {"kind": kind, "cells": []}
        elif tag in ("td", "th") and self.tr is not None:
            self.cell = []
        elif tag == "img" and self.tr is not None and self.tr["kind"] == "team" and not self.tr.get("team"):
            alt = a.get("alt", "")
            if alt and "payabl" not in alt.lower():
                self.tr["team"] = alt

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag in ("td", "th") and self.cell is not None and self.tr is not None:
            self.tr["cells"].append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.tr is not None:
            t = self.tr
            if t["kind"] == "team":
                self.team = t.get("team") or (t["cells"][0] if t["cells"] else None)
            elif t["kind"] == "row" and len(t["cells"]) >= 5 and self.team:
                pos, name, status, rnd, comment = t["cells"][:5]
                self.rows.append({"team": self.team, "pos": pos, "name": html.unescape(name),
                                  "status": status, "round": rnd, "comment": comment})
            self.tr = None
        elif tag == "table":
            self.in_table = False


def match_players(entries, players):
    by_team = {}
    for p in players:
        by_team.setdefault(p["team"], []).append(p)
    for e in entries:
        cands = by_team.get(e["code"], [])
        n = norm(e["name"])
        hit = next((p for p in cands if norm(p["name"]) == n), None)
        if not hit:
            parts = n.split()
            last = parts[-1] if parts else ""
            first = parts[0][:1] if parts else ""
            same_last = [p for p in cands if norm(p["name"]).split()[-1:] == [last]]
            if len(same_last) == 1:
                hit = same_last[0]
            else:
                hit = next((p for p in same_last if norm(p["name"])[:1] == first), None)
        if hit:
            e["pid"] = hit["id"]
            e["gp"], e["min"], e["pts"] = hit["gp"], hit["min"], hit["pts"]
    return entries


def fetch_page():
    """BasketNews sometimes turns automated requests away (403/429) for a few
    minutes; retry with growing waits before giving up."""
    import time
    import urllib.error
    waits = [0, 30, 90, 180]
    last = None
    for i, w in enumerate(waits):
        if w:
            print(f"  BasketNews refused ({last}); retrying in {w}s ({i + 1}/{len(waits)})")
            time.sleep(w)
        try:
            req = urllib.request.Request(SOURCE, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (403, 429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
    sys.exit(f"BasketNews could not be reached after {len(waits)} tries ({last}); keeping the previous report.")


def main():
    if "--file" in sys.argv:
        with open(sys.argv[sys.argv.index("--file") + 1], encoding="utf-8") as f:
            page = f.read()
    else:
        page = fetch_page()

    p = Parser()
    p.feed(page)
    if not p.rows:
        sys.exit("No injury rows found: the BasketNews page layout may have changed.")

    players = []
    if os.path.exists(HUB):
        with open(HUB) as f:
            players = json.load(f).get("players", [])

    entries, unknown = [], set()
    for r in p.rows:
        code = team_code(r["team"])
        if not code:
            unknown.add(r["team"])
            continue
        entries.append({"code": code, "pos": r["pos"], "name": r["name"], "status": r["status"],
                        "round": r["round"], "reason": reason_of(r["comment"]),
                        "back": return_of(r["comment"], r["round"])})
    match_players(entries, players)

    teams = {}
    rank = {s: i for i, s in enumerate(STATUS_ORDER)}
    for e in entries:
        teams.setdefault(e.pop("code"), []).append(e)
    for lst in teams.values():
        lst.sort(key=lambda e: (rank.get(e["status"], 9), -(e.get("min") or 0), e["name"]))

    out = {"source": SOURCE, "sourceName": "BasketNews", "published": p.published,
           "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "teams": teams}
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    matched = sum(1 for l in teams.values() for e in l if e.get("pid"))
    print(f"injuries.json: {len(entries)} players across {len(teams)} teams, {matched} matched to hub stats, "
          f"published {p.published}")
    if unknown:
        print("WARNING unmapped team names:", ", ".join(sorted(unknown)))


if __name__ == "__main__":
    main()
