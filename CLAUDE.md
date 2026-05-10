# Cubs 2026 Almanac

A self-updating Chicago Cubs 2026 season tracker built for family and friends. Deployed at https://zobott-dot.github.io/Cubs-2026-Almanac/.

## Architecture

Three files do all the work:

- **index.html** — Single static page with an embedded fallback schedule baked in so the page is never blank before data.json loads.
- **update_data.py** — Python stdlib-only script that calls the MLB Stats API, assembles the current schedule and standings, and writes `data.json` to the repo root.
- **.github/workflows/update.yml** — GitHub Action that runs `update_data.py` every 3 hours and commits the result.

### Why it works this way

Earlier attempts called the MLB Stats API directly from the browser. CORS blocks those requests. The committed-JSON proxy pattern solves it: the Action fetches the data server-side, commits `data.json`, and the static page reads it from the same origin. Zero cost, no backend.

## data.json schema

```
{
  "updatedAt": "2026-05-04T18:00:00+00:00",
  "schedule": [
    {
      "date": "2026-05-04",
      "opp": "MIL",
      "home": true,
      "time": "1:20 PM",
      "result": null,
      "broadcast": "MARQUEE",
      "gamePk": 824459,
      "probables": {
        "us":   { "id": 668678, "name": "Justin Steele",  "boxscoreName": "Steele",    "seasonStats": { "wins": 3, "losses": 1, "era": "2.45", "inningsPitched": "44.0" } },
        "them": { "id": 605400, "name": "Freddy Peralta", "boxscoreName": "Peralta, F", "seasonStats": { "wins": 4, "losses": 2, "era": "3.12", "inningsPitched": "52.0" } }
      },
      "lineup": {
        "us":   [ { "slot": 1, "id": 663457, "name": "Ian Happ", "boxscoreName": "Happ", "pos": "LF", "seasonStats": { "avg": ".278", "homeRuns": 6, "rbi": 22, "ops": ".812" } } ],
        "them": []
      },
      "live": { "inning": 3, "inningHalf": "Top", "status": "In Progress" }
    }
  ],
  "standings": [
    { "team": "Cincinnati Reds", "abbr": "CIN", "w": 12, "l": 8 }
  ]
}
```

Field notes:

- `result` is `null` for unplayed games, or `{ "us": <int>, "them": <int> }` for finals and live in-progress games.
- `home: true` means at Wrigley.
- `broadcast` is the API-derived display string for the channel ("MARQUEE", "FOX", "Apple TV+", "NBC/Peacock", "ABC/ESPN", "TBS"), or `null` if the API has no recognized broadcast for the game.
- `gamePk` is the MLB Stats API's primary key (integer); always populated. Used to fetch boxscore and linescore.
- `probables` is populated for ~38 games in any snapshot (today through ~3 days out, plus completed games). `us`/`them` each carry `id`, `name`, `boxscoreName`, and `seasonStats` (wins, losses, era, inningsPitched, plus the full pitching stats dict stored verbatim at the top level — *not* nested under a `pitching` sub-key). For probables MLB has named but who haven't pitched yet this season, `seasonStats` is present but populated with zeros and dash placeholders (`era: "-.--"`, `wins: 0`). Completed games retain the rich shape (`boxscoreName`, `seasonStats`) when the prior cycle captured it: the boxscore re-fetch is gated to non-final games, but `update_data.py` carries forward the previous write's rich-shape probables on finals so the game-day body keeps content past end-of-game (see May 2026 redesign notes below). For finals where no prior cycle captured the rich shape (first runs, backfills), only the bare `{id, name}` shape lands. `null` for games where MLB hasn't named a probable yet (typically more than ~3 days out).
- `lineup` is populated for non-final games when `lineup_present` is true on the API hydrate (typically today's game pre-first-pitch through end-of-game), and on finals via carry-over from the prior cycle's write. The boxscore is not refetched for finals, so a final whose lineup wasn't captured before the game ended (first runs, backfills) carries no `lineup` key. Each player object has `slot`, `id`, `name`, `boxscoreName`, `pos` (per-game position from boxscore, not primary), and `seasonStats` (avg, homeRuns, rbi, ops, plus the full batting stats dict stored verbatim at the top level — *not* nested under a `batting` sub-key).
- `live` has two coexisting shapes (transition state, both work via `!!g.live`):
  - Rich object form (today's in-progress game): `{ "inning": <int>, "inningHalf": "Top"|"Bottom", "status": <detailedState string> }`
  - Simpler form (rare timezone-edge case where API status says "Live" but game isn't on today's CT date): `{ "status": <detailedState string> }`
  - Legacy `live: true` boolean has been retired by the schema change but the index.html shim handles both via truthy check; cleanup safe to do later.
- `standings` covers the five NL Central clubs, sorted wins-desc / losses-asc (first-place team first).

## Game-day card system (designed May 3, 2026; Phase 1 deployed May 3, 2026; Phase 2 superseded by May 2026 redesign)

A new feature: a card that appears below the hero band on game days during the pre-game window, showing the pitcher matchup and starting lineups for both teams. Built in two phases by deliberate decision — Phase 1 (data pipeline) ships first, Phase 2 (card UI) follows after several days of real-world data accumulation so the visual design is built against observed behavior rather than predicted behavior.

### Phase 0: lineup data investigation (complete)

Investigation report at `docs/lineup-investigation.md`. Establishes endpoint findings, schema proposal, lifecycle states, and adjacent data inventory. Reference this report for any data-shape question rather than re-investigating. Two corrections to the report were surfaced during Phase 1 build (see Phase 1 outcomes below).

### Phase 1: data pipeline (deployed May 3, 2026; verified by data audit May 4, 2026)

Two commits on `main`: `ebcdc78` (cron schedule shift to 9 AM Central) and `5182f35` (schema additions and pipeline changes in `update_data.py` plus a one-line `index.html` shim for the `live` field shape change).

**Verification (May 4, 2026):** Live `data.json` audited against the spec. All new fields landing correctly: `gamePk` populated 162/162, `probables` populated for today + next 3 days with full season stats, `lineup` populated for today's pre-game window with both teams. The `us`/`them` naming convention matched the existing codebase pattern (consistent with the `result: { us, them }` shape that's been there since v1) — this differed from the investigation report's predicted `home`/`away` keys but is the correct call. Yesterday's final game (May 3, AZ) showed the boxscore-gating decision working as designed: kept `gamePk` and simple-shape `probables` ({id, name} only), no `lineup` re-fetch. Phase 1 considered fully verified.

**What landed:**
- Cron start moved from 12 PM to 9 AM Central
- Schedule hydrate extended from `team,broadcasts(all)` to `team,broadcasts(all),lineups,probablePitcher`
- `gamePk` extracted to top-level field on every schedule entry (162/162 populated)
- `probables` extracted from schedule hydrate, stats embedded from boxscore players dict (~38 games carry probables in any given snapshot — today through ~3 days out, plus completed games)
- `lineup` extracted from boxscore once `lineup_present` is true on the schedule hydrate (typically only today's game pre-first-pitch through end of game)
- `live` object replaces the legacy `live: true` boolean for in-progress games on today's date; carries `inning`, `inningHalf`, `status`
- Index.html shim: `g.live === true` → `!!g.live` so the existing live-indicator logic trips on both old boolean and new object shapes during the transition window

**Architectural decisions made during build, worth knowing for Phase 2:**

- **Boxscore fetch is gated to non-final games only.** The investigation report's spec, read literally, would have us fetch the boxscore for every game where `lineup_present` is true — including completed games, which is wasteful since their lineups are settled facts that don't change. The fetch is gated to non-final games, meaning past finals don't get the `lineup` field populated through the cron. If Phase 2 ever wants historical lineups for a season-ledger feature, that's a one-time backfill, not a per-cron concern.

- **Standalone `/api/v1/game/{gamePk}/linescore` endpoint is used for live inning state**, not `boxscore.linescore`. The investigation report claimed `linescore` was a sub-key of the boxscore response; it isn't. The standalone endpoint exists, returns `{currentInning, currentInningOrdinal, inningState, inningHalf, isTopInning, ...}`, and is the cleaner contract anyway since `fetch_linescore()` already exists in the file for live-score capture. Investigation report §3 would benefit from a one-line correction.

- **The `live` field shape change required the index.html shim.** The Phase 1 prompt's "no UI changes" guideline was almost achievable but not quite — the strict-equality check in `index.html` (`g.live === true`) had to become a truthy check (`!!g.live`) to handle both the legacy boolean form and the new object form. One-line change.

- **`live` field has two coexisting shapes by design.** Today's in-progress game gets the rich object form (`{inning, inningHalf, status}`); the rare timezone-edge case where a game's API status says "Live" but it isn't on today's CT date falls back to a simpler `{status}` object. Both are truthy under `!!g.live`. Future cleanup may unify them; not urgent.

- **`status` field in the `live` object carries the API's `detailedState`** (typical values: `"Live"`, `"In Progress"`, `"Pre-Game"`, `"Final"`), not `abstractGameState` (which would be `"Live"`, `"Final"`, `"Preview"`). The Phase 1 prompt's example showed `"status": "Live"` but the schema's field-level note pointed at `detailedState`; the implementation followed the note, which is the source of truth. If Phase 2 wants the abstract state instead, it's a one-line change.

### Phase 2: card UI (pending — pause is short but acceptable)

The intentional pause between phases lets real-world data accumulate (day games, night games, doubleheaders, occasional scratches) so the visual design is built against observed behavior rather than predicted behavior. The April 5 doubleheader (CLE, gamePks 824459 and 824460) is already in the rear-view but a useful test case to inspect when designing for the doubleheader-handling problem.

### Design decisions (settled, May 3, 2026)

**Lifecycle.** Card appears below the hero band when `lineup` becomes truthy in today's schedule entry. Card disappears when first run is scored OR end of second inning is reached, whichever comes first. Card hides for postponements, rainouts, and any state where the data is ambiguous. Card never coexists with the in-progress hero band beyond the first-run/end-of-2nd cutoff — the hero band carries the in-game job.

**Defaults collapsed, expandable.** During the visibility window the card renders collapsed by default, showing only its small header label and a one-line matchup summary — the two pitchers' last names joined by "vs" ("Cabrera vs Petty"). The visitor expands it via a chevron control matching the existing section disclosure pattern to reveal the pitcher matchup and stacked lineups. Collapse state persists for the rest of the visibility window via a single boolean (one card at a time — Set is overkill) and resets to collapsed when the underlying game changes (different gamePk). This matches the almanac conceit the rest of the page already follows — quiet on arrival, visitor chooses what to see. The card stays structurally distinct from the six main sections via its hero-band-class chrome (thin red rules above and below, no roman numeral, no big section title) rather than by its default state.

**Pitcher matchup (top of card).** Two pitchers, each rendered as name + W-L · ERA · IP on a single line. Three numbers chosen for editorial restraint — WHIP and K push the card toward fantasy-baseball density that fights the almanac voice. Full `seasonStats` pitching shape (flat at top level, not nested under `pitching`) is stored in `data.json` for future flexibility; only the three numbers render.

**Lineups (stacked sections).** Cubs lineup first, opponent lineup second, with a typographic divider between. Each row is a single line: slot number, name (`boxscoreName` from API), per-game position, AVG, HR, RBI — natural inline spacing, no forced columns or right-aligned stat blocks. Long names (Crow-Armstrong, Ballesteros) push stats further right; short names (Happ, Hoerner) pull them left. Reads as prose rather than spreadsheet, which fits the editorial voice.

**Per-game position vs primary position.** The card shows per-game position (Ballesteros at DH today even if he primaries as C), which means the pipeline must fetch the boxscore in addition to the schedule hydrate when `lineup_present` is true. Editorial accuracy was judged worth the cost; primary-position-only would ship cards that read wrong to anyone who knows the team.

**Score-line problem from the May 2 hero-band screenshot ("Cubs 1, Diamondbacks 0" wrapping awkwardly):** subsumed into the card design rather than fixed standalone. The post-game hero band state ("Cubs 2, Diamondbacks 0 · FINAL") is the canonical post-game treatment; the card has already disappeared by then. No score-line typography fix needed at the hero band.

### Open questions resolved during the design conversation

The investigation report's §9 listed 10 open questions. All resolved:

1. **Card visibility window** — first run scored OR end of second inning, whichever first. Not the originally-proposed "first pitch" trigger; the card stays useful through early innings.
2. **Per-game position vs primary position** — per-game (requires boxscore call).
3. **Pitcher stats on card** — W-L, ERA, IP only (full shape stored).
4. **Batter stats on card** — AVG, HR, RBI only (full shape stored).
5. **Scratch tolerance** — 15 minutes accepted; matches existing pipeline staleness model.
6. **Cron start-time change** — confirmed 9:00 AM Central. Deployed.
7. **Doubleheaders** — defensive default for v1: card renders for the first game whose first-pitch UTC has not passed, switches to second game's data when first game has hidden, hides if second game's lineup not yet available. Revisit when reality forces it.
8. **Initial-render ordering** — no copy adjustment for "lineup announced X ago"; masthead's existing UPDATED line is sufficient ambient freshness signaling.
9. **Posted-time copy** — dropped. No "Lineup posted at 10:42 AM" feature; would have required new schema (first-seen timestamps) for editorial value that wasn't load-bearing.
10. **Card on rainout/postponed** — defensive default: existing pipeline filters postponed games, so card hides automatically. Card hides cleanly for any ambiguous data state.

### May 2026 redesign — fold card into hero band, five-state hero, no mid-game data dependency

Phase 2's standalone card and the in-progress hero band score line both depended on the cron being current mid-game. When the cron lagged (rain delays, Action failures), both failed visibly: the hero band would show a stale running score, and the card would persist or vanish at unexpected moments because its visibility predicate was checking inning state. The redesign collapses this into a quieter, more honest design that reads as deliberate when the data is stale.

**Hero band — five states.** Today's pulse anchors to America/Chicago and renders one of:
- Pre-game: `Today · vs CIN · 6:40 PM CT · MARQUEE`
- In-progress: `Today · vs CIN · in progress · MARQUEE` — status only; no inning, no score, no live-data read.
- Final-pending: `Today · vs CIN · final pending · MARQUEE / WSCR 670` — italic "final pending"; channel preserved. Fires when the data says live but is meaningfully stale and the game is well past its likely end. See the May 10 staleness escape hatch contract below.
- Final: `Today · vs CIN · Cubs 4, Reds 2 · final` — matchup added before the score line; channel hidden (game is over).
- No game today / season complete — existing fallbacks unchanged.

The in-progress branch deliberately reads no `result` and no `live.inning` into the secondary line. The `live` truthy check is still consulted to classify state (still needs the producer's `live` object to flip from pre-game to in-progress), but no inning-level data flows into the rendered line. The live-score capture in `update_data.py` is left in place — the redesign changes the consumer, not the producer's emit.

**Card folds into the hero band.** The standalone `<div id="game-day-card">` is gone. The hero band itself is the disclosure surface: when today's lineup is posted, the band gains a `.has-body` class, a chevron in its top-right, and a click/keyboard handler. Tapping expands `.hero-band-body` directly below the head, containing the same pitcher matchup + Cubs lineup + opponent lineup blocks as Phase 2. CSS class names for body content (`.gdc-pitchers`, `.gdc-lineup-row`, etc.) are preserved; only the card-level chrome (`#game-day-card`, `.gdc-header`, `.gdc-summary`, `.gdc-chevron`, `.gdc-label`, `.gdc-body`) was removed.

**Visibility predicate simplifies.** `gameDayCardShouldShow(g)` is now: `g.lineup` truthy AND `g.lineup.us` non-empty array. The Phase 2 cutoff conditions (first run scored, `live.inning >= 3`, `isFinal`) are gone. The body persists across pre-game, in-progress, and final — settled facts (who pitched, who was in the lineup) stay accessible all day.

**Producer change required for "stays available after final".** Phase 1's boxscore-fetch gate (`not is_final`) means the cron drops the `lineup` field — and reduces `probables` to bare `{id, name}` — the moment a game flips to Final. Without producer changes the body would lose content immediately at end-of-game, contradicting the redesign's intent. `update_data.py` now carries forward `lineup` and rich-shape `probables` (entries with `boxscoreName` or `seasonStats`) from the prior `data.json` write whenever the new cycle's game is Final and we didn't refetch the boxscore. See `load_prior_data()` and the `if is_final:` block following the lineup write. The carry-over is best-effort: first-ever runs and parse errors degrade gracefully (no carry-over, no crash). It also means the body is only available on a final IF a prior cycle captured the lineup while the game was non-final — for a pristine cron history this is the steady state; for a backfill or a finals-only first run, the chevron is correctly absent.

**Doubleheader handling.** `pickGameDayCardGame()` is retained as the body's game picker — walks today's games in first-pitch order, returns the first one for which the predicate is true. Hero head still uses `pickTodayGame()` (state-priority: pregame > inprogress > final-pending > final, where final-pending and final each pick the latest game by first-pitch). On a single-game day they pick the same game; on a doubleheader they may diverge (head announces the next-to-play game while the body still shows the just-finished game's settled facts). Accepted defensive default for v1.

**Persisted state.** `gameDayCardCollapsed` and `lastGameDayCardGamePk` survive across renderHero re-renders (refresh button, autorefresh) but reset on full page load. Same closure-scoped pattern as `openMonths` / `openChannels` in Section V. Collapse resets when the body's gamePk changes (new day, new game).

**ARIA.** When `.has-body` is present, the head carries `role="button"`, `tabindex="0"`, `aria-controls="hero-band-body"`, and `aria-expanded` toggled in lockstep with the `.collapsed` class. When the band has no body to disclose, those attributes are omitted entirely so the head is a plain status line.

**Staleness escape hatch (deployed May 10, 2026).** The four-state design read no mid-game data into the in-progress branch — that part still holds; the hero band does not display inning or score during in-progress. But that didn't address a separate failure mode: the band staying on "in progress" for 60-120 minutes after a game has actually ended, because GitHub Actions cron drops cluster around end-of-game and the MLB Stats API typically takes 15-30 minutes after the last out to flip `abstractGameState` from "Live" to "Final." Until either of those resolves, `data.json` carries `live: {...}` truthy and the consumer faithfully renders "in progress" — including hard-refreshes, since the file itself is what's stale. The fix adds `final-pending` as a fifth state. When `g.live` is truthy AND the data is at least 30 minutes old (`dataAgeMin >= 30`) AND the game is more than 3.5 hours past first pitch (`gameAgeMin > 210`), the classifier returns `'final-pending'` instead of `'inprogress'`. The render output is `TODAY · vs CIN · final pending · MARQUEE / WSCR 670` with `final pending` in italic. Channel is preserved (the game has been on the air all afternoon; hiding it would suggest the game is over, which is exactly the ambiguity this state expresses). Score is NOT manufactured. The dual-threshold check ensures a fresh cron always trumps the staleness escape hatch — on a normal cron-catches-Final cycle, `dataAgeMin < 30` and the state never fires. The escape hatch is strictly a known-failure-mode backstop on top of the no-mid-game-data principle, not a replacement for it.

**Staleness check touchpoints.** The escape hatch lives entirely in `index.html` and consists of: (a) a module-scoped `let dataUpdatedAt = null;` populated from `data.updatedAt` in the fetch handler; (b) a `firstPitchMs(g)` helper that constructs a UTC ms timestamp from `g.date` (YYYY-MM-DD) and `g.time` ("1:20 PM" string format) with a hardcoded `-05:00` offset and returns `null` for "TBD" or unparseable input; (c) an `isStaleInProgress(g, updatedAt)` helper that returns true only when all three threshold conditions are met; (d) `classifyTodayGame(g, nowTime, updatedAt)` with a new branch returning `'final-pending'` placed BETWEEN `isFinal` and `g.live` checks (so genuine finals always win); (e) `pickTodayGame(games, nowTime, updatedAt)` with a `final-pending` priority bucket above `final` (sorted descending by gameTime for the doubleheader case); (f) a render branch in `computeHeroContent` for `state === 'final-pending'` outputting matchup + italic "final pending" + channel; (g) the CSS rule `.hero-state.final-pending { font-style: italic; }`. Modifying any one of these without the others will produce inconsistent behavior.

**Hardcoded `-05:00` offset is a regular-season assumption.** The `firstPitchMs` helper hardcodes a `-05:00` UTC offset, which is correct for CDT (the timezone the entire 2026 regular season runs in — DST runs March 8 through November 1, and the Cubs season runs March 26 through September 27). If the Cubs play postseason games after November 1, the offset becomes wrong by one hour and `firstPitchMs` returns a timestamp off by 60 minutes, which would make `gameAgeMin` over- or under-estimate and could misfire the staleness threshold. Not a bug to pre-fix; revisit only if October baseball happens. A proper fix would use `Intl.DateTimeFormat` with `timeZone: 'America/Chicago'` to compute the offset dynamically.

**Cron tightened to `*/10` during the primary window.** Companion change to the staleness escape hatch: `.github/workflows/update.yml` now runs `*/10 14-23,0-4 * * *` during 9am-midnight Central, replacing the prior 15-minute cadence. The `0 */3 * * *` overnight fallback is unchanged. 50% more attempts shrinks the typical staleness window when GitHub Actions cron drops cluster, but does not prevent drops (those are upstream on the GitHub side). The escape hatch catches whatever the tightened cron still misses; tightening the cron isn't sufficient on its own and the escape hatch isn't sufficient on its own — together they're belt-and-suspenders. The producer logic in `update_data.py` is unchanged.

## Visual identity

The look is an editorial almanac — think a 1968 Cubs game-day program, not a modern sports app.

- Palette: cream `#faf6ec`, royal Cubs blue `#0e3386`, Cubs red `#cc3433`.
- Typography: Playfair Display for headings, Source Serif 4 for body, JetBrains Mono for stats.
- **Do not add** purple gradients or brick-wall imagery. Muted ivy green is now the page's background pattern (see "Page background" below).

### Page background

The page has a full-bleed, fixed-position ivy pattern under all content — the almanac's Wrigley wallpaper voice. Implementation lives on `body::before`:

- Asset: `Ivy_back.jpg` at the repo root, 1672×941 JPEG, preprocessed for seamless tiling so `background-repeat: repeat` produces no visible seam at any viewport width.
- Properties: `background-size: auto` (native pixel size), `background-attachment: fixed` (pattern stays put on scroll), `background-position: top left`, `background-repeat: repeat`. The combination produces approximately the same per-leaf physical size on mobile portrait and desktop.
- `opacity: 0.92` softens the leaves about 8% — the cream paper underneath shows through, which warms the leaves slightly. This is the one-knob tuning control if the pattern ever needs to feel more prominent or more recessive.
- Layered at `z-index: 1`; `.container` sits above at `z-index: 2`.
- Don't switch to `background-size: cover` (would scale leaves bigger on desktop, breaking same-magnification across viewports). Don't add a `background-color` to the rule (the paper color is already the body background and showing through is the point).

## Page sections (in order)

1. **Season's Pulse** — marquee stats strip.
2. **NL Central standings** — divisional table.
3. **Recently & Coming Up** — last few results and next few games.
4. **Where to Catch the Game** — TV and radio coverage (renamed from "Where to Watch" in May 2026 when the section grew to cover radio in proportion with TV).
5. **Full Slate 162 Games** — complete schedule grid.
6. **Long Arithmetic** — pace-based projection with interactive slider.

## Interaction model

- Tap any section header to toggle that section's collapse state.
- Icon-only floating cluster anchored bottom-right: refresh, expand/collapse toggle, settings gear (left to right). 40×40 royal-blue squares with cream inline-SVG glyphs at 0.7 resting opacity, 1.0 on hover/focus.
- Tapping the gear opens a settings panel anchored above the cluster; tapping the gear again or anywhere outside the panel closes it. The panel is the home for instructional / meta content (currently: how to add to home screen, how the refresh / auto-update cadence works) — new settings-style copy goes here rather than on the visible page.

## Do not reintroduce

These were tried and intentionally removed. Do not add them back:

- Drag-to-reorder sections
- Standalone dateline `<div>`
- Italic subtitle
- Narrative lede paragraph
- Red star ornaments
- Double-rule graphic to the right of section titles
- Colophon footer
- Bracket collapse buttons (`[−]` / `[+]`)
- Browser-direct MLB API calls

## Known issues

- Pennant strip renders empty on first paint before data.json loads.
- Standings section has no empty-state fallback — if `standings` is an empty array, `renderStandings` clears the tbody and returns silently, leaving a headers-only table. Guarded upstream by `update_data.py`'s non-empty check, so rare in practice.
- Orphan `.dateline` CSS rule left behind after the dateline div was removed.
- Long Arithmetic slider doesn't initialize to the current pace value.

## Semantic contracts

Rules about non-obvious behavior that must survive future edits.

- Masthead GB label distinguishes three cases: sole leader (`holds 1st`), tied-for-first (`tied for 1st`), and trailing (`X.X GB`). Keep these distinct in any future `renderMasthead` edits — do not collapse "sole leader" and "tied" into a single label.
- Initial page load: all six main sections start collapsed. This is intentional, not an oversight — it's the almanac conceit in action (quiet on arrival, visitor chooses what to see). Do not default any top-level section to expanded without an explicit request to change the conceit.
- Hero band content priority: today's games first (with doubleheader priority pre-game > in-progress > final-pending > final, latest game by first-pitch within both the final-pending and final buckets), then next unplayed future game, then season complete. All dates anchored to America/Chicago (the almanac's frame of reference). Band hides itself via `is-empty` class if content can't be determined — never renders a dangling rule.
- Hero band channel segment shows on pre-game, in-progress, final-pending, and next-upcoming cases so the fan knows where to tune in (or, in the final-pending case, where the game has been on the air), rendered as `TV / WSCR 670` (TV from `g.tvNational` or `g.broadcast`; radio is a render-time constant — see channel-rendering contract below). Hidden on final (game is over; channel info is dead) and on season complete (no game to watch). Channel lookup is per-game, not per-date, so doubleheaders pick up the right game's broadcast.
- Section V (Full Slate) at viewports ≤700px: the standalone time and channel-cell columns are hidden, and both are re-emitted as a single sub-line under the opponent in the format `TIME · TV / WSCR 670` (`.sched-subline`). The hide selector targets `.sched-channel-cell` (the wrapper that holds the TV+radio pair as one grid item), not the inner `.sched-channel` spans — if you rename the wrapper, update the media query too. The national accent (gold star prefix, bold ink) carries through via `.sched-subline-channel.national` on the TV portion only; the radio portion stays in `--ink-soft` regardless. Channel is the "where to catch the game" promise — never let mobile drop it again.
- Section VI (Long Arithmetic) sits directly on the page background — no card wrapper. The slider runs the full content width at every viewport, with the value-readout caption (`current pace · .XXX` when at pace, bare `.XXX` with `↺ reset` when off) stacked beneath the track, not beside it. The slider's `step="1"` is load-bearing: it ensures the snapped current-pace value rounds identically to the `(w/(w+l)).toFixed(3)` formula used by Section I (pulse strip) and Section II (standings). All three pace renderings must agree to the third decimal — if you change the step, you reintroduce the .654/.655 mismatch.
- Schedule date labels carry the weekday prefix universally: every date rendered in a schedule context (Section III's Recently / Coming Up, Section V's Full Slate rows) uses the `weekday: 'short', month: 'short', day: 'numeric'` Intl shape, rendered uppercase as `THU, MAR 26`. `formatShortDate` and Section V's inline formatter must stay in lockstep — if you add a new schedule list, use the same shape; don't drop the weekday to save column width.
- Named subsection groups in Section V are universally collapsible with persistent open state. Date-sort months use `openMonths`; channel-sort groups use `openChannels`. Both are closure-scoped Sets that survive `renderSchedule()` re-renders, so filter clicks, sort toggles, and refreshes all preserve which groups the visitor opened. Initial state is collapsed for both — opt-in expansion only. If you add a new grouping mode (by opponent, by series, etc.), give it its own parallel Set and the same `month-collapsible` / `month-collapsed` chevron treatment; do not ship a grouping mode without collapsibility.
- "You-are-here" markers across the page share a single visual vocabulary: an 8% maroon wash (`rgba(122, 31, 43, 0.08)`), a 3px solid `var(--accent)` left bar, and 10px of left padding to clear the bar. Section V's `.schedule-game.today` and Section II's `.standings tr.cubs-row` both use this treatment — the today-row marks the current date in the schedule, the cubs-row marks the visitor's team in the standings. Keep the two in lockstep: if you re-tune the wash opacity, bar weight, or padding offset on one, apply the same change to the other so the page reads as one consistent "this is your anchor" signal. The cubs-row layers additional cues on top (deep-maroon text via `--accent-deep`, 700 weight, red `▸` triangle prefix) because table rows are denser than schedule rows and need more help; those extras are cubs-row-specific and don't need to mirror anywhere.
- The page refers to its in-market audience as "Chicagoland," never a specific suburb. The visitor base spans the Chicago suburbs, and naming any one town would exclude the others. This applies to Section IV's Marquee card, Section V's filter explanation, and any future copy that references where the viewer is watching from.
- Refresh button enforces a 600ms minimum spin window: `fetchData` races the actual fetch against a 600ms timer via `Promise.all`, so the rotation registers even on localhost / fast networks where `data.json` returns in under ~50ms. Silent on-load fetches skip the floor. The error path must `await minSpin` before rendering the failure toast, or the icon freezes mid-rotation on fast failures. Don't replace the parallel race with a sequential `await fetch(); await minSpin;` — that stacks 600ms on top of every refresh instead of riding alongside it.
- Settings panel and refresh toast share the bottom-right corner without colliding by occupying distinct vertical bands: cluster at `bottom: 24px` (mobile 16px), toast at `bottom: 80px` (mobile 72px) with `z-index: 99`, panel at `bottom: 140px` (mobile 132px) with `z-index: 101`. The panel is `var(--paper-deep)` with a `1px solid var(--rule)` border, 5px radius matching the icon squares, soft royal-blue-tinted drop shadow `0 2px 12px rgba(14, 51, 134, 0.08)`, 300px wide capped by `calc(100vw - 48px)` (mobile `calc(100vw - 32px)`) so it shrinks gracefully on narrow viewports. Resolution chosen at design time was to anchor the panel rather than reposition the toast — do not move the toast to make room for new panel content; widen / heighten the panel within its band instead.
- Settings panel outside-click uses path-checking via `.contains()` on both the gear button and the panel itself, not capture-phase trickery. The gear's own click bubbles up to the document handler, but the `.contains(e.target)` check on `settingsBtn` short-circuits the close, so the toggle works in either order. Mirror this pattern if you add another disclosure-style control — capture-phase listeners fight the natural event flow and break when nested controls are added later.
- Gear button uses the standard ARIA disclosure pattern: `aria-label="Settings"`, `aria-controls="settingsPanel"`, and `aria-expanded` toggled `"true"`/`"false"` in lockstep with the panel's `.visible` class. If you add a state to the panel, update `aria-expanded` in the same `setSettingsOpen` helper — do not branch state setters.
- Channel rendering is a TV+radio pair (`TV / WSCR 670`) across every per-game listing — hero band, Recent, Coming Up, Full Slate main row, Full Slate mobile sub-line. `resolveChannel(g)` returns `{ tv, radio, isNational }`; radio is the render-time string constant `"WSCR 670"`, not a `data.json` field, because regular-season radio coverage is uniform across all 162 games. Don't promote it to a data field — `update_data.py` and `data.json` are intentionally untouched. Postseason rights can shift; that's October work, not regular-season work. The TV portion picks up the `national` accent when applicable; the radio portion always reads in `--ink-soft` so the page communicates "TV varies, radio is constant" typographically.
- Radio span requires the two-class pattern: `class="<base> <base>-radio"` (e.g. `class="game-channel game-channel-radio"`, `class="hero-channel hero-channel-radio"`, `class="sched-channel sched-channel-radio"`, `class="sched-subline-channel sched-subline-channel-radio"`). The base class on the radio span is load-bearing — it's how the radio span picks up JetBrains Mono, uppercase, and letter-spacing typography directly. Inheritance through the parent wrapper isn't reliable across all four contexts; the two-class pattern was added after the May 2026 deploy when single-class radio spans rendered in serif. The `-radio` modifier rule sets `color: var(--ink-soft); font-weight: 400` — the font-weight reset defeats any bold inherited from a sibling `.national` span.
- Full Slate main row (`buildGameRow`) wraps the TV+radio pair in a `.sched-channel-cell` span to preserve the 5-column grid (`80px 1fr 70px 180px 38px`). The wrapper is the grid item; it carries `text-align: right` and the inner spans flow inline within it. Don't unwrap the pair into direct grid children — that creates a 6th grid item and pushes the W/L badge to a wrapped second row on completed games. The Recent/Coming Up `.game-channel` div, the hero band, and the Full Slate sub-line don't need this wrapper because they're not direct grid children.
- Section IV's `data-section-id` stays as `watch` despite the user-facing rename to "Where to Catch the Game." The id is structural, not a label — keeping it stable preserves any localStorage section-order continuity from the old drag-to-reorder feature. Don't rename the id to match the title; rename the title freely.

## Working with Dave

- Address the user as "Dave."
- No emojis.
- Be honest and direct — engage with problems rather than offering reassurance.
- Always check your work before presenting it.
- When told "don't change anything except X," change only X. No drive-by cleanup.
- Dave prefers flowing prose over bullet-heavy responses in conversation.
