# V13V1-14 — Fishing Gut Book and Chart Gut Markers

## Implemented

- Added a **GUT BOOK** tab to the Ship's Notebook (`F9`). Use **5** to open the tab directly while the notebook is open, or **Tab** to cycle sections.
- The gut book records the first confident crew lookout for each hotspot: campaign date/time, sailor, skill, species call, confidence, and the chart position the crew plotted at that moment.
- Entries are retained after a school expires and are labelled **ACTIVE** or **HISTORICAL**. The list is capped at 100 records. Positions are snapshots of crew belief; navigation fixes do not silently rewrite old records.
- The navigation chart now draws a pale-yellow `G##` diamond for each live school a main-deck lookout has detected with at least 50% confidence. Multiple sailors looking at the same school produce one marker.
- Live chart markers use the current dead-reckoning position error. A successful fix can therefore move a gut marker, while the gut-book entry remains at its original recorded plot.
- The chart key distinguishes `G#` crew gut plots from `R#` uncertain fleet/harbour reports. The chart never marks undetected live hotspots, and it does not show the hidden physical ship position.
- All project Markdown files are preserved in the release ZIP. This includes `v13 Plans.md` at the root and under `docs/`, the roadmap, prior changelogs, and this changelog.

## Verification

Run from the project directory:

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

Automated model/integration tests cover belief-offset plotting, bounded session history, recording at the first confident detection, ACTIVE/HISTORICAL status, notebook navigation, and chart-marker integration. Pygame is unavailable in the build environment, so a graphical playtest is still needed for marker legibility and gut-book layout at the minimum window size.

## Limitations

The gut book persists across hotspot expiry for the current game session. The project has no save-game format, so the record does not survive closing and restarting the application.
