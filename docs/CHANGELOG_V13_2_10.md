# Fishing Simulator v13.2.10 Changelog

## M12 — Phase B high-seas backend (partial)

- Added `TrafficWorld(phase="B")` with the full deterministic source-plan population: 300 corporate catchers, 11 motherships, 80 independent gillnetters, 40 independent longliners, 15 corporate longliners, 5 Coast Guard vessels and 10 Soviet trawlers (461 total).
- Added projected Phase B bounds spanning 140°E–175°W and 41°N–62°N with date-line wrapping around the 160°E/45°N reference.
- Added eleven deterministic mothership cluster anchors and clustered corporate catcher routes, with stable `mothership_id` links, southern/transit routes for independent vessels and treaty-boundary patrol routes for Soviet trawlers.
- Added seasonal spatial-index thinning when month/day are supplied: most corporate catchers and motherships are off-index outside May 20–August 10 while stable identities persist. Known/active distress contacts remain available.
- Tagged traffic contact snapshots with phase and rejected cross-phase restore attempts.
- Connected `WorldContext(phase="B")` to Phase B traffic and matching weather bounds.
- Added an 80-NM Phase B coarse weather overview as the performance-conscious default, retaining an explicit 20-NM override for profiling. Phase A retains 20-NM default weather.
- Added Phase B benchmark utility and 13 focused regression tests.
- Updated package version to 13.2.10 and kept all Markdown under `/docs`.

## Compatibility

- `TrafficWorld()` continues to default to Phase A, preserving existing in-game coordinates and the active Pygame campaign.
- Existing Phase A traffic contact snapshots without a `phase` field continue to load as Phase A.
- Full Phase B campaign viewport and save/load integration are not yet delivered.
