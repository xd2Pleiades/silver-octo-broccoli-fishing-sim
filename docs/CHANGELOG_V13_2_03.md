# Fishing Simulator v13.2.03 — Regional Weather Grid

## Implemented

- Added `fishing_sim/world/weather_grid.py`: deterministic, spatially varying weather at 20-nautical-mile resolution for Phase A.
- Weather cells include pressure, east/north wind components, precipitation, cloud, fog, and normalized sea state.
- Weather advects upstream using wind and evolves on a fixed five-simulation-second tick (about 12 in-game minutes under the current 600-second game-day scale).
- Added stable, versioned JSON snapshot/restore helpers with schema, bounds, finite-value, and field-range validation.
- Added a copied-state 72-hour forecast at configurable intervals. Forecasting does not mutate the live weather grid.
- Added `WorldContext.weather` so traffic and weather share the same world simulation clock.
- Integrated the grid into the live game loop. The existing shipboard `Weather` remains authoritative for the player; that observed weather is assimilated into the current local grid cell. The selected-contact radio UI now uses sampled weather at the contacted ship for its weather report.
- Moved all Markdown files into the single project `docs/` folder. Historical duplicates are retained under unique names instead of overwriting one another. Tests were updated for the new document locations.
- Updated package version, window caption, and runtime diagnostics to v13.2.03.

## Deliberately deferred

- Full career save/load integration for the weather snapshot (the snapshot API is ready, but the legacy game does not yet have one authoritative save format).
- Using the grid as the authority for player-local weather transitions, market surge/scarcity, and tow-line risk. Those still use existing systems until an explicit one-source-of-truth migration is made.
- A weather-grid map overlay, Phase B high-seas bounds, and NumPy/vectorized storage.

## Verification

See `TEST_RESULTS_V13_2_03.txt`. Weather grid, forecast immutability, fixed-tick cadence, snapshot round-trip, radio weather integration, and selected previous regressions are covered. Visual playtesting was not possible in this environment because Pygame is unavailable.
