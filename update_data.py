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

# Marquee Sports Network broadcaster id. Hardcoded because IDs are stable
# across the API while names drift; the Phase 1 probe confirmed this is the
# right primitive for the in-market/blackout test.
MARQUEE_BROADCAST_ID = 5580

# Display-name normalization keyed by broadcaster id. The API name field has
# parentheticals ("TBS (out-of-market only)") and brand drift ("Apple TV"
# vs the official "Apple TV+"), so we don't display it verbatim. New ids
# encountered (MLB Network, Roku, etc.) hit the warn path below.
CHANNEL_NAME_BY_ID = {
    5580: "MARQUEE",       # Marquee Sports Network
    144:  "FOX",
    5235: "TBS",
    6019: "Apple TV+",
    6021: "NBC/Peacock",
    5725: "NBC/Peacock",   # API also issues this id ("NBCSN / Peacock") for some Peacock windows
    5655: "ABC/ESPN",
}

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


def resolve_broadcast(broadcasts, game_pk=None):
    """Pick the channel string for a game from its broadcasts array.

    Rules from the Phase 1 investigation:
      - Filter to TV-only entries (skip AM/FM radio).
      - Dedup by broadcaster id (national broadcasts appear twice, once
        per home/away row).
      - If Marquee Sports Network is present, the channel is MARQUEE
        (Marquee carries every Cubs game except the four exclusive
        national windows; its absence from the array IS the blackout
        signal).
      - Otherwise pick the first national broadcast and normalize via
        CHANNEL_NAME_BY_ID.
      - Otherwise return None and let the page fall through to its
        default (Marquee).
    """
    if not broadcasts:
        return None

    seen_ids = set()
    tv = []
    for b in broadcasts:
        if b.get("type") != "TV":
            continue
        bid = b.get("id")
        if bid in seen_ids:
            continue
        seen_ids.add(bid)
        tv.append(b)

    if not tv:
        return None

    if any(b.get("id") == MARQUEE_BROADCAST_ID for b in tv):
        return "MARQUEE"

    nat = next((b for b in tv if b.get("isNational")), None)
    if nat is None:
        return None

    bid = nat.get("id")
    normalized = CHANNEL_NAME_BY_ID.get(bid)
    if normalized:
        return normalized

    api_name = nat.get("name") or nat.get("callSign") or "Unknown"
    print(
        f"WARN: unknown national broadcaster id={bid} name={api_name!r} "
        f"gamePk={game_pk} — add to CHANNEL_NAME_BY_ID",
        file=sys.stderr,
    )
    return api_name


def fetch_linescore(game_pk):
    """Fetch current home/away runs for a single in-progress game.

    Returns (home_runs, away_runs) or None on any failure. Individual
    game failures should not break the overall update, so we log and
    return None rather than raise.
    """
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/linescore"
    try:
        data = http_get_json(url)
    except Exception as e:
        print(f"WARN: linescore fetch failed for gamePk={game_pk}: {e}", file=sys.stderr)
        return None
    teams = data.get("teams") or {}
    home_runs = (teams.get("home") or {}).get("runs")
    away_runs = (teams.get("away") or {}).get("runs")
    if isinstance(home_runs, int) and isinstance(away_runs, int):
        return home_runs, away_runs
    return None


def fetch_live_inning_state(game_pk):
    """Fetch (currentInning, inningHalf) from the linescore endpoint for
    an in-progress game. Returns a dict or None on failure / missing data.

    Used to populate the `live` block on today's in-progress game so the
    Phase 2 game-day card can implement its end-of-second-inning hide
    trigger. The boxscore endpoint does NOT carry linescore at top level
    (verified 2026-05-03), so we hit the standalone linescore endpoint.
    """
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/linescore"
    try:
        data = http_get_json(url)
    except Exception as e:
        print(f"WARN: live-state fetch failed for gamePk={game_pk}: {e}", file=sys.stderr)
        return None
    inning = data.get("currentInning")
    inning_half = data.get("inningHalf")
    if inning is None or inning_half is None:
        return None
    return {"inning": inning, "inningHalf": inning_half}


def fetch_boxscore(game_pk):
    """Fetch a single game's boxscore. Returns parsed JSON or None on failure."""
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    try:
        return http_get_json(url)
    except Exception as e:
        print(f"WARN: boxscore fetch failed for gamePk={game_pk}: {e}", file=sys.stderr)
        return None


def fetch_pitcher_season_stats(player_id):
    """Fallback for when a probable pitcher is missing from a boxscore's
    players dict. Returns the season pitching stat dict or None.
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
        f"?stats=season&group=pitching&season={SEASON_YEAR}"
    )
    try:
        data = http_get_json(url)
    except Exception as e:
        print(f"WARN: pitcher stats fetch failed for id={player_id}: {e}", file=sys.stderr)
        return None
    for stats_block in data.get("stats", []):
        splits = stats_block.get("splits") or []
        if splits:
            return splits[0].get("stat") or None
    return None


def fetch_pitcher_hand(player_id):
    """Fetch a pitcher's throwing hand from the player-detail endpoint.
    Returns 'L', 'R', 'S', or None. The boxscore's nested `person` object
    does not carry `pitchHand`; the player-detail endpoint does.
    """
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"
    try:
        data = http_get_json(url)
    except Exception as e:
        print(f"WARN: pitcher hand fetch failed for id={player_id}: {e}", file=sys.stderr)
        return None
    people = data.get("people") or []
    if not people:
        return None
    return (people[0].get("pitchHand") or {}).get("code")


def slot_from_batting_order(s):
    """Translate boxscore's `battingOrder` string ('100', '200', ..., '900')
    into integer slot 1-9. In-game substitutes carry suffixes ('101', '102')
    but for starters the slot is always (n // 100). Returns None for empty
    / unparseable inputs."""
    if not s:
        return None
    try:
        return int(s) // 100
    except (ValueError, TypeError):
        return None


def build_probable(pp_summary, box_team_players, fallback_to_people_endpoint=True):
    """Build a probables.us/them entry from the schedule hydrate's
    probablePitcher summary (always present once known: id + fullName)
    and an optional boxscore players dict (carries boxscoreName +
    seasonStats.pitching when available).

    Falls back to /people/{id}/stats for season stats only when the
    boxscore players dict didn't carry the pitcher record (shouldn't
    happen since the probable starter is always on the active roster,
    but guard for it).
    """
    if not pp_summary:
        return None
    pid = pp_summary.get("id")
    out = {
        "id": pid,
        "name": pp_summary.get("fullName"),
    }
    season_stats = None
    boxscore_name = None
    pitch_hand = None
    if box_team_players and pid is not None:
        p_record = box_team_players.get(f"ID{pid}")
        if p_record:
            boxscore_name = (p_record.get("person") or {}).get("boxscoreName")
            season_stats = (p_record.get("seasonStats") or {}).get("pitching") or None
    if boxscore_name:
        out["boxscoreName"] = boxscore_name
    if not season_stats and fallback_to_people_endpoint and box_team_players is not None and pid is not None:
        # Only fall back when we actually opened a boxscore for this game.
        # If we didn't, "no stats" is the intended state for far-future
        # games — don't pile on extra HTTP calls.
        season_stats = fetch_pitcher_season_stats(pid)
    if season_stats:
        out["seasonStats"] = season_stats
    if pid is not None:
        # Handedness lives on /people/{id}, not on the boxscore's nested
        # person object. Fetch it for every probable so far-future-game
        # probables (no boxscore opened) still carry pitchHand.
        pitch_hand = fetch_pitcher_hand(pid)
    if pitch_hand in ("L", "R"):
        out["pitchHand"] = pitch_hand
    return out


def build_lineup_side(box_team):
    """Build a 9-entry lineup list from one side's boxscore team block.

    Each entry: id, name, boxscoreName, slot (1-9), pos (per-game
    position abbreviation, NOT primary), seasonStats (full
    seasonStats.batting object).

    Returns the list (may be shorter than 9 if the boxscore is half-baked
    pre-game). Caller should sanity-check len() == 9 before emitting.
    """
    batting_order = box_team.get("battingOrder") or []
    players = box_team.get("players") or {}
    out = []
    for pid in batting_order:
        rec = players.get(f"ID{pid}")
        if not rec:
            continue
        person = rec.get("person") or {}
        slot = slot_from_batting_order(rec.get("battingOrder"))
        season_batting = (rec.get("seasonStats") or {}).get("batting") or {}
        pos = (rec.get("position") or {}).get("abbreviation")
        out.append({
            "id": person.get("id"),
            "name": person.get("fullName"),
            "boxscoreName": person.get("boxscoreName"),
            "slot": slot,
            "pos": pos,
            "seasonStats": season_batting,
        })
    return out


def load_prior_data():
    """Read the existing data.json (if present) and return a dict mapping
    gamePk -> game_obj from the previous write.

    Used to carry forward settled facts (lineup + rich-shape probables) on
    games that have just gone Final. The boxscore fetch is gated to
    non-final games to bound API calls, so without carry-over, the cron
    cycle that flips a game to Final would also drop its lineup and
    reduce probables to the bare {id, name} schedule shape — making the
    game-day card body lose content the moment the game ends.

    Empty dict on first-ever run or any read/parse error: carry-over is
    a best-effort enhancement, never a failure path.
    """
    try:
        with open("data.json", "r") as f:
            prior = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    out = {}
    for g in prior.get("schedule", []):
        pk = g.get("gamePk")
        if pk is not None:
            out[pk] = g
    return out


def today_in_chicago():
    """Today's date as YYYY-MM-DD anchored to America/Chicago. The almanac's
    'today' is the city's day, not UTC, not the runner's TZ."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    except Exception:
        from datetime import timedelta
        # Fallback: assume CDT (UTC-5). Within the season this is right;
        # off-season days drift by one hour, harmless.
        return (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d")


def fetch_schedule():
    """Fetch the Cubs' full regular-season schedule and return the parsed list."""
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={CUBS_TEAM_ID}&season={SEASON_YEAR}&gameType=R"
        f"&hydrate=team,broadcasts(all),lineups,probablePitcher"
    )
    data = http_get_json(url)
    games = []

    # Anchor "today" to America/Chicago — the almanac's frame of reference.
    today_str = today_in_chicago()

    # Prior write (gamePk-keyed) for the lineup + probables carry-over on
    # games that have just gone Final. See load_prior_data() docstring.
    prior_by_gamepk = load_prior_data()

    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            # Defensive: skip anything that isn't regular season
            if g.get("gameType", "R") != "R":
                continue

            # Skip postponed predecessors. When a game is rained out and
            # rescheduled into a doubleheader, the API returns both the
            # original (detailedState: "Postponed", null scores) and the
            # makeup (detailedState: "Final" with scores), often sharing
            # the same gamePk. The postponed record is a ghost.
            if g.get("status", {}).get("detailedState") == "Postponed":
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

            # Cache gamePk early — used by live-score fallback, by the
            # boxscore enrichment pass below, and as a top-level field.
            game_pk = g.get("gamePk")

            # Result if final or live. "Live" covers In Progress, Warmup,
            # Manager Challenge, Delayed, etc. — anything MLB considers
            # mid-game. Pregame ("Preview") and other states leave result=None.
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
            elif status == "Live":
                # Prefer the schedule's running score; fall back to the
                # per-game linescore endpoint if the schedule omits it.
                home_score = g["teams"]["home"].get("score")
                away_score = g["teams"]["away"].get("score")
                if not (isinstance(home_score, int) and isinstance(away_score, int)):
                    if game_pk is not None:
                        scores = fetch_linescore(game_pk)
                        if scores:
                            home_score, away_score = scores
                if isinstance(home_score, int) and isinstance(away_score, int):
                    if is_home:
                        result = {"us": home_score, "them": away_score}
                    else:
                        result = {"us": away_score, "them": home_score}
                else:
                    print(
                        f"WARN: no live score available for gamePk={game_pk} "
                        f"({opp_abbr} {date_str})",
                        file=sys.stderr,
                    )

            try:
                broadcast = resolve_broadcast(
                    g.get("broadcasts") or [],
                    game_pk=game_pk,
                )
            except Exception as e:
                print(
                    f"WARN: broadcast resolution failed for gamePk="
                    f"{game_pk} ({opp_abbr} {date_str}): {e}",
                    file=sys.stderr,
                )
                broadcast = None

            game_obj = {
                "date": date_str,
                "opp": opp_abbr,
                "home": is_home,
                "time": time_str,
                "result": result,
                "broadcast": broadcast,
                "gamePk": game_pk,
            }

            # ---- Game-day card data (Phase 1) ------------------------------
            #
            # Three new optional blocks that the Phase 2 card UI will read:
            #   - probables   : matchup pitchers + season stats
            #   - lineup      : 9-batter starting order per side
            #   - live        : current inning state (replaces the old
            #                   `live: true` boolean — see index.html shim)
            #
            # The boxscore is the only source for per-game position, slot
            # encoding, and embedded seasonStats. We fetch it conditionally:
            # only for non-final games where lineup is announced or where
            # we have probables + the schedule signals the game is within
            # ~3 days (the `lineups` key being present in the entry).
            # Past finals are skipped to avoid 100+ boxscore fetches per
            # cron cycle later in the season; their lineup data is a
            # separate backfill if ever wanted. See docs/lineup-investigation.md.

            home_pp = g["teams"]["home"].get("probablePitcher")
            away_pp = g["teams"]["away"].get("probablePitcher")
            us_pp = home_pp if is_home else away_pp
            them_pp = away_pp if is_home else home_pp

            lineup_present = bool((g.get("lineups") or {}).get("homePlayers"))
            lineups_key_present = "lineups" in g  # signals game is within ~3 days

            is_final = (status == "Final")
            is_in_progress = (status == "Live")

            should_fetch_boxscore = False
            if not is_final and game_pk is not None:
                if lineup_present:
                    should_fetch_boxscore = True
                elif (us_pp or them_pp) and lineups_key_present:
                    should_fetch_boxscore = True

            box = fetch_boxscore(game_pk) if should_fetch_boxscore else None
            box_teams = (box or {}).get("teams", {}) if box else {}
            home_box = box_teams.get("home") or {}
            away_box = box_teams.get("away") or {}
            us_box = home_box if is_home else away_box
            them_box = away_box if is_home else home_box

            # Probables: emit whenever the schedule has them, with stats
            # only when we opened a boxscore.
            us_probable = build_probable(
                us_pp,
                us_box.get("players") if box else None,
            )
            them_probable = build_probable(
                them_pp,
                them_box.get("players") if box else None,
            )
            if us_probable or them_probable:
                probables = {}
                if us_probable:
                    probables["us"] = us_probable
                if them_probable:
                    probables["them"] = them_probable
                game_obj["probables"] = probables

            # Lineup: only when both sides have a 9-batter order locked in.
            if lineup_present and box:
                us_lineup = build_lineup_side(us_box)
                them_lineup = build_lineup_side(them_box)
                if len(us_lineup) == 9 and len(them_lineup) == 9:
                    game_obj["lineup"] = {"us": us_lineup, "them": them_lineup}

            # Carry-over for finals: settled facts (lineup + rich-shape
            # probables) from the prior cycle persist across the cron run
            # that flips a game to Final, since the boxscore fetch is gated
            # to non-final games. Without this the game-day card body would
            # lose content the moment the last out is recorded.
            if is_final:
                prior = prior_by_gamepk.get(game_pk)
                if prior:
                    if prior.get("lineup") and "lineup" not in game_obj:
                        game_obj["lineup"] = prior["lineup"]
                    prior_probables = prior.get("probables") or {}
                    if prior_probables:
                        game_obj.setdefault("probables", {})
                        for side in ("us", "them"):
                            ps = prior_probables.get(side)
                            if ps and ("boxscoreName" in ps or "seasonStats" in ps):
                                # Preserve freshly-fetched pitchHand through
                                # the carry-over so handedness lands on finals
                                # too, not just on lookahead probables.
                                fresh_hand = (game_obj["probables"].get(side) or {}).get("pitchHand")
                                game_obj["probables"][side] = ps
                                if fresh_hand and "pitchHand" not in ps:
                                    game_obj["probables"][side] = {**ps, "pitchHand": fresh_hand}
                        if not game_obj["probables"]:
                            game_obj.pop("probables", None)

            # Live: only on today's in-progress game. Object shape replaces
            # the old `live: true` boolean. The renderer's truthy check
            # (`!!g.live`) still trips, but anything checking `=== true`
            # would break — see the shim in index.html.
            if is_in_progress and date_str == today_str:
                detailed = g.get("status", {}).get("detailedState", "Live")
                inning_state = (
                    fetch_live_inning_state(game_pk) if game_pk is not None else None
                )
                live_obj = {"status": detailed}
                if inning_state:
                    live_obj["inning"] = inning_state["inning"]
                    live_obj["inningHalf"] = inning_state["inningHalf"]
                game_obj["live"] = live_obj
            elif is_in_progress:
                # Game is "Live" per the API but isn't on today's CT date
                # (rare timezone-edge case). Preserve a truthy live signal
                # so the existing in-schedule live indicator still lights up.
                game_obj["live"] = {"status": g.get("status", {}).get("detailedState", "Live")}

            games.append(game_obj)

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
