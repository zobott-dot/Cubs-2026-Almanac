# Lineup Investigation — Game-Day Card Phase 0

**Probed:** 2026-05-02. **Reference games:** today's Cubs/D-backs (gamePk 824685, Final), tomorrow's rematch (824687, Scheduled), Cubs/White Sox 2026-05-15 (824601, Scheduled, T-13d), and two recent finals (824686, 824688).

## 1. Executive summary

The cleanest primary source for confirmed lineups is **`/api/v1/schedule?...&hydrate=lineups,probablePitcher`** — a tiny (~2KB single-day, ~360KB whole-season) response that includes a 9-player batting-order array per side once the lineup is announced, and probable starters at all stages. The MLB Stats API gives a clean three-state lifecycle signal (`lineups` key absent → too early to ask; `lineups: {}` → game is approaching but lineups not yet posted; `lineups: {homePlayers, awayPlayers}` → announced) with no ambiguous in-between. For the *position each batter plays today* and for batter/pitcher season stats embedded in-line, the **`/api/v1/game/{gamePk}/boxscore`** endpoint is the canonical second source — ~165KB per final game, ~127KB pre-game, ~140ms median latency. The `/api/v1.1/game/{gamePk}/feed/live` endpoint contains a superset of the boxscore plus play-by-play and weather, but at 700KB+ for finals it's overkill for our card. Lineup posting timing is consistent with the working assumption (~2-3 hours before first pitch); for the typical 1:20 PM Wrigley day game, lineups should be live by ~10:30-11:00 AM CT, meaning the cron should start by **9:00 AM Central** to catch them inside one cycle.

## 2. Endpoint findings

### Primary: `GET /api/v1/schedule?sportId=1&teamId=112&date=YYYY-MM-DD&gameType=R&hydrate=lineups,probablePitcher`

**Path to lineup data:** `dates[0].games[0].lineups.homePlayers` and `.awayPlayers`. Each is an array of player records in batting-order sequence:

```json
{
  "id": 683737,
  "fullName": "Michael Busch",
  "link": "/api/v1/people/683737",
  "firstName": "Michael",
  "lastName": "Busch",
  "primaryPosition": {
    "code": "3", "name": "First Base",
    "type": "Infielder", "abbreviation": "1B"
  },
  "useName": "Michael"
}
```

**Probable starter:** `dates[0].games[0].teams.{home,away}.probablePitcher` (id, fullName, link only — see §6 for stats). Tomorrow's game (824687) returns both `Merrill Kelly` and `Matthew Boyd` already, despite no lineups posted yet.

**Caveats:**
- `primaryPosition` is the player's general position, **not the position they're playing today**. A utility infielder DHing today would still show his primary position. For "Ballesteros (DH)" accuracy, supplement with the boxscore (§ "Secondary").
- `lineups.homePlayers` arrives in batting-order sequence (verified against today's `boxscore.battingOrder`), but slot index is implicit — no field carries "this player is the 6th hitter."
- `note` and `stats` sub-hydrates against `probablePitcher` accept the syntax but return no extra data (tested `probablePitcher(note)` and `probablePitcher(stats(group=[pitching],type=[season]))`; both gave the same `{id, fullName, link}` body).

**Response size:**
- Single day, two teams: ~2-7KB.
- Six days, six games: ~7KB.
- Whole season (163 games), all states: 359KB / 274ms.

### Secondary: `GET /api/v1/game/{gamePk}/boxscore`

**Path to lineup data:** `teams.{home,away}.battingOrder` is an array of 9 player IDs (or empty `[]` pre-lineup); each player's full record lives at `teams.{home,away}.players.ID{n}`.

```json
"battingOrder": [683737, 694208, 608324, 664023, 673548,
                 691718, 621020, 807713, 665804]
```

The per-player record carries:

```json
"ID683737": {
  "person": { "id": 683737, "fullName": "Michael Busch", "boxscoreName": "Busch" },
  "jerseyNumber": "29",
  "position": { "code": "3", "name": "First Base",
                "type": "Infielder", "abbreviation": "1B" },
  "status": { "code": "A", "description": "Active" },
  "battingOrder": "100",
  "stats": { "batting": {...}, "pitching": {}, "fielding": {} },
  "seasonStats": { "batting": {...}, "pitching": {...}, "fielding": {...} },
  "gameStatus": { "isCurrentBatter": false, "isCurrentPitcher": false,
                  "isOnBench": false, "isSubstitute": false }
}
```

`battingOrder` is encoded as a string of `slot * 100` for starters (`"100"`, `"200"`, …, `"900"`) and `slot * 100 + N` for substitutes (`"101"` for the first sub at the leadoff slot, `"102"` for the second, etc.). Verified against yesterday's game (824686), which had Hoerner at slot 100 and Shaw — pinch-hit substitute — at slot 101, with `gameStatus.isSubstitute: true` on Shaw.

**Why this is the secondary, not the primary:**
- Carries the same lineup data as the schedule hydrate, but at ~50× the byte cost.
- Pre-game payload (~127KB) is nearly all roster boilerplate and zero-stat splits, with empty `battingOrder`/`batters`/`pitchers` arrays.
- However, it's the only source for **per-game position** (the position the player is actually fielding today, e.g. Ballesteros at DH) and for **embedded season stats** (every player on the active roster carries `seasonStats.batting` and `seasonStats.pitching` whether or not they're starting).

**Response size:** 127-170KB depending on game state (final games ~165KB, pre-game/scheduled ~127KB). Median latency 143ms across 5 sequential fetches, range 131-153ms.

### Considered and dropped: `/api/v1.1/game/{gamePk}/feed/live`

Returns 707KB for a final game, 180KB for a scheduled one. Contains everything the boxscore has (`liveData.boxscore`) plus `gameData.probablePitchers`, `gameData.weather`, `gameData.gameInfo`, `gameData.players`, `liveData.plays`, and play-by-play. The boxscore subtree is identical to what `/boxscore` returns directly. **Not worth the bytes** unless we want play-by-play or weather, neither of which is part of the card scope.

## 3. Timing model

**Posted lineups in this probe (whole-season hydrate, 2026-05-02):** 33 of the 30 played games + 0 of the next 130 carried populated `lineups.homePlayers`. (The 33 includes today's game and 32 prior finals.) No mid-window or "almost-posted" state was visible in the snapshot — every future game returned either an empty `lineups: {}` (next ~3 days) or no `lineups` key at all (further out).

**Working assumption:** lineups post 2-3 hours before first pitch. The probe couldn't directly catch a "just posted" moment, but tomorrow's game (824687, first pitch 1:20 PM CT 2026-05-03) had `lineups: {}` at probe time (mid-day 2026-05-02), ~24 hours before first pitch — consistent with the assumption.

**Day-game cron implication for §7:** Wrigley day games typically start at 1:20 PM CT. With a 2.5-hour lineup-post window, lineups are confirmed by ~10:50 AM CT in the typical case, with outliers as early as ~10:00 AM (early scratches forcing an early post) and as late as ~11:30 AM. **Recommend: shift the cron's start to 9:00 AM Central**, with the 15-minute cadence the workflow already runs. That gives 4-5 cycles between cron-start and the typical lineup-post window, and ensures the card is live by the time anyone is checking the page in the lunch hour.

The current cron (12pm-midnight Central) misses early lineups by 1-3 hours. Even night games at 7:05 PM (lineup ~4:30 PM) are caught only because that's well into the 12pm-midnight window. The 9:00 AM start handles both day and night games with the same shape.

`gameInfo.firstPitch` and `datetime.dateTime` from the live feed give per-game canonical first-pitch time in UTC, which can be converted to CT for the cron-precision case if we ever want to be smarter than a fixed start.

There is **no `lastUpdated` timestamp** on the lineup data itself. The schedule hydrate response carries no metadata that would let us tell *when* a lineup was set, only *that* it has been. If we want to render "Lineup posted 11:42 AM" copy on the card, we'll need to record the first-seen timestamp in our own pipeline, not pull it from the API.

## 4. Lifecycle states

There are three distinguishable states for a game's lineup field via the schedule hydrate, plus the post-game state:

| State | `lineups` key | `lineups.homePlayers` | When |
| --- | --- | --- | --- |
| Far future | absent (key not present in JSON) | n/a | Game is more than ~3 days out |
| Approaching | present, value is `{}` | n/a | Game is within ~3 days but lineup not yet posted |
| Announced | present, value has both arrays | array of 9 records | ~2-3 hours before first pitch through end of game |
| Final | same as announced | array of 9 (the *starters* — substitutes are NOT folded in here) | After the game ends |

**The signal:**

```python
lineup_present = bool(g.get("lineups", {}).get("homePlayers"))
```

This collapses all three "not yet" states into `False`, which is what the card-visibility logic wants. No ambiguity, no string-parsing, no status-code-checking. If a future API change breaks this collapse (e.g. by setting `homePlayers: null` instead of omitting it), the falsy check still does the right thing.

**Edge note on the "approaching" state:** Within ~3 days of a game, `lineups: {}` shows up before any data is actually there. This is harmless for our gating logic, but it's worth knowing — it implies the API is staging the lineup field server-side before the team posts.

## 5. Scratches and corrections

The MLB Stats API tracks **current truth only.** There is no `originalLineup` field, no version history, no audit trail of "X was announced and then scratched." If a team posts a lineup at 10:45 AM and replaces a player at 11:30 AM, the schedule hydrate at 11:31 AM returns the corrected lineup as if it had always been that way.

The boxscore's `battingOrder` slot encoding (`"100"`, `"101"`, `"102"`) only describes *in-game* substitutions — pinch hits, double switches, defensive replacements. A pre-game scratch is invisible to that encoding because the scratched player simply doesn't appear in the boxscore at all.

This shapes the card's correctness story:
- Our pipeline writes `data.json` every 15 minutes during the cron window. If a scratch happens between two runs, the card displays the stale lineup for up to 15 minutes. That's the operating tolerance; nothing in the API can shorten it.
- We could track our own first-seen-vs-now diff to surface "Suzuki was scratched, replaced by ___" copy, but it would require persisting prior `data.json` snapshots and diffing on each run. **Not recommended** for v1 — the editorial bar isn't worth the engineering, and a single scratch correction propagating quietly through the next cron is fine.

**Helpful flags that exist:**
- `players.ID{n}.gameStatus.isSubstitute` — boolean, true for in-game subs.
- `players.ID{n}.status.code` / `.description` — `"A"`/"Active" for everyone in the boxscore. Active-roster moves (IL, optioned to AAA) take effect via the player vanishing from the roster, not via a status flag on a boxscore record.

**Helpful flags that don't exist:**
- No `isStartingPitcher` or `isStarter` flag on player records. The starter is identified post-hoc by being the first entry in `pitchers[]` or by having `gamesStarted > 0` in their season stats; pre-game it's only available via `probablePitcher` on the schedule.
- No `originalLineup` vs `currentLineup`. The lineup is mutated in place.

## 6. Adjacent data inventory

What's available alongside the lineup, presented as a menu (not a recommendation):

**Probable pitcher's season stats** (every batter and pitcher in the boxscore players dict carries this, including all 26 active-roster pitchers pre-game). Live example for Imanaga:

```json
"seasonStats.pitching": {
  "era": "2.40", "whip": "0.85",
  "wins": 3, "losses": 2,
  "inningsPitched": "41.1", "strikeOuts": 43,
  "baseOnBalls": 10, "homeRuns": 3,
  "gamesStarted": 7, "strikeoutsPer9Inn": "9.36",
  "walksPer9Inn": "2.18", "hitsPer9Inn": "5.44"
  // ~40 more fields
}
```

This is **embedded in the boxscore for free** as long as the player is on the active roster (which the probable starter always is by definition). No separate `/people/{id}/stats` call needed. If for some reason we wanted a player off the boxscore players dict, that endpoint exists at `/api/v1/people/{id}/stats?stats=season&group=pitching&season=2026` (1.7KB, 115ms).

**Per-batter season stats** (same shape, batting-side fields like avg/obp/ops/HR/RBI), embedded the same way.

**Pitcher and batter handedness:** `gameData.players.ID{n}.batSide.code` and `.pitchHand.code` (`"L"`, `"R"`, `"S"`). Available from the live feed, **not** from the boxscore directly. Useful for "LHP" badge or platoon implications. Could be backfilled from a separate `/people/{id}` call if we want to avoid the live feed.

**Weather:** `gameData.weather` — `condition` ("Partly Cloudy"), `temp` ("50"), `wind` ("5 mph, In From CF"). Live-feed only.

**First pitch / game duration / attendance:** `gameData.gameInfo.firstPitch`, `.gameDurationMinutes`, `.attendance`. Live-feed only. (Schedule API gives `gameDate`/`officialDate`, which is enough for first pitch; duration and attendance are post-game.)

**Venue:** `gameData.venue.name` ("Wrigley Field") — live feed; or `dates[].games[].venue.name` from the schedule API.

**Top performers:** `liveData.boxscore.topPerformers` — pre-computed list of standout players with summary lines like `"7.0 IP, 0 ER, 5 K, BB"` and a `"(W, 3-2)"` decision tag. Post-game only.

**Game flags:** `gameData.flags` — `noHitter`, `perfectGame`, `homeTeamNoHitter`, etc. Boolean snapshot of historic-watch state.

**ABS challenges:** `gameData.absChallenges` (Automated Ball/Strike) — `usedSuccessful`, `usedFailed`, `remaining` per side. New for 2026 and visible per game.

**IL / roster status:** Available from `/api/v1/teams/112/roster?rosterType=fullRoster&season=2026` — 254 names with statuses including `Active`, `Injured 7-Day`, `Injured 15-Day`, `Injured 60-Day`, `Injured - Full Season`, `Restricted List`, `Designated for Assignment`, `Reassigned to Minors`, `Development List`. The boxscore's per-player `status` only shows the active state for players who appear in the boxscore (pre-game: 26 active per side; post-game: 26 active + however many appeared); IL'd players don't show up there. If the card wants "Steele on the 60-day IL" copy, it needs the roster endpoint as a separate call.

**Bench and bullpen:** `teams.{home,away}.bench` and `.bullpen` — arrays of player IDs. Pre-game these are filled with the entire active roster spread across the two arrays (13/13 split observed). Post-game they're populated with players who were available but didn't appear. Not editorially interesting pre-game.

**Pitching notes:** `boxscore.pitchingNotes` — array of strings like `"Imanaga pitched to 1 batter in the 8th"`. Post-game only.

**`info` array (post-game):** Game-summary lines — `WP`, `IBB`, `Pitches-strikes` (`"Imanaga 87-56"`), `Groundouts-flyouts`, `Batters faced`, `ABS Challenge` log per batter. Useful for a post-game expansion of the card if we ever want one.

**`note` array per team (post-game):** Pinch-hit lineage — `"a: Grounded out for Hoerner in the 2nd."` Linked to substitute slot encoding via `gameStatus.isSubstitute`.

## 7. Performance notes

| Endpoint | Bytes | Median latency (5 runs) |
| --- | --- | --- |
| `schedule?date=YYYY-MM-DD&hydrate=lineups,probablePitcher` (single day, both teams) | ~2-7KB | 104ms (range 98-124) |
| `schedule?season=2026&hydrate=lineups,probablePitcher` (full season, all 163 games) | 359KB | 274ms |
| `game/{gamePk}/boxscore` | 127-170KB | 143ms (range 131-153) |
| `game/{gamePk}/feed/live` (Final) | 707KB | 237ms |
| `game/{gamePk}/feed/live` (Scheduled) | 180KB | 161ms |
| `people/{id}/stats?stats=season&group=pitching` | 1.7KB | 115ms |

**Marginal cron cost** if we add a single-day lineups hydrate + a single boxscore call per cron run:
- ~104ms + ~143ms ≈ **250ms per cycle**, ~2-7KB + ~165KB ≈ **170KB transferred**.
- That's well inside the latency budget of an Action that already does a season-wide schedule call (~270ms) and a NL Central standings call.
- For doubleheaders (rare but real — 2 games same day), double the boxscore cost. Still negligible.

**Rate limits:** No documented hard limit on `statsapi.mlb.com`. The endpoints we hit returned consistently in 100-300ms range with no throttling, no `Retry-After` headers, no 429s. The Phase 1 broadcast investigation (per repo history) ran higher-volume probes against the same domain without trouble. Conservative posture: stay below ~10 req/sec sustained, which we're nowhere close to.

## 8. Recommended `data.json` schema additions

Folded into the existing schedule entries, not as a new top-level block (keeps the contract that `schedule[i]` is the unit of game-day truth). Add fields only on games where data is meaningful — null/absent for games without it.

```json
{
  "updatedAt": "2026-05-02T18:57:00Z",
  "schedule": [
    {
      "date": "2026-05-03",
      "opp": "AZ",
      "home": true,
      "time": "1:20 PM",
      "result": null,
      "broadcast": "MARQUEE",
      "gamePk": 824687,
      "probables": {
        "us":   { "id": 571510, "name": "Matthew Boyd",
                  "era": "3.42", "wl": "5-2", "ip": "47.1",
                  "k": 52, "whip": "1.18" },
        "them": { "id": 518876, "name": "Merrill Kelly",
                  "era": "4.10", "wl": "3-3", "ip": "52.0",
                  "k": 48, "whip": "1.25" }
      },
      "lineup": {
        "us": [
          { "id": 683737, "name": "Michael Busch",
            "boxscoreName": "Busch", "pos": "1B", "slot": 1,
            "avg": ".287", "hr": 8, "rbi": 22, "ops": ".812" }
          // ... slots 2-9
        ],
        "them": [ /* same shape */ ]
      }
    }
  ],
  "standings": [ /* unchanged */ ]
}
```

**Notes on the proposal:**

- `gamePk` is added as a top-level field because it's the join key for any per-game endpoint and the existing schema doesn't carry it. Probably worth adding regardless of whether we ship the card.
- `probables` always present once the schedule hydrate has it (~2-3 days out at the latest, usually further). Stats fold in from each pitcher's `seasonStats.pitching` in the boxscore (or from `/people/{id}/stats` if not yet on the boxscore players dict).
- `lineup` is absent until the lineup is announced. Card visibility = `lineup` truthy.
- `slot` is 1-9 (not the API's `100`/`200` encoding) for cleanliness.
- `pos` is the per-game position from `boxscore.players.ID{n}.position.abbreviation`, not the player's primary position. This means `update_data.py` needs to fetch the boxscore (not just the schedule hydrate) once a lineup is detected.
- `us`/`them` orientation matches the existing `result.us`/`result.them` convention. No need to track home/away orientation inside `lineup`.

**Pipeline shape inside `update_data.py`:** for each game in today's schedule (anchored to America/Chicago), check `lineup_present` from the schedule hydrate. If true, add the boxscore as a second fetch and unpack starting nine + per-game position + season stats for both sides. Skip both extra calls otherwise.

## 9. Open questions

These should be resolved in the design conversation before any build:

1. **Card visibility window:** the prompt says "appears as soon as lineup is announced, disappears at first pitch." But the lineup data is *more* useful in the pre-game window than during the game (we have an in-progress hero band already). Confirm the disappearance trigger — is it `gameStatus == 'Live'` (status flips to live), or first-pitch UTC timestamp passing, or both?

2. **DH-position display:** should the slot show the per-game position (Ballesteros today plays DH, even though he might primary as C) or the primary position? Per-game is more accurate but requires the boxscore call — primary is free with the schedule hydrate alone. Cost difference: ~165KB and ~140ms per game-day cron run.

3. **Probable starter stat shape:** the proposal includes ERA / W-L / IP / K / WHIP. Editorial: which five (or three, or seven) actually go on the card? This affects whether we slim `probables` in `data.json` or carry the whole `seasonStats.pitching` shape and let the renderer pick.

4. **Per-batter stat display:** included AVG / HR / RBI / OPS in the proposal. Same question — what's actually surfaced visually? Likely fewer than four numbers on a phone-width card.

5. **Scratch tolerance:** OK with up to 15 minutes of stale lineup display after a scratch? (Confirmed above as the de-facto worst case given cron cadence.)

6. **Cron start-time change:** §7 recommends 9:00 AM Central. Confirm before editing the workflow YAML.

7. **Doubleheaders:** when there are two games on one date, both will satisfy the "today" check. The card needs to either pick one (probably the one whose first-pitch UTC has not yet passed, with a fallback to the second game once the first is final) or render both. Defer until we hit one in the schedule.

8. **Initial-render ordering:** the lineup is only meaningful after the page knows which game is "today." If the schedule's lineup field is filled but the game starts at 7:05 PM and someone is loading the page at 8:00 AM, the card renders with a 11-hour-old "lineup announced X ago" feel. Probably fine, but worth a sentence in the design about copy tone in that window.

9. **Posted-time copy:** there's no API field for "lineup posted at 10:42 AM." If the card wants to show that, the pipeline would need to record first-seen-with-lineup timestamps in `data.json` itself. Decide whether that's worth the schema bloat.

10. **Card on rainout / postponed:** existing pipeline skips postponed predecessors (per `update_data.py` comment). Confirm card hides cleanly when today's game is postponed but the makeup is rescheduled into a doubleheader on a later day.

---

*Probed using only `urllib` + ad-hoc Python in `/tmp/cubs-probe/`. No production files modified other than this report. JSON dumps and reproducer snippets are local-only and will be discarded with the next reboot.*
