# v13.2.10 — Phase B High-Seas Backend Status

## Scope

This release starts M12 from `Roadmap_V13_2_Optimized.md` and `Plan 13.2.xx.md`. It adds a usable high-seas simulation backend, but does not claim the entire Phase B campaign UI is complete. The default game remains Phase A.

## Delivered

- `TrafficWorld(phase="B")` creates all 461 stable vessel identities from `SOURCE_FLEET_COUNTS`.
- High-seas coordinates use the equirectangular plane centered at 160°E/45°N, with longitudes wrapped through the date line. The bounds represent 140°E–175°W and 41°N–62°N, including the Hokkaido transit corridor.
- Eleven deterministic mothership anchors distribute 300 corporate catcher schedules into local clusters. Independents occupy transit/southern waters, while Soviet routes patrol near the 45°N treaty boundary. Coast Guard routes span the transit corridor and high-seas approaches.
- Routes are deterministic and bounded by projected geography. The active ship cap remains 30 and traffic samples on a fixed three-simulation-second tick.
- When an explicit month/day is supplied to a Phase B tick, most corporate catchers and motherships are removed from the live spatial/radio index outside May 20–August 10. Stable IDs and schedule state stay resident. Known contacts, runtime contacts, activity overrides, and unresolved distress ships remain queryable.
- Traffic contact snapshots store their phase, and restore rejects a Phase A/Phase B mismatch. Older snapshots without a phase are treated as Phase A for backwards compatibility.
- `WorldContext(phase="B")` now selects Phase B traffic and matching weather bounds. Phase A defaults and schedule output are unchanged.
- Phase B weather bounds use an 80-NM coarse overview by default; users can set `cell_size_nm=20` for detailed profiling.

## Local benchmark

See `PERFORMANCE_V13_2_10.txt`. The latest run on the build host measured: 12.50 ms fleet construction; 1.26 ms average full traffic tick (1.57 ms p95); 0.066 ms average radio-candidate query (0.129 ms p95); 384-cell coarse weather tick averaging 1.85 ms (2.18 ms p95); and a 72-hour forecast in 0.67 seconds. These are microbenchmark observations, not a guarantee on other hardware.

## Not yet delivered

- No selectable Phase B mode is exposed in the normal Pygame campaign. The legacy chart/sea viewport is still calibrated around Hakodate regional coordinates.
- High-seas ship silhouettes/chart viewport, date-line map presentation and user-facing world transition are not implemented.
- The full career save/load flow remains wired to the default Phase A `TrafficWorld`; Phase B snapshots are phase-safe, but full-game Phase B career save/load has not been tested or completed.
- Phase B's default weather is intentionally coarse, not the plan's final 20-NM global field. The 20-NM override creates over 6,000 cells and still needs profiling/optimization before default enablement.
- No Pygame visual test was possible in this environment.

## Verification

- 12 dedicated Phase B tests passed.
- 132 focused v13.2 world/weather/tow/distress/save/relationship regression tests passed after updating current-version assertions.
- Python compilation passed.
- Exact date-line coordinate round trips, stable IDs, bounds, clustering, seasonal sparse indexing, active cap, phase mismatch rejection and weather snapshot restoration are covered.
