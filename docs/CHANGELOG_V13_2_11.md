# Changelog — v13.2.11

## Phase B campaign interface

- Added A / REGIONAL and B / HIGH SEAS tabs to the in-game navigation chart; keyboard A/B also switches sheets while the chart is open.
- Added a cached Phase B high-seas chart with latitude/longitude graticule, schematic coastline, fleet operating box, mothership cluster context, Hakodate reference, and explicit approximate-chart disclaimer.
- Added Phase B reported-vessel markers, staleness labels, selection highlight, and `R` to open the existing radio UI for an in-range selected contact.
- Added chart route editing across the wide Phase B bounds while keeping waypoint storage compatible with legacy physical movement.
- Added coordinate adapters for player fixes, chart waypoints, sea-view traffic hulls, and the unified Coast Guard/tow identity.
- Added independent Phase A/B traffic, weather and relationship caches, with phase-aware career-save validation and restoration of previously visited phase snapshots.
- Added a weather-grid time rebase for phases first visited late in a career, avoiding a huge catch-up loop for unseen historical weather.
- Sorted Phase B chart labels nearest-first and capped visible labels while retaining all known marker hitboxes.
- Moved the current status and use instructions into `/docs`, alongside both the optimized roadmap and source Plan 13.2.xx.

## Validation and boundaries

- Phase B UI/coordinate contract tests added in `test_v13_2_11_phase_b_campaign_ui.py`.
- Current Phase B coastlines are schematic; hull physics still uses the legacy local plane through a projection adapter.
- A Pygame-enabled graphical playtest was not possible in the build environment.
