#!/usr/bin/env python3
"""
update_data.py — Fetch the Cubs' season data from the MLB Stats API
and write it to data.json for the Cubs Almanac to consume.

Uses only Python's standard library; no pip install required.
Runs nightly (or every few hours) via GitHub Actions.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
import sys

CUBS_TEAM_ID = 112
SEASON_YEAR  = 2026
NL_CENTRAL_DIVISION_ID = 205
NL_LEAGUE_ID = 104

# Map MLB API team abbreviations to the abbreviations used in the HTML.
# Most match exactly; these are the exceptions.
ABBR_MAP = {
    "CHW": "CWS",
    "TBR": "TB",
    "KCR": "KC",
    "SDP": "SD",
    "SFG": "SF",
    "WSN": "WSH",
}


def normalize_abbr(a: str) -> str:
    return ABBR_MAP.get(a, a)


# Hand-crafted abbreviations for when the API doesn't return one.
# Keyed by the last word of the team name (the team nickname).
NICKNAME_TO_ABBR = {
    "Angels": "LAA", "Astros": "HOU", "Athletics": "ATH",
    "Blue Jays": "TOR", "Braves": "ATL", "Brewers": "MIL",
    "Cardinals": "STL", "Cubs": "CHC", "Diamondbacks": "AZ",
    "Dodgers": "LAD", "Giants": "SF", "Guardians": "CLE",
    "Mariners": "SEA", "Marlins": "MIA", "Mets": "NYM",
    "Nationals": "WSH", "Orioles": "BAL", "Padres": "SD",
    "Phillies": "PHI", "Pirates": "PIT", "Rangers": "TEX",
    "Rays": "TB", "Red Sox": "BOS", "Reds": "CIN",
    "Rockies": "COL", "Royals": "KC", "Tigers": "DET",
    "Twins": "MIN", "White Sox": "CWS", "Yankees": "NYY",
}


def derive_abbr_from_name(name: str) -> str:
    """Best-effort abbreviation from a team name like 'Washington Nationals'."""
    if not name:
        return ""
    # Try the full nickname-match first (handles "Red Sox", "Blue Jays", "White Sox")
    for nickname, abbr in NICKNAME_TO_ABBR.items():
        if name.endswith(nickname):
            return abbr
    # Fallback: uppercase first 3 letters of the last word
    parts = name.strip().split()
    return parts[-1][:3].upper() if parts else ""


def http_get_json(url: str):
    """Fetch a URL and parse it as JSON. Raises on any failure."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "cubs-almanac-updater/1.0 (github actions)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return json.loads(resp.read().decode("utf-8"))


def fetch_schedule():
    """Fetch the Cubs' full regular-season schedule and return the parsed list."""
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={CUBS_TEAM_ID}&season={SEASON_YEAR}&gameType=R"
        f"&hydrate=team"
    )
    data = http_get_json(url)
    games = []

    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            # Defensive: skip anything that isn't regular season
            if g.get("gameType", "R") != "R":
                continue

            home_team = g["teams"]["home"]["team"]
            away_team = g["teams"]["away"]["team"]
            is_home = home_team["id"] == CUBS_TEAM_ID
            opp = away_team if is_home else home_team

            # Try every known field for the abbreviation; if all fail, build one
            # from the team name (e.g. "Washington Nationals" -> "WAS") rather
            # than defaulting to "OPP" for every game.
            opp_abbr_raw = (
                opp.get("abbreviation")
                or opp.get("teamCode")
                or opp.get("fileCode")
                or derive_abbr_from_name(opp.get("teamName") or opp.get("name") or "")
                or "OPP"
            )
            opp_abbr = normalize_abbr(opp_abbr_raw.upper())

            # Date in YYYY-MM-DD — officialDate respects league calendar day
            date_str = (g.get("officialDate") or g.get("gameDate", ""))[:10]

            # Game time in Central
            time_str = "TBD"
            game_date = g.get("gameDate")
            if game_date:
                try:
                    # Parse ISO 8601 UTC timestamp
                    dt_utc = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                    # Convert to Central — use offset since stdlib doesn't have tzdata always
                    # Chicago is UTC-6 (CST) or UTC-5 (CDT). Baseball season is mostly CDT.
                    # For accuracy across the season we'll use zoneinfo if available.
                    try:
                        from zoneinfo import ZoneInfo
                        dt_ct = dt_utc.astimezone(ZoneInfo("America/Chicago"))
                    except Exception:
                        # Fallback: subtract 5 hours (CDT). Acceptable since season is mostly CDT.
                        from datetime import timedelta
                        dt_ct = dt_utc - timedelta(hours=5)
                    hour = dt_ct.hour
                    minute = dt_ct.minute
                    suffix = "AM" if hour < 12 else "PM"
                    h12 = hour % 12 or 12
                    time_str = f"{h12}:{minute:02d} {suffix}"
                except Exception:
                    pass

            # Result if final
            result = None
            status = g.get("status", {}).get("abstractGameState", "")
            if status == "Final":
                home_score = g["teams"]["home"].get("score")
                away_score = g["teams"]["away"].get("score")
                if isinstance(home_score, int) and isinstance(away_score, int):
                    if is_home:
                        result = {"us": home_score, "them": away_score}
                    else:
                        result = {"us": away_score, "them": home_score}

            games.append({
                "date": date_str,
                "opp": opp_abbr,
                "home": is_home,
                "time": time_str,
                "result": result,
            })

    # Sort by date for determinism (the API usually returns sorted but make sure)
    games.sort(key=lambda x: (x["date"], x["time"]))
    return games


def fetch_standings():
    """Fetch the NL Central standings and return parsed team records."""
    url = (
        f"https://statsapi.mlb.com/api/v1/standings"
        f"?leagueId={NL_LEAGUE_ID}&season={SEASON_YEAR}&standingsTypes=regularSeason"
    )
    data = http_get_json(url)
    standings = []

    for rec in data.get("records", []):
        division = rec.get("division", {})
        if division.get("id") != NL_CENTRAL_DIVISION_ID:
            continue
        for tr in rec.get("teamRecords", []):
            standings.append({
                "team": tr["team"]["name"],
                "abbr": normalize_abbr(tr["team"].get("abbreviation", "")),
                "w": tr.get("wins", 0),
                "l": tr.get("losses", 0),
            })

    # Sort by wins desc, losses asc — matches "first place by record"
    standings.sort(key=lambda s: (-s["w"], s["l"]))
    return standings


def main():
    try:
        schedule = fetch_schedule()
    except Exception as e:
        print(f"ERROR: schedule fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        standings = fetch_standings()
    except Exception as e:
        print(f"ERROR: standings fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    if not schedule:
        print("ERROR: schedule came back empty", file=sys.stderr)
        sys.exit(1)
    if not standings:
        print("ERROR: standings came back empty", file=sys.stderr)
        sys.exit(1)

    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "schedule": schedule,
        "standings": standings,
    }

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote data.json: {len(schedule)} games, {len(standings)} teams")


if __name__ == "__main__":
    main()
