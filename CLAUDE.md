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
  "updatedAt": "2026-04-19T18:57:00Z",
  "schedule": [
    {
      "date": "2026-04-05",
      "opp": "CLE",
      "home": true,
      "time": "1:20 PM CT",
      "result": "W 5-3"
    }
  ],
  "standings": [
    {
      "team": "Cubs",
      "w": 10,
      "l": 5,
      "pct": ".667",
      "gb": "-"
    }
  ]
}
```

`result` is `null` for unplayed games. `home` is boolean. `standings` covers the five NL Central clubs.

## Visual identity

The look is an editorial almanac — think a 1968 Cubs game-day program, not a modern sports app.

- Palette: cream `#faf6ec`, royal Cubs blue `#0e3386`, Cubs red `#cc3433`.
- Typography: Playfair Display for headings, Source Serif 4 for body, JetBrains Mono for stats.
- **Do not add** purple gradients, ivy textures, or brick-wall imagery.

## Page sections (in order)

1. **Season's Pulse** — marquee stats strip.
2. **NL Central standings** — divisional table.
3. **Recently & Coming Up** — last few results and next few games.
4. **Where to Watch** — broadcast info.
5. **Full Slate 162 Games** — complete schedule grid.
6. **Long Arithmetic** — pace-based projection with interactive slider.

## Interaction model

- Tap any section header to toggle that section's collapse state.
- Floating **Refresh** and **Collapse All** buttons anchored bottom-right.

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
- Hero band content priority: today's games first (with doubleheader priority pre-game > in-progress > final, latest final if all final), then next unplayed future game, then season complete. All dates anchored to America/Chicago (the almanac's frame of reference). Band hides itself via `is-empty` class if content can't be determined — never renders a dangling rule.
- Hero band channel segment shows on pre-game, in-progress, and next-upcoming cases so the fan knows where to tune in. Hidden on final (game is over; Marquee is dead information) and on season complete (no game to watch). Channel lookup is per-game via `g.tvNational`, not per-date, so doubleheaders pick up the right game's broadcast.
- Section V (Full Slate) at viewports ≤700px: the standalone time and channel columns are hidden, and both are re-emitted as a single sub-line under the opponent in the format `TIME · CHANNEL` (`.sched-subline`). The national accent (gold star prefix, bold ink) carries through via `.sched-subline-channel.national` for FOX, Apple TV+, NBC/Peacock, ABC/ESPN. Channel is the "where to watch" promise — never let mobile drop it again.
- Section VI (Long Arithmetic) sits directly on the page background — no card wrapper. The slider runs the full content width at every viewport, with the value-readout caption (`current pace · .XXX` when at pace, bare `.XXX` with `↺ reset` when off) stacked beneath the track, not beside it. The slider's `step="1"` is load-bearing: it ensures the snapped current-pace value rounds identically to the `(w/(w+l)).toFixed(3)` formula used by Section I (pulse strip) and Section II (standings). All three pace renderings must agree to the third decimal — if you change the step, you reintroduce the .654/.655 mismatch.
- Schedule date labels carry the weekday prefix universally: every date rendered in a schedule context (Section III's Recently / Coming Up, Section V's Full Slate rows) uses the `weekday: 'short', month: 'short', day: 'numeric'` Intl shape, rendered uppercase as `THU, MAR 26`. `formatShortDate` and Section V's inline formatter must stay in lockstep — if you add a new schedule list, use the same shape; don't drop the weekday to save column width.
- Named subsection groups in Section V are universally collapsible with persistent open state. Date-sort months use `openMonths`; channel-sort groups use `openChannels`. Both are closure-scoped Sets that survive `renderSchedule()` re-renders, so filter clicks, sort toggles, and refreshes all preserve which groups the visitor opened. Initial state is collapsed for both — opt-in expansion only. If you add a new grouping mode (by opponent, by series, etc.), give it its own parallel Set and the same `month-collapsible` / `month-collapsed` chevron treatment; do not ship a grouping mode without collapsibility.

## Working with Dave

- Address the user as "Dave."
- No emojis.
- Be honest and direct — engage with problems rather than offering reassurance.
- Always check your work before presenting it.
- When told "don't change anything except X," change only X. No drive-by cleanup.
- Dave prefers flowing prose over bullet-heavy responses in conversation.
