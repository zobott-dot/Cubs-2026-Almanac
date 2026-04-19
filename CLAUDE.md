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

- Masthead shows "As of conversation" placeholder text instead of the real timestamp.
- Pennant strip renders empty on first paint before data.json loads.
- Standings section can render empty when data is missing or malformed.
- Duplicate 4/5 CLE entries appear in data.json.
- Orphan `.dateline` CSS rule left behind after the dateline div was removed.
- Refresh button doesn't cache-bust — browser may serve stale data.json.
- `.pulse-L` class has no `font-weight` set.
- Long Arithmetic slider doesn't initialize to the current pace value.

## Working with Dave

- Address the user as "Dave."
- No emojis.
- Be honest and direct — engage with problems rather than offering reassurance.
- Always check your work before presenting it.
- When told "don't change anything except X," change only X. No drive-by cleanup.
- Dave prefers flowing prose over bullet-heavy responses in conversation.
