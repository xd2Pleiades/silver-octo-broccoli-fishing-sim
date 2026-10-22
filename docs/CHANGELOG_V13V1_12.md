# V13V1-12 — Chart fishing reports and uncertain leads

## Implemented

- **Fishing-spot reports now appear on the navigation chart.** Each report gets a numbered `R#` marker, a reported-area ring, a species guess, its source tag, approximate age, and a source-confidence percentage.
- **Reports are leads, not truth markers.** Some reports are based on a current hotspot but carry positional noise and may misidentify the species. Others are false rumours placed in plausible offshore water, generally away from current schools. The UI never says which report is true.
- **Freshness is visible.** Reports age in simulation time, their chart ink fades as they grow stale, and old reports expire. The live chart retains at most five leads to limit map clutter.
- **The chart side panel now has a dedicated `FISHING SPOT REPORTS (?)` section.** It lists recent leads and explicitly reminds the player they may be false or stale. The chart key explains that `R#` markers are unconfirmed reports, not confirmed schools.
- **Report arrivals are recorded in the Ship's Notebook crew log only.** They do not create fake speech bubbles attributed to a sailor. This extends the V13V1-11 conversation-first bubble routing.
- **Markdown documentation is included in the release ZIP.** Existing root and package changelogs, design notes and `docs/` material are retained. The supplied `v13 Plans.md` is included both at the ZIP root and in `docs/`.

## Tuning defaults

- First report: after approximately 25–50 game seconds.
- Later reports: approximately every 180–300 game seconds.
- Grounded-report chance when a chartable live hotspot exists: 64%.
- Report search-area radius: 250–850 chart design units.
- Report lifetime: 1,200–2,700 game seconds.
- Maximum active chart reports: 5.

These values are initial playtest settings, not a guarantee of truth. A source-confidence score describes the reputation of the source, not whether the specific claim is correct.

## Verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

The report model tests cover grounded and false leads, plausible water positions, deterministic generation, aging/expiry, source-confidence visualization, and the rule that truth status is never exposed by the chart drawing code. **Full project suite: 252 tests passed, 0 failed; Python compilation passed.** A Pygame graphical playtest is still required to validate marker readability and panel layout at normal and small window sizes.

## Next milestone

`v13v1-13` — optional fishing-log gut book. `v13v1-14` — integration, balance, and release hardening.
